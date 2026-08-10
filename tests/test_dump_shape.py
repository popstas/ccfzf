"""Форма дампа для оконного трекера. Запуск: python3 tests/test_dump_shape.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

FULL = {
    "id": "a1", "cwd": "/p", "file": "/d/a1.jsonl", "projects": ["p"],
    "title": "t", "gist": "g", "doing": "d", "mtime": 100.0, "age": "1m",
    "live": True, "frozen": False, "kind": "interactive", "parent": "",
    "activityAt": 99, "pid": 7, "tty": "pts/0", "tmux": None, "agent": {},
    "window": None,
}


def test_dump_keeps_exactly_what_the_reader_uses():
    # Читателей у файла два, оба в windows11-manager/src/claude-wt/sessions.js.
    # Список сверен по ним; лишнее поле здесь — это байты, которые оба процесса
    # разбирают четырежды в минуту и выбрасывают.
    assert CC["DUMP_KEEP"] == (
        "id", "title", "cwd", "live", "mtime", "kind", "parent", "activityAt",
    ), CC["DUMP_KEEP"]


def test_dump_record_drops_everything_else():
    got = CC["dump_record"](FULL)
    assert set(got) == set(CC["DUMP_KEEP"]), got
    assert got["id"] == "a1" and got["activityAt"] == 99, got


def test_dump_record_shouts_when_a_field_is_missing():
    # Проекция — единственное место, где сходятся два писателя одного файла.
    # Молча отдать читателю запись без title значило бы стереть ему индекс.
    try:
        CC["dump_record"]({"id": "a1"})
    except KeyError:
        return
    raise AssertionError("ожидался KeyError на неполной записи")


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
