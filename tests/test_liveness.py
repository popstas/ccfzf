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


def test_live_by_hook_adds_a_working_session_no_process_names():
    now = time.time()
    live = set()
    CC["live_by_hook"](live, {UUID_A: now - 10}, now)
    assert live == {UUID_A}, live


def test_live_by_hook_keeps_a_running_session_whose_hook_is_silent():
    now = time.time()
    live = {UUID_B}
    CC["live_by_hook"](live, {UUID_B: now - 86400}, now)
    assert live == {UUID_B}, live


def test_live_by_hook_does_not_resurrect_a_session_that_went_quiet():
    now = time.time()
    live = set()
    CC["live_by_hook"](live, {UUID_A: now - 3600}, now)
    assert live == set(), live


def test_live_by_hook_does_not_resurrect_an_id_reattribute_just_vacated():
    # Ротация A->B тридцать секунд назад: без skip live_by_hook добавил бы
    # A обратно по его ещё не остывшей отметке — ровно та дублирующая
    # строка, ради ухода от которой существует reattribute().
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 30, UUID_B: now - 5}
    moved = CC["reattribute"](live, procs, agents, stamps, now,
                              ids_in=lambda cwd: [UUID_A, UUID_B])
    CC["live_by_hook"](live, stamps, now, skip=moved)
    assert live == {UUID_B}, live


def test_reattribute_does_not_let_a_second_process_reclaim_a_vacated_id():
    # UUID_A переезжает на UUID_B (его хук свежее) и освобождает UUID_A.
    # UUID_IDLE — второй, простаивающий процесс в том же каталоге: его
    # собственная отметка старая, а у освобождённого UUID_A она ещё не
    # остыла, так что без защиты он выглядел бы для UUID_IDLE лучшим
    # кандидатом — хотя в этот транскрипт больше никто не пишет.
    UUID_IDLE = "cccccccc-1111-2222-3333-444444444444"
    now = time.time()
    live = {UUID_A, UUID_IDLE}
    procs = {UUID_A: _proc(42), UUID_IDLE: _proc(43)}
    agents = {}
    stamps = {UUID_A: now - 25, UUID_B: now - 5, UUID_IDLE: now - 3600}

    def ids_in(cwd):
        return [UUID_A, UUID_B, UUID_IDLE]

    CC["reattribute"](live, procs, agents, stamps, now, ids_in=ids_in)
    assert procs.get(UUID_A) is None, procs
    assert procs[UUID_IDLE]["pid"] == 43, procs
    assert UUID_A not in live, live


def test_reattribute_returns_the_ids_it_vacated():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    moved = CC["reattribute"](live, procs, agents, stamps, now,
                              ids_in=lambda cwd: [UUID_A, UUID_B])
    assert moved == {UUID_A}, moved


def test_reattribute_returns_an_empty_set_when_nothing_moves():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 3600}
    moved = CC["reattribute"](live, procs, agents, stamps, now,
                              ids_in=lambda cwd: [UUID_A, UUID_B])
    assert moved == set(), moved


def test_hook_stamps_reads_both_of_two_state_files():
    with tempfile.TemporaryDirectory() as d:
        path_a = os.path.join(d, UUID_A + ".state.json")
        path_b = os.path.join(d, UUID_B + ".state.json")
        with open(path_a, "w") as fh:
            fh.write("{}")
        with open(path_b, "w") as fh:
            fh.write("{}")
        os.utime(path_a, (1000, 1000))
        os.utime(path_b, (2000, 2000))
        assert CC["hook_stamps"](d) == {UUID_A: 1000, UUID_B: 2000}


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
