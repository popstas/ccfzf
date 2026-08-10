"""Сквозной прогон режима --state поверх подставного HOME.

Единственный тест, который проверяет саму проводку веток режимов: harness
исполняет python-блок с argv из одного элемента, и ни одна ветка там не
срабатывает — значит соединение функций между собой ловится только так.

Запуск: python3 tests/test_state_mode.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ccfzf")

A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"


def build_home(tmp, sids):
    """~/.claude/projects/<mangled>/<sid>.jsonl, по строке на сессию.

    cwd берётся из первых строк файла (dir_cwd), заголовок — из хвоста
    (tail_facts), поэтому обе записи кладутся сразу.
    """
    cwd = os.path.join(tmp, "proj")
    os.makedirs(cwd, exist_ok=True)
    d = os.path.join(tmp, ".claude", "projects", re.sub(r"[^a-zA-Z0-9]", "-", cwd))
    os.makedirs(d, exist_ok=True)
    for i, sid in enumerate(sids):
        path = os.path.join(d, sid + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"cwd": cwd, "type": "user",
                                 "message": {"role": "user", "content": "hello %d" % i}}) + "\n")
            fh.write(json.dumps({"type": "custom-title", "customTitle": "t%d" % i}) + "\n")
        os.utime(path, (2000 + i, 2000 + i))
    return cwd


def run_state(tmp, dump_path, *extra):
    env = dict(os.environ)
    env.update({
        "HOME": tmp,
        "FZF_MARKS_FILE": os.path.join(tmp, "no-marks"),
        "CCFZF_SESSIONS_FILE": dump_path,
        "CCFZF_PROJECTS_FILE": "",
        "CCFZF_WINDOWS_FILE": "",
        "CCFZF_FACTS_FILE": os.path.join(tmp, "facts.json"),
        "XDG_CACHE_HOME": os.path.join(tmp, "cache"),
    })
    r = subprocess.run(["bash", SRC, "--state", *extra],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return json.loads(r.stdout)


def test_state_lists_the_fixture_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        assert sorted(s["id"] for s in out["sessions"]) == sorted([A, B]), out["sessions"]


def test_limit_cuts_the_list():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        out = run_state(tmp, os.path.join(tmp, "dump.json"), "--limit", "1")
        assert len(out["sessions"]) == 1, out["sessions"]


def test_activity_at_comes_from_the_hook_file():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        hooks = os.path.join(tmp, ".claude", "claude-wt")
        os.makedirs(hooks)
        state_file = os.path.join(hooks, A + ".state.json")
        with open(state_file, "w", encoding="utf-8") as fh:
            fh.write("{}")
        os.utime(state_file, (1234567890, 1234567890))
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        by_id = {s["id"]: s for s in out["sessions"]}
        assert by_id[A]["activityAt"] == 1234567890, by_id[A]
        # Хук про неё не писал — ноль, ровно то же, что сегодня возвращает
        # сетевой вызов у читателя при отсутствии файла.
        assert by_id[B]["activityAt"] == 0, by_id[B]


if __name__ == "__main__":
    fails = 0
    names = [n for n in globals() if n.startswith("test_")]
    for name in sorted(names):
        try:
            globals()[name]()
            print("ok   " + name)
        except AssertionError as e:
            fails += 1
            print("FAIL " + name + ": " + str(e))
    print("%d/%d passed" % (len(names) - fails, len(names)))
    sys.exit(1 if fails else 0)
