"""Метка кеша промпта. Запуск: python3 tests/test_cache_at.py

Кеш промпта живёт час от последнего вызова API, и пикер показывает, сколько
от этого часа осталось. От ccfzf нужна только сама метка, `cacheAt`: время
последнего ответа агента, который этот кеш правда тронул.

Правила те же, что у виджета cache-timer в ccstatusline (запасная ветвь, по
транскрипту), — им уже доверяют в статуслайне, и два разных ответа на один
вопрос в двух местах экрана были бы поводом не верить обоим.
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
T1, T2, T3 = HUMAN_AT + 60, HUMAN_AT + 120, HUMAN_AT + 180


def _stamp(at):
    return datetime.datetime.fromtimestamp(
        at, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _human(at, text="сделай так"):
    return {"type": "user", "timestamp": _stamp(at),
            "message": {"role": "user", "content": text}}


def _answer(at, read=100, created=0, usage=True, **extra):
    """Ответ агента. `usage=False` — записи без поля вовсе, такие бывают."""
    message = {"role": "assistant", "stop_reason": "end_turn",
               "content": [{"type": "text", "text": "готово"}]}
    if usage:
        message["usage"] = {"input_tokens": 3, "output_tokens": 10,
                            "cache_read_input_tokens": read,
                            "cache_creation_input_tokens": created}
    rec = {"type": "assistant", "timestamp": _stamp(at), "message": message}
    rec.update(extra)
    return rec


def _agent(records):
    """Шестое значение tail_facts — словарь агента, где метка и живёт."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return CC["tail_facts"](path)[5]


# ── Что считается ответом ──────────────────────────────────────────────────

def test_метка_последнего_ответа_с_кешем():
    agent = _agent([_human(HUMAN_AT), _answer(T1, read=100)])
    assert agent.get("cacheAt") == T1, agent


def test_метка_целая():
    # Читатель сравнивает её с секундами своих часов, дробь там лишняя.
    agent = _agent([_human(HUMAN_AT), _answer(T1)])
    assert isinstance(agent["cacheAt"], int), agent


def test_запись_кеша_тоже_кеш():
    # Первый вызов после остывания кеш не читает, а пишет заново — и с этой
    # секунды час идёт сначала.
    agent = _agent([_human(HUMAN_AT), _answer(T1, read=0, created=5000)])
    assert agent.get("cacheAt") == T1, agent


def test_ошибка_api_и_ответ_без_кеша_пропускаются():
    # Ни ошибка API, ни ответ с нулями в обоих полях кеш не продлевают:
    # первая до модели не дошла, второй прошёл мимо кеша.
    agent = _agent([_human(HUMAN_AT),
                    _answer(T1, read=100),
                    _answer(T2, isApiErrorMessage=True),
                    _answer(T3, read=0, created=0)])
    assert agent.get("cacheAt") == T1, agent


def test_ответ_без_usage_засчитывается():
    agent = _agent([_human(HUMAN_AT), _answer(T1, usage=False)])
    assert agent.get("cacheAt") == T1, agent


def test_сайдчейн_не_считается():
    # У субагента свой контекст и свой кеш; час основной цепочки он не двигает.
    agent = _agent([_human(HUMAN_AT),
                    _answer(T1),
                    _answer(T2, isSidechain=True)])
    assert agent.get("cacheAt") == T1, agent


def test_ответ_без_времени_не_метка():
    # Без времени отсчитывать час не от чего; берётся предыдущий ответ.
    no_stamp = _answer(T2)
    del no_stamp["timestamp"]
    agent = _agent([_human(HUMAN_AT), _answer(T1), no_stamp])
    assert agent.get("cacheAt") == T1, agent


def test_испорченное_usage_не_роняет_разбор():
    # Транскрипт пишет чужая программа, и одно кривое поле стоит метки, а не
    # всей строки списка.
    bad = _answer(T2)
    bad["message"]["usage"] = {"cache_read_input_tokens": "много"}
    agent = _agent([_human(HUMAN_AT), _answer(T1), bad])
    assert agent.get("cacheAt") == T1, agent
    assert agent["state"] == "review", agent


# ── Когда ключа нет ────────────────────────────────────────────────────────

def test_нет_ответа_нет_ключа():
    # Не ноль: показанный ноль — «кеш остыл в 1970-м», и это единственное
    # число строки, которое врало бы. То же правило, что у contextPct.
    agent = _agent([_human(HUMAN_AT)])
    assert "cacheAt" not in agent, agent


def test_пустой_файл_нет_ключа():
    assert "cacheAt" not in _agent([]), _agent([])


def test_выход_из_цикла_не_ждёт_метку():
    # Человек только что написал, ответа ещё нет. Проход останавливается на
    # его реплике, как и прежде: дочитывать хвост ради метки прошлого хода
    # значило бы платить за неё у каждой работающей сессии, а таймер у
    # работающей пикер не показывает вовсе — кеш освежает каждый вызов.
    agent = _agent([_human(HUMAN_AT - 600, "раньше"),
                    _answer(HUMAN_AT - 300),
                    _human(HUMAN_AT, "теперь вот это")])
    assert agent["state"] == "active", agent
    assert "cacheAt" not in agent, agent


# ── Обе дороги записи агента ───────────────────────────────────────────────

def _agent_of(tail, hook):
    with tempfile.TemporaryDirectory() as d:
        sid = "s1"
        if hook:
            with open(os.path.join(d, sid + ".state.json"), "w", encoding="utf-8") as fh:
                json.dump({"state": "review", "updated": 7}, fh)
        saved = CC["STATUS_DIR"]
        try:
            CC["STATUS_DIR"] = d
            return CC["agent_of"](sid, "", 0, tail, 100)
        finally:
            CC["STATUS_DIR"] = saved


def test_обе_дороги():
    tail = {"state": "review", "question": "", "cacheAt": T1}
    hooked = _agent_of(tail, hook=True)
    bare = _agent_of(tail, hook=False)
    assert "source" not in hooked and bare["source"] == "transcript", (hooked, bare)
    assert hooked["cacheAt"] == T1, hooked
    assert bare["cacheAt"] == T1, bare


def test_обе_дороги_без_метки_без_ключа():
    tail = {"state": "review", "question": ""}
    assert "cacheAt" not in _agent_of(tail, hook=True)
    assert "cacheAt" not in _agent_of(tail, hook=False)


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
