"""Состояние агента, посчитанное из хвоста транскрипта.

Хуков не бывает ни на Windows, ни на маке (каталога `~/.claude/claude-wt/` там
нет вовсе), ни у сессии Claude Desktop. Такая сессия получала `agent: None`, и
строка вечно показывала серый кружок — «простаивает» вместо «спросить не у
кого». Отвечает на это тот же обратный проход по хвосту, каким считаются
заголовок, начало хода и `entrypoint`.

Запуск: python3 tests/test_agent_state.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

AT = "2026-08-21T22:04:29.000Z"


def _write(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _assistant(blocks, stop_reason="tool_use"):
    return {"type": "assistant", "timestamp": AT,
            "message": {"role": "assistant", "content": blocks,
                        "stop_reason": stop_reason}}


def _text(t, stop_reason="end_turn"):
    return _assistant([{"type": "text", "text": t}], stop_reason)


def _call(tool_id, name, inp=None):
    return _assistant([{"type": "tool_use", "id": tool_id, "name": name,
                        "input": inp if inp is not None else {}}])


def _result(tool_id):
    """Ответ инструмента: под `type: user`, но человеком не считается."""
    return {"type": "user", "timestamp": AT, "toolUseResult": {"ok": True},
            "message": {"role": "user",
                        "content": [{"type": "tool_result",
                                     "tool_use_id": tool_id,
                                     "content": "done"}]}}


def _human(text="go on"):
    return {"type": "user", "timestamp": AT,
            "message": {"role": "user", "content": text}}


def _facts(records):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        _write(path, records)
        return CC["tail_facts"](path)[5]


def _state(records):
    return _facts(records)["state"]


QUESTION = {"questions": [{"question": "Merge strategy?", "header": "Merge",
                           "options": [{"label": "squash"}]},
                          {"question": "Release now?", "header": "Release",
                           "options": [{"label": "yes"}]}]}


# ── Что значит незакрытый вызов ────────────────────────────────────────────

def test_an_open_question_is_a_question():
    assert _state([_human(), _call("t1", "AskUserQuestion", QUESTION)]) == "question"


def test_an_open_plan_is_a_question_too():
    """ExitPlanMode ждёт человека ровно так же, только текста у него нет."""
    got = _facts([_human(), _call("t1", "ExitPlanMode", {"plan": "..."})])
    assert got["state"] == "question", got
    assert got["question"] == "", got


def test_an_open_tool_is_work():
    assert _state([_human(), _call("t1", "Bash", {"command": "du -sh"})]) == "active"


def test_a_closed_tool_is_work_too():
    """Результат пришёл, ход не кончен — агент считает, что делать дальше."""
    assert _state([_human(), _call("t1", "Bash"), _result("t1")]) == "active"


def test_an_answered_question_is_no_longer_a_question():
    """Ответ на AskUserQuestion приезжает `tool_result`, как у любого вызова."""
    assert _state([_human(), _call("t1", "AskUserQuestion", QUESTION),
                   _result("t1")]) == "active"


def test_a_finished_turn_waits_for_a_prompt():
    assert _state([_human(), _call("t1", "Bash"), _result("t1"),
                   _text("готово")]) == "review"


def test_a_fresh_prompt_is_work():
    """Человек только что написал, агент ещё ничего не ответил."""
    assert _state([_text("готово"), _human("а теперь вот это")]) == "active"


# ── Почему не stop_reason ──────────────────────────────────────────────────

def test_stop_reason_does_not_tell_work_from_waiting():
    """Тот самый контрпример, ради которого правило написано по имени вызова.

    Снято живьём 2026-08-21 на сессии 44e3e1b8: в 21:55 последней записью стоял
    `tool_use` `Bash du -sh`, в 22:04 — `tool_use` `AskUserQuestion`. Работа и
    ожидание, а `stop_reason` в обеих один и тот же.
    """
    работа = [_human(), _call("t1", "Bash", {"command": "du -sh"})]
    ожидание = [_human(), _call("t1", "AskUserQuestion", QUESTION)]
    stop = "message.stop_reason"
    assert работа[-1]["message"]["stop_reason"] == "tool_use", stop
    assert ожидание[-1]["message"]["stop_reason"] == "tool_use", stop
    assert _state(работа) != _state(ожидание)


# ── Граница хода ───────────────────────────────────────────────────────────

def test_a_new_prompt_closes_an_unanswered_question():
    """На вопрос отвечают и не кнопкой — новым промптом поверх него.

    `tool_result` при этом не приезжает вовсе, то есть вызов так и остаётся
    незакрытым. Без границы хода такая сессия вечно числилась бы ждущей.
    """
    assert _state([_call("t1", "AskUserQuestion", QUESTION),
                   _human("не надо, сделай иначе")]) == "active"


def test_a_question_from_a_previous_turn_is_not_the_current_state():
    assert _state([_call("t1", "AskUserQuestion", QUESTION),
                   _human("ладно"),
                   _call("t2", "Bash"), _result("t2"),
                   _text("сделал")]) == "review"


# ── Текст вопроса ──────────────────────────────────────────────────────────

def test_the_question_text_comes_from_the_call_itself():
    """До версии 2.1.234 считалось, что записи с вызовом в хвосте нет вовсе.

    Снято живьём 2026-08-21: у ждущей сессии последняя запись файла несёт
    полный `input` — все вопросы, заголовки и варианты. То есть источник у
    вопроса есть и без хука PreToolUse.
    """
    got = _facts([_human(), _call("t1", "AskUserQuestion", QUESTION)])
    assert got["question"] == "Merge strategy? · Release now?", got


def test_a_broken_input_costs_the_text_but_not_the_state():
    got = _facts([_human(), _call("t1", "AskUserQuestion", {"questions": "?"})])
    assert got["state"] == "question", got
    assert got["question"] == "", got


def test_the_question_text_is_only_for_a_question():
    got = _facts([_human(), _call("t1", "Bash")])
    assert got["question"] == "", got


# ── Сказать нечего ─────────────────────────────────────────────────────────

def test_an_empty_transcript_says_nothing():
    got = _facts([])
    assert got["state"] == "" and got["question"] == "", got


def test_a_missing_file_says_nothing():
    got = CC["tail_facts"]("/nonexistent-transcript-for-tests.jsonl")[5]
    assert got == {"state": "", "question": ""}, got


def test_nothing_to_say_is_not_a_record():
    """Пустое состояние — не `idle`: выдуманное «простаивает» и есть та ложь,
    от которой всё затевалось."""
    assert CC["from_tail"]({"state": "", "question": ""}, 5, 100) is None
    assert CC["from_tail"](None) is None


# ── Собранная запись ───────────────────────────────────────────────────────

def _built(state="question", question="q?", turn_at=5.0, mtime=100.0):
    return CC["from_tail"]({"state": state, "question": question}, turn_at, mtime)


def test_the_built_record_names_its_own_origin():
    """Читатель обязан отличать её от хуковой: на ней держатся и отметки
    «просмотрено», и доверие к нулю в деньгах."""
    assert _built()["source"] == "transcript"


def test_the_built_record_has_no_money_and_no_context():
    """Ключей нет вовсе, а не нули: считает их перехват статуслайна, а на
    машине без хуков его нет — показанный ноль был бы единственным числом
    строки, которое врёт."""
    got = _built()
    assert "costUsd" not in got, got
    assert "contextPct" not in got, got


def test_the_built_record_is_dated_by_the_file():
    """Ноль в `updated` значил бы «человек этого не видел» навсегда: на нём
    держится гашение кружка у читателя."""
    assert _built(mtime=1755800000.0)["updated"] == 1755800000


def test_the_built_record_carries_the_turn():
    assert _built(turn_at=42.0)["turnAt"] == 42


def test_the_built_record_carries_the_question():
    assert _built(question="Merge strategy?")["question"] == "Merge strategy?"


# ── Хук главнее хвоста ─────────────────────────────────────────────────────

def test_a_hook_record_wins_over_the_tail():
    """Дорога из хвоста — запасная, и включается она только там, где файлов
    хука нет вовсе."""
    with tempfile.TemporaryDirectory() as d:
        sid = "s1"
        with open(os.path.join(d, sid + ".state.json"), "w", encoding="utf-8") as fh:
            json.dump({"state": "active", "updated": 7}, fh)
        saved = CC["STATUS_DIR"]
        try:
            CC["STATUS_DIR"] = d
            got = CC["agent_of"](sid, "", 0, {"state": "question", "question": "q?"}, 100)
        finally:
            CC["STATUS_DIR"] = saved
    assert got["state"] == "active", got
    assert "source" not in got, got


def test_without_hook_files_the_tail_answers():
    with tempfile.TemporaryDirectory() as d:
        saved = CC["STATUS_DIR"]
        try:
            CC["STATUS_DIR"] = d
            got = CC["agent_of"]("s1", "", 0, {"state": "question", "question": "q?"}, 100)
        finally:
            CC["STATUS_DIR"] = saved
    assert got["state"] == "question", got
    assert got["source"] == "transcript", got


# ── Памятка фактов ─────────────────────────────────────────────────────────

P = "/d/a.jsonl"


def _tail(state):
    return lambda path: ("T", "D", 0, {}, "cli", {"state": state, "question": ""})


def test_a_note_without_the_state_is_a_miss():
    """Записи прошлой версии этого ключа не носят вовсе, и без промаха строка,
    чей mtime больше не сдвинется, осталась бы без состояния навсегда."""
    calls = []

    def tail(path):
        calls.append(path)
        return ("T", "D", 0, {}, "cli", {"state": "review", "question": ""})

    old = {P: {"mtime": 100.0, "title": "T", "doing": "D", "entrypoint": "cli",
               "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 100.0, old, tail=tail, head=lambda p: "g",
                          size_of=lambda p: 10)
    assert calls == [P], calls
    assert got["agentState"] == "review", got


def test_a_note_that_knows_the_state_stays_a_hit():
    calls = []

    def tail(path):
        calls.append(path)
        return ("T", "D", 0, {}, "cli", {"state": "review", "question": ""})

    old = {P: {"mtime": 100.0, "title": "T", "doing": "D", "entrypoint": "cli",
               "agentState": "question", "agentQuestion": "q?",
               "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 100.0, old, tail=tail, head=lambda p: "g",
                          size_of=lambda p: 10)
    assert calls == [], calls
    assert got["agentState"] == "question", got
    assert got["agentQuestion"] == "q?", got


def test_a_changed_file_recomputes_the_state():
    got = CC["facts_for"](P, 200.0, {P: {"mtime": 100.0, "agentState": "review",
                                         "agentQuestion": ""}},
                          tail=_tail("active"), head=lambda p: "g",
                          size_of=lambda p: 10)
    assert got["agentState"] == "active", got


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok   " + name)
        except AssertionError as e:
            bad += 1
            print("FAIL " + name + ": " + str(e))
    print("%d/%d passed" % (len(tests) - bad, len(tests)))
    sys.exit(1 if bad else 0)
