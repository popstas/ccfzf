"""Свободное имя новой сессии. Запуск: python3 tests/test_session_name.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()


def test_free_name_is_taken_as_is():
    assert CC["free_session_name"]("api", set()) == "api"
    assert CC["free_session_name"]("api", {"other"}) == "api"


def test_taken_name_gets_a_suffix():
    assert CC["free_session_name"]("api", {"api"}) == "api-2"
    assert CC["free_session_name"]("api", {"api", "api-2"}) == "api-3"


def test_the_gap_is_filled_not_skipped():
    # Номер — это первое свободное имя, а не счётчик сессий.
    assert CC["free_session_name"]("api", {"api", "api-3"}) == "api-2"


def test_numbering_starts_at_two():
    # Первая сессия называется просто именем каталога, и `api-1` рядом с ней
    # читался бы как ещё одна из многих. То же правило в ccfzf-picker.
    assert CC["free_session_name"]("api", {"api"}) != "api-1"


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
