"""Проекты в ответе --state. Запуск: python3 tests/test_state_projects.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()


def test_project_rows_shape_is_what_state_promises():
    # Ответ --state собирается проекцией project_rows, и имена полей в нём
    # свои: `sessions` вместо `n`. Тест сторожит саму проекцию — если у
    # project_rows переименуют ключ, здесь станет KeyError, а не тихо пустое
    # поле у читателя на другой машине.
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/a.jsonl", 1000.0)]}]
    rows = CC["project_rows"](dirs, set(), {})
    got = [{"path": r["path"], "name": r["name"], "mark": r["mark"],
            "sessions": r["n"], "live": r["live"], "mtime": r["mtime"]}
           for r in rows]
    assert got == [{"path": "/p/one", "name": "one", "mark": False,
                    "sessions": 1, "live": 0, "mtime": 1000.0}], got


def test_a_marked_project_without_sessions_is_still_listed():
    # Ради этого случая поле и добавляется: проект, где ни разу не запускали
    # claude, приходит только из marks, и по cwd сессий его не восстановить.
    rows = CC["project_rows"]([], set(), {"/p/empty": "empty"})
    assert [r["path"] for r in rows] == ["/p/empty"], rows
    assert rows[0]["n"] == 0 and rows[0]["live"] == 0, rows


def test_live_sessions_are_counted_per_project():
    sid = "aaaaaaaa-1111-2222-3333-444444444444"
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/%s.jsonl" % sid, 1000.0)]}]
    rows = CC["project_rows"](dirs, {sid}, {})
    assert rows[0]["live"] == 1, rows


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
