"""Проекция сессии для ответа --state. Запуск: python3 tests/test_state_record.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

HISTORY = {
    "id": "a1", "cwd": "/p", "file": "/d/a1.jsonl", "projects": ["/p"],
    "prompts": 3, "title": "", "gist": "g", "doing": "d", "mtime": 100.5,
    "age": "1m", "live": False, "frozen": False, "activityAt": 99,
    "kind": "interactive", "parent": "", "pid": 0, "tty": "", "tmux": None,
    "zellij": None, "window": None, "windows": None, "shell": False, "shellCmd": "",
    "agent": {"state": "idle", "event": "", "message": "", "summary": "итог",
              "lastSummary": "прошлый", "prompt": "сделай", "question": "",
              "branch": "", "pr_url": "", "costUsd": 0, "contextPct": 12.0,
              "updated": 0, "turnAt": 0, "started": 0},
}


def test_history_row_keeps_only_what_the_picker_reads():
    got = CC["state_record"](HISTORY)
    assert got == {
        "id": "a1", "cwd": "/p", "prompts": 3, "title": "", "mtime": 100.5,
        "live": False, "kind": "interactive",
        "agent": {"state": "idle", "summary": "итог", "prompt": "сделай",
                  "contextPct": 12.0, "updated": 0},
    }, got


def test_the_source_row_is_not_touched():
    # Те же словари уходят в dump_record: проекция не должна их портить.
    before = {k: (dict(v) if isinstance(v, dict) else v) for k, v in HISTORY.items()}
    CC["state_record"](HISTORY)
    assert HISTORY == before
    assert set(CC["dump_record"](HISTORY)) == set(CC["DUMP_KEEP"])


def test_a_background_command_survives_only_when_it_is_running():
    live = {**HISTORY, "live": True, "pid": 7, "shell": True, "shellCmd": "sleep 300"}
    got = CC["state_record"](live)
    assert got["shell"] is True and got["shellCmd"] == "sleep 300", got
    got = CC["state_record"]({**live, "shell": False, "shellCmd": ""})
    assert "shell" not in got and "shellCmd" not in got, got


def test_last_summary_stays_when_summary_is_blank():
    # sessionDescription читает lastSummary ровно тогда, когда summary пуст
    # после trim — у работающей сессии.
    got = CC["state_agent"]({"summary": "  ", "lastSummary": "прошлый", "updated": 5})
    assert got == {"summary": "  ", "lastSummary": "прошлый", "updated": 5}, got
    got = CC["state_agent"]({"summary": "", "lastSummary": "прошлый", "updated": 5})
    assert got == {"lastSummary": "прошлый", "updated": 5}, got


def test_a_live_row_keeps_its_pid_even_at_zero():
    # validateState: у live-сессии pid обязан быть числом. Живая по одному
    # открытому окну своего процесса здесь не имеет — pid 0.
    row = dict(HISTORY, live=True, pid=0,
               window={"host": "nb", "title": "t"}, windows=[{"host": "nb", "title": "t"}])
    got = CC["state_record"](row)
    assert got["pid"] == 0 and got["live"] is True, got
    assert got["window"] == {"host": "nb", "title": "t"}, got
    assert got["windows"] == [{"host": "nb", "title": "t"}], got


def test_missing_agent_record_drops_the_key():
    got = CC["state_record"](dict(HISTORY, agent=None))
    assert "agent" not in got, got


def test_non_empty_optional_fields_survive():
    row = dict(HISTORY, frozen=True, parent="p0", tty="pts/1", tmux="w:1",
               zellij="home", pid=42, live=True, todo=[{"done": 1, "todo": 2}],
               comment="к", head="h", headId="hid", entrypoint="cli",
               spec="docs/s.md", plan="docs/p.md")
    got = CC["state_record"](row)
    for key in ("frozen", "parent", "tty", "tmux", "zellij", "pid", "todo",
                "comment", "head", "headId", "entrypoint", "spec", "plan"):
        assert got[key] == row[key], (key, got)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
