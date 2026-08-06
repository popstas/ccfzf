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


def _proc(pid, cwd="/p"):
    return {"pid": pid, "tty": "/dev/pts/1", "tmux": None, "cwd": cwd}


def test_reattribute_moves_the_process_to_the_id_being_written():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_B}, live
    assert UUID_A not in procs, procs
    assert procs[UUID_B]["pid"] == 42, procs


def test_reattribute_leaves_a_candidate_owned_by_another_process():
    now = time.time()
    live, procs, agents = {UUID_A, UUID_B}, {UUID_A: _proc(42), UUID_B: _proc(43)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_A, UUID_B}, live
    assert procs[UUID_A]["pid"] == 42, procs


def test_reattribute_ignores_a_candidate_whose_hook_went_quiet():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 3600}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_A}, live
    assert procs[UUID_A]["pid"] == 42, procs


def test_reattribute_carries_the_background_mark_along():
    now = time.time()
    live, procs = {UUID_A}, {UUID_A: _proc(42)}
    agents = {UUID_A: {"kind": "background", "parent": "p"}}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert agents == {UUID_B: {"kind": "background", "parent": "p"}}, agents


def test_reattribute_does_nothing_without_a_cwd():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42, cwd="")}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_A}, live


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
