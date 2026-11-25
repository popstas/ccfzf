"""Закрытая через `claude-wt session close` сессия не жива по отметке хука.

`live_by_hook` раздаёт живость сессии без процесса, если её хук писал не
дольше HOOK_LIVE_TTL назад. Закрытый ребёнок поэтому ещё до двух минут после
выхода стоял в `ccfzf --state` с `live: true` и без pid, и `claude-wt waiting`
показывал его среди ждущих (2026-11-25, .wait-hook-fix a1c091cc).

`session close` кладёт `<id>.closed.json` рядом с `<id>.state.json`. Отметка
хука не старше отметки закрытия — уже не довод о жизни. Хук, записавший
что-то после закрытия (сессию подняли снова), и живой процесс — по-прежнему
довод.
"""
import os
import tempfile
import time

import harness

CC = harness.load()

A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
B = "11111111-2222-4333-8444-555555555555"
CLAUDE = "/home/u/.local/bin/claude"


def touch(d, name, at):
    path = os.path.join(d, name)
    with open(path, "w") as fh:
        fh.write("{}")
    os.utime(path, (at, at))


def test_closed_marks_reads_mtime_of_closed_files_only():
    with tempfile.TemporaryDirectory() as d:
        touch(d, A + ".closed.json", 1000)
        touch(d, B + ".state.json", 2000)
        touch(d, "not-a-uuid.closed.json", 3000)
        assert CC["closed_marks"](d) == {A: 1000}


def test_closed_marks_survives_a_missing_directory():
    assert CC["closed_marks"]("/nonexistent-dir-for-tests") == {}


def run(table, stamps, closed):
    """running_sessions() над подставной таблицей процессов, отметками и закрытиями."""
    names = ("all_pids", "proc_args", "parent_pid", "proc_cwd", "proc_tty",
             "proc_tmux", "proc_zellij", "proc_created", "hook_stamps",
             "closed_marks", "pid_owners", "registry_by_pid", "WINDOWS")
    saved = {n: CC[n] for n in names}

    def args(pid):
        if str(pid) not in table:
            raise OSError(pid)
        return table[str(pid)][1]

    try:
        CC["WINDOWS"] = False
        CC["all_pids"] = lambda: list(table)
        CC["proc_args"] = args
        CC["parent_pid"] = lambda pid: table[str(pid)][0] if str(pid) in table else ""
        CC["proc_cwd"] = lambda pid: "/p/" + str(pid)
        CC["proc_tty"] = lambda pid: ""
        CC["proc_tmux"] = lambda pid: None
        CC["proc_zellij"] = lambda pid: None
        CC["proc_created"] = lambda pid: 0
        CC["hook_stamps"] = lambda: dict(stamps)
        CC["closed_marks"] = lambda: dict(closed)
        CC["pid_owners"] = lambda: {}
        CC["registry_by_pid"] = lambda path=None: {}
        live, _, procs, _ = CC["running_sessions"]()
    finally:
        CC.update(saved)
    return live, procs


def test_a_fresh_hook_without_a_close_still_means_alive():
    now = time.time()
    live, _ = run({}, {A: now - 10}, {})
    assert live == {A}, live


def test_a_closed_session_is_not_alive_by_its_last_hook():
    now = time.time()
    live, _ = run({}, {A: now - 60}, {A: now - 5})
    assert live == set(), live


def test_a_hook_written_after_the_close_brings_it_back():
    # Сессию подняли снова (`claude --resume`), и её хук уже пишет.
    now = time.time()
    live, _ = run({}, {A: now - 2}, {A: now - 30})
    assert live == {A}, live


def test_a_running_process_wins_over_the_close_mark():
    now = time.time()
    table = {"100": ("10", [CLAUDE, "--session-id", A])}
    live, procs = run(table, {A: now - 60}, {A: now - 5})
    assert live == {A}, live
    assert procs[A]["pid"] == 100, procs


def test_a_closed_session_is_no_candidate_for_a_new_process_nearby():
    # Новый claude без аргументов в каталоге закрытой сессии: свежая отметка
    # закрытой не должна притянуть его к её id (reattribute).
    now = time.time()
    table = {"100": ("10", [CLAUDE])}
    live, procs = run(table, {A: now - 60}, {A: now - 5})
    assert A not in live, live
