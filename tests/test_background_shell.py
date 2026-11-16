"""Фоновая команда при законченном ходе — статус `shell` агента.

Запуск: python3 tests/test_background_shell.py
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

# Ровно такой argv был у typesafe-categories 2026-11-16, без простыни export.
WRAPPED = [
    "/bin/zsh", "-c",
    "source /home/u/.claude/shell-snapshots/snapshot-zsh-1794850592144-ajywui.sh "
    "2>/dev/null || true && export X='1'\n: && \\builtin setopt NO_EXTENDED_GLOB "
    "2>/dev/null || true && { \\builtin unalias -- 'which'; } >/dev/null 2>&1 || true "
    "&& eval 'until ! pgrep -f \"telegram-download-chat \" >/dev/null; do sleep 5; done; "
    "echo done' < /dev/null",
]


# ── Текст команды из argv ──────────────────────────────────────────────────


def test_the_command_is_the_last_eval():
    got = CC["shell_command"](WRAPPED)
    assert got.startswith('until ! pgrep -f "telegram-download-chat " >/dev/null;'), got
    assert len(got) == CC["SHELL_CMD_MAX"] and got.endswith("…"), got


def test_a_quote_inside_the_command_is_unescaped():
    args = ["/bin/bash", "-c", "source ~/.claude/shell-snapshots/snapshot-bash-1.sh && "
            "eval 'echo '\\''hi'\\''   there' < /dev/null"]
    assert CC["shell_command"](args) == "echo 'hi' there"


def test_a_process_without_the_snapshot_is_not_ours():
    assert CC["shell_command"](["/bin/zsh", "-c", "eval 'sleep 5'"]) is None
    assert CC["shell_command"](["npm", "exec", "chrome-devtools-mcp"]) is None


def test_ours_without_eval_reads_as_unknown_text():
    args = ["/bin/zsh", "-c", "source ~/.claude/shell-snapshots/snapshot-zsh-1.sh"]
    assert CC["shell_command"](args) == ""


# ── Решение ────────────────────────────────────────────────────────────────


def _shells(*cmds):
    calls = []

    def ask(pid):
        calls.append(pid)
        return list(cmds)
    return ask, calls


def test_the_registry_says_shell():
    ask, _ = _shells("sleep 300")
    got = CC["background_shell"]({"pid": 5, "status": "shell"}, "idle", ask)
    assert got == (True, "sleep 300"), got


def test_shell_from_the_registry_needs_no_child_to_be_seen():
    # Windows: детей спросить нечем, а реестр отвечает и без них.
    ask, _ = _shells()
    assert CC["background_shell"]({"pid": 5, "status": "shell"}, "", ask) == (True, "")


def test_any_other_status_is_a_no_without_asking_children():
    # `busy` — посреди хода у обычного Bash такой же ребёнок; `idle` при живом
    # ребёнке — команда уже кончилась и процесс доживает.
    for status in ("busy", "idle", "waiting"):
        ask, calls = _shells("sleep 300")
        assert CC["background_shell"]({"pid": 5, "status": status}, "idle", ask) == (False, "")
        assert calls == [], (status, calls)


def test_without_a_status_a_child_counts_only_when_the_turn_is_over():
    for state in ("idle", "review"):
        ask, _ = _shells("sleep 300")
        assert CC["background_shell"]({"pid": 5, "status": None}, state, ask) == (True, "sleep 300")
    for state in ("active", "question", "unknown", ""):
        ask, calls = _shells("sleep 300")
        assert CC["background_shell"]({"pid": 5, "status": None}, state, ask) == (False, "")
        assert calls == [], (state, calls)


def test_without_a_status_and_without_a_child_it_is_a_no():
    ask, _ = _shells()
    assert CC["background_shell"]({"pid": 5, "status": None}, "idle", ask) == (False, "")


def test_a_session_without_a_process_is_a_no():
    ask, calls = _shells("sleep 300")
    assert CC["background_shell"](None, "idle", ask) == (False, "")
    assert CC["background_shell"]({"pid": 0, "status": "shell"}, "idle", ask) == (False, "")
    assert calls == []


# ── Дети процесса ─────────────────────────────────────────────────────────


def test_children_are_found_on_this_machine():
    if sys.platform != "linux":
        return
    child = subprocess.Popen(
        ["sh", "-c", ": /x/.claude/shell-snapshots/snapshot-sh-1.sh && eval 'sleep 30' ; sleep 30"])
    try:
        for _ in range(50):
            got = CC["agent_shells"](os.getpid())
            if got:
                break
            time.sleep(0.02)
        assert got == ["sleep 30"], got
    finally:
        child.kill()
        child.wait()


def test_children_on_a_mac_come_from_the_ps_table():
    saved = CC["DARWIN"], CC["ps_table"], CC["proc_args"]
    try:
        CC["DARWIN"] = True
        CC["ps_table"] = lambda: {"11": {"ppid": "7"}, "12": {"ppid": "8"}, "13": {"ppid": "7"}}
        argv = {"11": WRAPPED, "12": WRAPPED, "13": ["node", "mcp"]}
        CC["proc_args"] = lambda pid: argv[pid]
        got = CC["agent_shells"](7)
        assert len(got) == 1 and got[0].startswith("until ! pgrep"), got
    finally:
        CC["DARWIN"], CC["ps_table"], CC["proc_args"] = saved


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, exc)
    sys.exit(1 if fails else 0)
