"""Объявленное ожидание (`claude-wt wait set`) в ответе --state.

Запуск: python3 tests/test_wait.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from test_state_mode import A, B, build_home, run_state

CC = harness.load()


def _write(d, name, obj):
    with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
        fh.write(obj if isinstance(obj, str) else json.dumps(obj))


def test_waits_all_keeps_only_valid_records_and_known_fields():
    with tempfile.TemporaryDirectory() as d:
        _write(d, A + ".wait.json", {"kind": "decision", "ask": " схема A или B? ",
                                     "clearBy": "ответ в чате", "setAt": 100, "extra": 1})
        _write(d, B + ".wait.json", {"kind": "nonsense", "ask": "x"})
        _write(d, "cccccccc-1111-2222-3333-444444444444.wait.json", {"kind": "review", "ask": "  "})
        _write(d, "dddddddd-1111-2222-3333-444444444444.wait.json", "{broken")
        _write(d, "not-a-uuid.wait.json", {"kind": "review", "ask": "x"})
        _write(d, A + ".state.json", {"state": "idle"})
        got = CC["waits_all"](d)
        assert got == {A: {"kind": "decision", "ask": "схема A или B?",
                           "clearBy": "ответ в чате", "setAt": 100}}, got


def test_waits_all_without_the_directory_is_empty():
    assert CC["waits_all"]("/nonexistent/claude-wt") == {}


def test_state_carries_the_declared_wait_of_a_session():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        hooks = os.path.join(tmp, ".claude", "claude-wt")
        os.makedirs(hooks)
        _write(hooks, A + ".wait.json", {"kind": "external", "ask": "ждём ответа Саши", "setAt": 5})
        dump = os.path.join(tmp, "dump.json")
        out = run_state(tmp, dump)
        by_id = {s["id"]: s for s in out["sessions"]}
        assert by_id[A]["wait"] == {"kind": "external", "ask": "ждём ответа Саши", "setAt": 5}, by_id[A]
        assert "wait" not in by_id[B], by_id[B]
        with open(dump, encoding="utf-8") as fh:
            assert all("wait" not in s for s in json.load(fh)["sessions"]), "в дамп не едет"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
