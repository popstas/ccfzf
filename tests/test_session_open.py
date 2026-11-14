"""`ccfzf --session <id>`: чем открывается живая сессия. Запуск: python3 tests/test_session_open.py

Раньше ветка знала только транскрипт и всегда делала `claude --resume`.
Живой сессии в tmux это поднимало второй процесс рядом с первым, а живая без
единого запроса (транскрипта ещё нет) отвечала «not found» — так 2026-11-14
Enter пикера на такой сессии открыл терминал с ошибкой.

Тесты двух слоёв. `session_target` — чистая функция, ей хватает словарей.
Ветка bash проверяется прогоном самого скрипта: живой «агент» — настоящий
процесс с argv `claude … --session-id <id>` (так его находит обход /proc), а
tmux, reptyr, pgrep и claude — заглушки в PATH, пишущие свои аргументы в журнал.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccfzf")
SID = "abababab-1111-2222-3333-444444444444"


# ── session_target ──────────────────────────────────────────────────────────

def target(live, procs, registry=()):
    return CC["session_target"](SID, set(live), procs, list(registry))


def test_live_in_tmux_attaches():
    t = target([SID], {SID: {"pid": 7, "tmux": "work:1.0", "zellij": None, "cwd": "/p"}})
    assert t["how"] == "tmux" and t["tmux"] == "work:1.0", t


def test_live_in_zellij_attaches():
    t = target([SID], {SID: {"pid": 7, "tmux": None, "zellij": "home", "cwd": "/p"}})
    assert t["how"] == "zellij" and t["zellij"] == "home", t


def test_live_without_multiplexer_is_stolen():
    # Сирота на чужом pty: окно закрыли, держатель (sshd) жив.
    t = target([SID], {SID: {"pid": 7, "tmux": None, "zellij": None, "cwd": "/p"}})
    assert t["how"] == "reptyr" and t["pid"] == 7, t


def test_dead_session_resumes():
    t = target([], {SID: {"pid": 7, "tmux": "work:1.0", "cwd": "/p"}})
    assert t["how"] == "resume" and t["pid"] == 0 and t["tmux"] == "", t


def test_live_without_pid_resumes():
    # Живой сессию мог назвать и хук, а процесс так и не нашёлся: переносить
    # нечего.
    t = target([SID], {})
    assert t["how"] == "resume", t


def test_cwd_comes_from_the_registry_first():
    # У сессии без единого запроса транскрипта нет, и каталог знает только
    # реестр агента (`~/.claude/sessions/<pid>.json`).
    t = target([SID], {SID: {"pid": 7, "tmux": None, "zellij": None, "cwd": "/proc-cwd"}},
               [{"sid": SID, "pid": 7, "cwd": "/registry-cwd"}])
    assert t["cwd"] == "/registry-cwd", t


def test_registry_record_of_another_process_is_not_trusted():
    # Запись мёртвого процесса с тем же id (сессию возобновляли) — не про этот.
    t = target([SID], {SID: {"pid": 7, "tmux": None, "zellij": None, "cwd": "/proc-cwd"}},
               [{"sid": SID, "pid": 99, "cwd": "/stale"}])
    assert t["cwd"] == "/proc-cwd", t


def test_cwd_falls_back_to_the_registry_for_a_dead_session():
    t = target([], {}, [{"sid": SID, "pid": 99, "cwd": "/registry-cwd"}])
    assert t["how"] == "resume" and t["cwd"] == "/registry-cwd", t


# ── ветка bash ──────────────────────────────────────────────────────────────

STUBS = {
    # proc_tmux разворачивает TMUX_PANE через `tmux display`.
    "tmux": 'if [ "$1" = display ]; then echo fake:1.0; exit 0; fi\n'
            'echo "tmux $*" >>"$STUB_LOG"\n',
    "zellij": 'echo "zellij $*" >>"$STUB_LOG"\n',
    "reptyr": 'echo "reptyr $*" >>"$STUB_LOG"\n'
              'case "$1" in -T) exit "${REPTYR_T_RC:-0}" ;; *) exit "${REPTYR_FLAT_RC:-0}" ;; esac\n',
    "pgrep": 'echo "pgrep $*" >>"$STUB_LOG"\n[ -n "$PGREP_OUT" ] && echo "$PGREP_OUT"\nexit 0\n',
    "claude": 'echo "claude $*" >>"$STUB_LOG"\n',
}


class Env:
    """Подставной HOME, заглушки в PATH и живой «агент» по желанию."""

    def __init__(self, tmp, live=False, tmux=False, transcript=True, registry=True):
        self.tmp = tmp
        self.home = os.path.join(tmp, "home")
        self.cwd = os.path.join(tmp, "proj")
        self.bin = os.path.join(tmp, "bin")
        self.log = os.path.join(tmp, "stub.log")
        os.makedirs(self.home)
        os.makedirs(self.cwd)
        os.makedirs(self.bin)
        for name, body in STUBS.items():
            path = os.path.join(self.bin, name)
            with open(path, "w") as fh:
                fh.write("#!/bin/sh\n" + body)
            os.chmod(path, 0o755)
        open(self.log, "w").close()
        # Без единой метки и сессии скрипт выходит раньше ветки --session.
        self.marks = os.path.join(tmp, "marks")
        with open(self.marks, "w") as fh:
            fh.write("proj : %s\n" % self.cwd)
        if transcript:
            d = os.path.join(self.home, ".claude", "projects", CC["mangle"](self.cwd))
            os.makedirs(d)
            with open(os.path.join(d, SID + ".jsonl"), "w") as fh:
                fh.write(json.dumps({"type": "user", "cwd": self.cwd}) + "\n")
        self.proc = None
        if live:
            env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"])
            env.pop("TMUX", None)
            env.pop("TMUX_PANE", None)
            if tmux:
                env["TMUX_PANE"] = "%9"
            # argv[0] = claude — по нему обход /proc узнаёт агента; `; :` не
            # даёт bash заменить себя на sleep.
            self.proc = subprocess.Popen(
                ["bash", "-c", "exec -a claude bash -c 'sleep 60; :' --session-id " + SID],
                cwd=self.cwd, env=env)
            deadline = time.time() + 5
            while time.time() < deadline and not self._found():
                time.sleep(0.05)
            if registry:
                d = os.path.join(self.home, ".claude", "sessions")
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "%d.json" % self.agent_pid()), "w") as fh:
                    json.dump({"pid": self.agent_pid(), "sessionId": SID, "cwd": self.cwd,
                               "procStart": "1", "kind": "interactive"}, fh)

    def _found(self):
        try:
            return self.agent_pid() > 0
        except Exception:
            return False

    def agent_pid(self):
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open("/proc/%s/cmdline" % pid, "rb") as fh:
                    args = fh.read().split(b"\0")
            except OSError:
                continue
            if args[0] == b"claude" and SID.encode() in args:
                return int(pid)
        return 0

    def run(self, *args, **extra):
        env = {
            "HOME": self.home, "PATH": self.bin + os.pathsep + os.environ["PATH"],
            "SHELL": "/bin/bash", "STUB_LOG": self.log, "FZF_MARKS_FILE": self.marks,
            "TERM": "dumb",
        }
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run(["bash", SRC, "--session", SID, *args], env=env,
                              capture_output=True, text=True, timeout=30)

    def calls(self):
        with open(self.log) as fh:
            return [line.rstrip("\n") for line in fh]

    def close(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()


def with_env(fn, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        e = Env(tmp, **kw)
        try:
            fn(e)
        finally:
            e.close()


def test_print_attaches_to_tmux_instead_of_resuming():
    def check(e):
        r = e.run("--print")
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip().endswith("&& tmux attach -t fake:1.0"), r.stdout
        assert "--resume" not in r.stdout, r.stdout
    with_env(check, live=True, tmux=True)


def test_runs_tmux_attach_and_not_claude():
    def check(e):
        r = e.run()
        assert r.returncode == 0, r.stderr
        assert "tmux attach -t fake:1.0" in e.calls(), e.calls()
        assert not any(c.startswith("claude") for c in e.calls()), e.calls()
    with_env(check, live=True, tmux=True)


def test_inside_tmux_switches_the_client():
    # `tmux attach` изнутри tmux отказывается («should be nested with care»).
    def check(e):
        r = e.run(TMUX="/tmp/tmux-1/default,1,0")
        assert r.returncode == 0, r.stderr
        assert "tmux switch-client -t fake:1.0" in e.calls(), e.calls()
    with_env(check, live=True, tmux=True)


def test_live_without_transcript_takes_cwd_from_the_registry():
    # Было: «session <id> not found», хотя сессия работала.
    def check(e):
        r = e.run("--print")
        assert r.returncode == 0, r.stderr
        assert "not found" not in r.stderr, r.stderr
        assert r.stdout.startswith("cd %s && tmux attach" % e.cwd), r.stdout
    with_env(check, live=True, tmux=True, transcript=False)


def test_orphan_is_stolen_with_reptyr():
    def check(e):
        r = e.run()
        assert r.returncode == 0, r.stderr
        assert e.calls() == ["reptyr -T %d" % e.agent_pid()], e.calls()
    with_env(check, live=True)


def test_print_names_both_halves_of_the_steal():
    def check(e):
        r = e.run("--print")
        pid = e.agent_pid()
        assert r.stdout.strip() == (
            "reptyr -T %d || reptyr \"$(pgrep -x -f 'reptyr -T %d' | head -1)\"" % (pid, pid)), r.stdout
    with_env(check, live=True)


def test_second_steal_moves_the_first_reptyr():
    # Первая кража унесла мастер pty от sshd к первому reptyr: `-T` его не
    # находит, и переносится сам первый reptyr.
    def check(e):
        r = e.run(REPTYR_T_RC=1, PGREP_OUT=4242)
        assert r.returncode == 0, r.stderr
        calls = e.calls()
        assert calls[-1] == "reptyr 4242", calls
        assert not any(c.startswith("claude") for c in calls), calls
    with_env(check, live=True)


def test_failed_steal_falls_back_to_resume_and_says_so():
    def check(e):
        r = e.run(REPTYR_T_RC=1)
        assert "resuming instead" in r.stderr, r.stderr
        assert "claude --resume " + SID in e.calls(), e.calls()
    with_env(check, live=True)


def test_failed_steal_without_transcript_is_an_error_not_a_resume():
    # Возобновлять нечего: транскрипта нет. Код 1, а не тихий успех.
    def check(e):
        r = e.run(REPTYR_T_RC=1)
        assert r.returncode == 1, (r.returncode, r.stderr)
        assert "no transcript" in r.stderr, r.stderr
        assert not any(c.startswith("claude") for c in e.calls()), e.calls()
    with_env(check, live=True, transcript=False)


def test_dead_session_resumes_as_before():
    def check(e):
        r = e.run()
        assert r.returncode == 0, r.stderr
        assert e.calls() == ["claude --resume " + SID], e.calls()
    with_env(check)


def test_unknown_session_is_still_an_error():
    def check(e):
        r = e.run()
        assert r.returncode == 1 and "not found" in r.stderr, (r.returncode, r.stderr)
    with_env(check, transcript=False)


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
