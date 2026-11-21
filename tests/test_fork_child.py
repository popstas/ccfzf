"""Форк-ребёнок head: `claude-wt-new` с файлом `<sid>.fork` запускает
`claude -n <имя> --session-id <свой> --resume <headId> --fork-session`.

Тот же набор флагов, что у фонового агента (`--session-id … --fork-session
--resume <родитель>.jsonl`), и проверяется здесь, что агрегатор не путает их:
фоновым агента делает родословная — pty host демона над процессом, — а не
argv. Форк-ребёнок, поднятый из шелла окна, остаётся обычной сессией со своим
id, а head сохраняет свой процесс и свою строку.

Таблица процессов подставная: обход /proc заменён словарём, хуки и реестр —
пустотой, чтобы ответ не зависел от машины.
"""
import harness

CC = harness.load()

HEAD = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
CHILD = "11111111-2222-4333-8444-555555555555"
BG = "99999999-bbbb-4ccc-8ddd-eeeeeeeeeeee"
CLAUDE = "/home/u/.local/bin/claude"


def run(table):
    """running_sessions() над таблицей {pid: (ppid, argv)}."""
    names = ("all_pids", "proc_args", "parent_pid", "proc_cwd", "proc_tty",
             "proc_tmux", "proc_zellij", "proc_created", "hook_stamps",
             "pid_owners", "registry_by_pid", "WINDOWS")
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
        CC["hook_stamps"] = lambda: {}
        CC["pid_owners"] = lambda: {}
        CC["registry_by_pid"] = lambda path=None: {}
        live, agents, procs, _ = CC["running_sessions"]()
    finally:
        CC.update(saved)
    return live, agents, procs


def table():
    return {
        # head в своём окне
        "100": ("10", [CLAUDE, "-n", "x-head", "--session-id", HEAD]),
        # шелл окна ребёнка, его поднял claude-wt-new
        "200": ("20", ["/bin/zsh", "-ic", "cd -- /p && claude …"]),
        "201": ("200", [CLAUDE, "-n", "└x", "--session-id", CHILD,
                        "--resume", HEAD, "--fork-session", "--", "вступление"]),
    }


def test_a_fork_child_is_an_interactive_session_of_its_own():
    live, agents, procs = run(table())
    assert live == {HEAD, CHILD}, live
    assert CHILD not in agents, agents
    assert procs[CHILD]["pid"] == 201, procs


def test_the_head_keeps_its_own_process():
    live, agents, procs = run(table())
    assert procs[HEAD]["pid"] == 100, procs
    assert HEAD not in agents, agents


def test_a_background_agent_is_still_recognised_by_its_host():
    """Регрессия: правка про форк не должна снять пометку с настоящего
    фонового агента — у него над процессом pty host демона."""
    t = table()
    t["300"] = ("30", [CLAUDE, "daemon"])
    t["301"] = ("300", [CLAUDE, "bg-pty-host"])
    t["302"] = ("301", [CLAUDE, "--session-id", BG, "--fork-session",
                        "--resume", "/home/u/.claude/projects/-p/%s.jsonl" % HEAD])
    live, agents, procs = run(t)
    assert agents.get(BG) == {"kind": "background", "parent": HEAD}, agents
    assert CHILD not in agents, agents
    assert procs[HEAD]["pid"] == 100 and procs[CHILD]["pid"] == 201, procs


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
