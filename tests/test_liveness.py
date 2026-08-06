"""Тесты живости сессий. Запуск: python3 tests/test_liveness.py"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "bbbbbbbb-1111-2222-3333-444444444444"


def test_hook_stamps_reads_mtime_of_state_files():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, UUID_A + ".state.json")
        with open(path, "w") as fh:
            fh.write("{}")
        os.utime(path, (1000, 1000))
        assert CC["hook_stamps"](d) == {UUID_A: 1000}


def test_hook_stamps_ignores_everything_but_state_files():
    with tempfile.TemporaryDirectory() as d:
        for name in (UUID_A + ".status.json", UUID_A + ".meta.json",
                     "not-a-uuid.state.json", "README"):
            with open(os.path.join(d, name), "w") as fh:
                fh.write("{}")
        assert CC["hook_stamps"](d) == {}


def test_hook_stamps_survives_a_missing_directory():
    assert CC["hook_stamps"]("/nonexistent-dir-for-tests") == {}


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("ok   %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (t.__name__, e))
    print("%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)
