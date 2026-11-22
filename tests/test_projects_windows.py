"""Файл оконного трекера в интерактивном списке. Запуск: python3 tests/test_projects_windows.py

Режимы `--state` и `--dump` считали живой сессию с открытым окном, а режим
`projects` — нет: он судил по одному `running_sessions()`. Его индекс читают
`sessions` и `newname`, так что одна и та же сессия была живой в пикере и
мёртвой в списке ccfzf. Правило одно на все представления: открытое окно —
наблюдение, а не догадка.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

UUID_W = "cccccccc-1111-2222-3333-444444444444"


def _run_projects(home, windows_file, windows_dir):
    index = os.path.join(home, "index.json")
    saved = os.environ.get("HOME")
    os.environ["HOME"] = home
    try:
        harness.run(["projects", os.path.join(home, "marks"), index,
                     windows_file, windows_dir])
    finally:
        os.environ["HOME"] = saved
    with open(index, encoding="utf-8") as fh:
        return json.load(fh)


def test_a_session_with_an_open_window_is_live_in_the_projects_index():
    with tempfile.TemporaryDirectory() as home:
        wdir = os.path.join(home, "windows")
        os.makedirs(wdir)
        with open(os.path.join(wdir, "pc.json"), "w", encoding="utf-8") as fh:
            json.dump({"generated": time.time(), "host": "pc", "pid": 42,
                       "windows": {UUID_W: {"title": "w", "lastSeen": time.time()}}}, fh)
        index = _run_projects(home, "", wdir)
        assert UUID_W in index["live"], index["live"]


def test_without_a_windows_file_the_index_is_unchanged():
    # Трекера нет — ни одной лишней живой сессии, и режим не падает.
    with tempfile.TemporaryDirectory() as home:
        index = _run_projects(home, os.path.join(home, "none.json"),
                              os.path.join(home, "no-such-dir"))
        assert UUID_W not in index["live"], index["live"]


def test_a_stale_windows_file_revives_nobody():
    # Протухший файл трекера (WINDOWS_TTL) отбрасывает сама read_windows —
    # здесь проверяется, что `projects` идёт той же дорогой, а не своей.
    with tempfile.TemporaryDirectory() as home:
        wdir = os.path.join(home, "windows")
        os.makedirs(wdir)
        with open(os.path.join(wdir, "pc.json"), "w", encoding="utf-8") as fh:
            json.dump({"generated": time.time() - 86400, "host": "pc", "pid": 42,
                       "windows": {UUID_W: {"title": "w"}}}, fh)
        index = _run_projects(home, "", wdir)
        assert UUID_W not in index["live"], index["live"]


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("ok  ", t.__name__)
        except Exception as e:  # noqa: BLE001 — отчёт о любом падении
            failed += 1
            print("FAIL", t.__name__, repr(e))
    print("%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)
