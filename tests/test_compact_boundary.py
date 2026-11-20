"""Граница сжатия контекста. Запуск: python3 tests/test_compact_boundary.py

После `/compact` в транскрипте ложится запись `compact_boundary`, за ней
сводка (`isCompactSummary`), сама команда `/compact` и её вывод
(`<local-command-stdout>`). Всё, что выше границы, к текущему ходу, кешу и
состоянию агента отношения не имеет: следующий вызов начнёт кеш заново со
сводки, а ход, закончившийся до сжатия, закончен.

Прежде проход принимал сводку и вывод команды за реплику человека, вставал на
них и до ответа агента не доходил вовсе: у сжатой сессии пропадала метка кеша
(случайно, а не по правилу), ход датировался секундой сжатия, а на машине без
хуков сессия горела зелёным — «человек написал, агент работает».

Записи в фикстурах — того вида, какой снят с живой сессии e586230b 2026-11-20.
"""
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

HUMAN_AT = 1785958000
T1, T2, T3, T4 = HUMAN_AT + 60, HUMAN_AT + 120, HUMAN_AT + 180, HUMAN_AT + 240


def _stamp(at):
    return datetime.datetime.fromtimestamp(
        at, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _human(at, text="сделай так"):
    return {"type": "user", "timestamp": _stamp(at),
            "message": {"role": "user", "content": text}}


def _answer(at, stop="end_turn", text="готово"):
    return {"type": "assistant", "timestamp": _stamp(at),
            "message": {"role": "assistant", "stop_reason": stop,
                        "content": [{"type": "text", "text": text}],
                        "usage": {"input_tokens": 3, "output_tokens": 10,
                                  "cache_read_input_tokens": 100,
                                  "cache_creation_input_tokens": 0}}}


def _compact(at, trigger="manual", attachments=0, pad=0):
    """Записи одного сжатия в том порядке, в каком они лежат в файле.

    `pad` — байты на вложение: после сжатия агент перечитывает файлы и кладёт
    их вложениями, и на живых сессиях за границей лежит 250–430 КБ, то есть
    больше TAIL.
    """
    recs = [
        {"type": "system", "subtype": "compact_boundary",
         "content": "Conversation compacted", "timestamp": _stamp(at),
         "compactMetadata": {"trigger": trigger}},
        {"type": "user", "isCompactSummary": True, "isVisibleInTranscriptOnly": True,
         "timestamp": _stamp(at - 1),
         "message": {"role": "user", "content":
                     "This session is being continued from a previous conversation"}},
    ]
    if trigger == "manual":
        recs += [
            {"type": "user", "isMeta": True, "timestamp": _stamp(at - 60),
             "message": {"role": "user", "content":
                         "<local-command-caveat>The command below was run directly"}},
            {"type": "user", "timestamp": _stamp(at - 60),
             "message": {"role": "user", "content":
                         "<command-name>/compact</command-name>\n"
                         "            <command-message>compact</command-message>\n"
                         "            <command-args></command-args>"}},
            {"type": "user", "repeatsCompactSummary": True, "timestamp": _stamp(at + 1),
             "message": {"role": "user", "content":
                         "<local-command-stdout>Compacted (ctrl+o to see full summary)"}},
        ]
    for _ in range(attachments):
        recs.append({"type": "attachment", "timestamp": _stamp(at),
                     "attachment": {"type": "file", "content": "x" * pad}})
    recs.append({"type": "last-prompt"})
    return recs


def _facts(records):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return CC["tail_facts"](path)


BEFORE = [_human(HUMAN_AT, "сделай отчёт"), _answer(T1, text="отчёт готов")]


# ── Сжатие и после него ничего ─────────────────────────────────────────────

def test_после_сжатия_ничего_простаивает():
    agent = _facts(BEFORE + _compact(T2))[5]
    assert agent["state"] == "idle", agent


def test_после_сжатия_ничего_кеша_нет():
    # Старый кеш мёртв: следующий вызов начнёт его заново со сводки.
    agent = _facts(BEFORE + _compact(T2))[5]
    assert "cacheAt" not in agent, agent


def test_после_сжатия_ничего_метка_сжатия():
    agent = _facts(BEFORE + _compact(T2))[5]
    assert agent.get("compactAt") == T2, agent
    assert isinstance(agent["compactAt"], int), agent


def test_после_сжатия_ничего_хода_нет():
    # Ход, закончившийся до сжатия, закончен; нового никто не начинал.
    assert _facts(BEFORE + _compact(T2))[2] == 0


def test_сводка_не_становится_делом_сессии():
    doing = _facts(BEFORE + _compact(T2))[1]
    assert "continued from a previous" not in doing, doing
    assert doing == "отчёт готов", doing


def test_граница_дальше_первого_хвоста():
    # Вложений за границей больше TAIL — граница находится вторым, широким
    # проходом, и его ответ про агента не теряется.
    pad = 64 * 1024
    n = CC["TAIL"] // pad + 2
    title, doing, turn_at, docs, entry, agent = _facts(
        BEFORE + _compact(T2, attachments=n, pad=pad))
    assert agent["state"] == "idle", agent
    assert agent.get("compactAt") == T2, agent
    assert "cacheAt" not in agent, agent
    assert turn_at == 0, turn_at


# ── После сжатия жизнь продолжилась ────────────────────────────────────────

def test_промпт_после_сжатия_начинает_ход():
    title, doing, turn_at, docs, entry, agent = _facts(
        BEFORE + _compact(T2) + [_human(T3, "дальше")])
    assert turn_at == T3, turn_at
    assert agent["state"] == "active", agent
    assert "compactAt" not in agent, agent
    assert "cacheAt" not in agent, agent


def test_ответ_после_сжатия_ставит_метку_кеша():
    agent = _facts(BEFORE + _compact(T2) + [_human(T3), _answer(T4)])[5]
    assert agent.get("cacheAt") == T4, agent
    assert agent["state"] == "review", agent
    assert "compactAt" not in agent, agent


def test_автосжатие_посреди_хода_ход_не_теряет():
    # Автосжатие приходит внутри хода: человек спросил до границы, агент
    # продолжает после неё. Ход начался с той реплики — граница его не рвёт.
    recs = [_human(HUMAN_AT), _answer(T1, stop="tool_use")] \
        + _compact(T2, trigger="auto") + [_answer(T3, stop="tool_use")]
    title, doing, turn_at, docs, entry, agent = _facts(recs)
    assert turn_at == HUMAN_AT, turn_at
    assert agent["state"] == "active", agent
    assert agent.get("cacheAt") == T3, agent
    assert "compactAt" not in agent, agent


def test_метка_кеша_за_границу_не_ходит():
    # После сжатия агент ещё не отвечал (только сайдчейн или ошибка) — метка
    # прошлого хода из-за границы не подхватывается.
    recs = BEFORE + _compact(T2, trigger="auto") + [
        {"type": "assistant", "isApiErrorMessage": True, "timestamp": _stamp(T3),
         "message": {"role": "assistant", "stop_reason": "stop_sequence",
                     "content": [{"type": "text", "text": "API Error"}]}}]
    agent = _facts(recs)[5]
    assert "cacheAt" not in agent, agent


def test_берётся_ближайшая_граница():
    recs = BEFORE + _compact(T2) + [_human(T3), _answer(T3 + 5)] + _compact(T4)
    agent = _facts(recs)[5]
    assert agent.get("compactAt") == T4, agent
    assert agent["state"] == "idle", agent


# ── Реплика человека ───────────────────────────────────────────────────────

def test_служебные_записи_сжатия_не_человек():
    h = CC["is_human_message"]
    for rec in _compact(T2):
        if rec.get("type") == "user":
            assert not h(rec), rec


def test_обычная_слэш_команда_человек():
    # Команду, на которую отвечает агент, человек посылает теми же тегами.
    rec = _human(T1, "<command-name>/do</command-name>\n<command-args>x</command-args>")
    assert CC["is_human_message"](rec)


# ── Обе дороги записи агента ───────────────────────────────────────────────

def _agent_of(tail, hook):
    with tempfile.TemporaryDirectory() as d:
        sid = "s1"
        if hook:
            with open(os.path.join(d, sid + ".state.json"), "w", encoding="utf-8") as fh:
                json.dump({"state": "idle", "event": "attention", "updated": 7}, fh)
        saved = CC["STATUS_DIR"]
        try:
            CC["STATUS_DIR"] = d
            return CC["agent_of"](sid, "", 0, tail, 100)
        finally:
            CC["STATUS_DIR"] = saved


def test_обе_дороги_несут_метку_сжатия():
    tail = {"state": "idle", "question": "", "compactAt": T2}
    hooked = _agent_of(tail, hook=True)
    bare = _agent_of(tail, hook=False)
    assert hooked.get("compactAt") == T2, hooked
    assert bare.get("compactAt") == T2 and bare["state"] == "idle", bare


def test_без_сжатия_ключа_нет():
    tail = {"state": "review", "question": ""}
    assert "compactAt" not in _agent_of(tail, hook=True)
    assert "compactAt" not in _agent_of(tail, hook=False)


def test_памятка_поднята():
    # Ключ памятки — mtime, а у сжатой и простаивающей сессии он больше не
    # сдвинется: без новой версии старый ответ остался бы в памятке навсегда.
    assert CC["FACTS_VERSION"] >= 11, CC["FACTS_VERSION"]


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("ok   %s" % t.__name__)
        except Exception as e:
            failed += 1
            print("FAIL %s: %r" % (t.__name__, e))
    print("%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)
