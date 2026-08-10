"""Срез сессий для дампа. Запуск: python3 tests/test_pick_files.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"
C = "cccccccc-1111-2222-3333-444444444444"


def files(*ids):
    # mtime убывает по порядку, как их отдаёт сам ccfzf после сортировки.
    return [("/d/%s.jsonl" % sid, 1000.0 - i, "/p") for i, sid in enumerate(ids)]


def test_sid_of_strips_the_jsonl_suffix():
    assert CC["sid_of"]("/d/-p/%s.jsonl" % A) == A


def test_within_the_limit_nothing_is_added():
    got = CC["pick_files"](files(A, B), 5, {B})
    assert [f[0] for f in got] == ["/d/%s.jsonl" % A, "/d/%s.jsonl" % B], got


def test_beyond_the_limit_the_tail_is_cut():
    got = CC["pick_files"](files(A, B, C), 1, set())
    assert [CC["sid_of"](f[0]) for f in got] == [A], got


def test_a_session_worth_keeping_survives_the_cut():
    # Ради этого случая объединение и существует: окно открыто, а транскрипт
    # не трогали дольше среза. Без неё читателю дампа нечем понять, чьё окно.
    got = CC["pick_files"](files(A, B, C), 1, {C})
    assert [CC["sid_of"](f[0]) for f in got] == [A, C], got


def test_order_stays_by_falling_mtime():
    # Добавка всегда старше головы, поэтому сортировать заново незачем —
    # но если срез когда-нибудь начнут делать не по отсортированному списку,
    # порядок разъедется молча.
    got = CC["pick_files"](files(A, B, C), 2, {C})
    assert [f[1] for f in got] == [1000.0, 999.0, 998.0], got


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
