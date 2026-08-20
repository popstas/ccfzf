"""Признак клиента, которым сессию открывали в последний раз.

`entrypoint` лежит полем в каждой записи транскрипта: `cli` у терминального
клиента, `claude-desktop` у приложения. Другого признака нет вовсе — файл,
каталог и формат у обеих сессий одинаковые, — а читателю он нужен, чтобы
вернуть человека туда, откуда он ушёл.

Запуск: python3 tests/test_entrypoint.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

# Шестое значение tail_facts — состояние агента из хвоста. Подставным хвостам
# этих тестов оно безразлично: своё правило у него своё, в test_agent_state.py.
NO_STATE = {"state": "", "question": ""}


DESKTOP = "claude-desktop"


def _write(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _say(text, entrypoint=None):
    rec = {"type": "assistant", "timestamp": "2026-08-20T19:04:36.000Z",
           "message": {"role": "assistant", "content": text}}
    if entrypoint is not None:
        rec["entrypoint"] = entrypoint
    return rec


def _entrypoint_of(records):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        _write(path, records)
        return CC["tail_facts"](path)[4]


def test_the_tail_names_the_client():
    assert _entrypoint_of([_say("hi", DESKTOP)]) == DESKTOP


def test_the_last_client_wins():
    """Сессию приложения можно продолжить `claude --resume` в терминале.

    Обратный проход по хвосту отвечает на вопрос «где она сейчас», а не «где
    её завели»: вернуть человека надо туда, откуда он ушёл в последний раз.
    """
    assert _entrypoint_of([_say("in the app", DESKTOP),
                           _say("and then in a terminal", "cli")]) == "cli"


def test_a_transcript_without_the_field_reads_as_nothing():
    """Пустая строка, а не «cli»: поля не было у прежних версий агента вовсе.

    Выдумывать за них `cli` значило бы утверждать то, чего файл не говорит, —
    а читателю разница видна: по пустому полю он оставляет прежнее поведение.
    """
    assert _entrypoint_of([_say("no field here")]) == ""


def test_a_missing_file_reads_as_nothing():
    assert CC["tail_facts"]("/nonexistent-transcript-for-tests.jsonl")[4] == ""


# ── Памятка ────────────────────────────────────────────────────────────────


P = "/d/a.jsonl"


def _tail(entrypoint):
    return lambda path: ("T", "D", 0, {}, entrypoint, NO_STATE)


def test_the_note_keeps_the_client():
    got = CC["facts_for"](P, 100.0, {}, tail=_tail(DESKTOP),
                          head=lambda p: "g", size_of=lambda p: 10)
    assert got["entrypoint"] == DESKTOP, got


def test_a_note_that_never_knew_the_client_is_a_miss():
    """Иначе простаивающая сессия не узнала бы поля никогда.

    Памятка ключуется по mtime, а у закончившейся сессии он больше не
    сдвинется: запись, положенная прошлой версией, читалась бы как полная, и
    строка вечно оставалась бы без признака клиента. Та же болезнь уже
    описана у `gist` в самой `facts_for`.
    """
    calls = []

    def tail(path):
        calls.append(path)
        return ("T", "D", 0, {}, DESKTOP, NO_STATE)

    old = {P: {"mtime": 100.0, "title": "T", "doing": "D",
               "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 100.0, old, tail=tail, head=lambda p: "g",
                          size_of=lambda p: 10)
    assert calls == [P], calls
    assert got["entrypoint"] == DESKTOP, got


def test_a_note_that_knows_the_client_stays_a_hit():
    calls = []

    def tail(path):
        calls.append(path)
        return ("T", "D", 0, {}, DESKTOP, NO_STATE)

    old = {P: {"mtime": 100.0, "title": "T", "doing": "D", "entrypoint": "cli",
               "agentState": "", "agentQuestion": "",
               "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 100.0, old, tail=tail, head=lambda p: "g",
                          size_of=lambda p: 10)
    assert calls == [], calls
    assert got["entrypoint"] == "cli", got


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
