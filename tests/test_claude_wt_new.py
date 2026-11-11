"""claude-wt-new: разбор аргументов, проверка головы, запись о дочерней сессии.

Сам claude не запускается: его место занимает подставной скрипт
(`CCFZF_CLAUDE_COMMAND`). На `agents --json` он отвечает списком живых сессий
из файла, на всё прочее пишет в файл свой argv, каталог и окружение. Каталоги
записей и меток — временные, шелл — bash без чужого rc, чтобы тест не зависел
от машины.
"""
import json
import os
import pathlib
import pty
import select
import subprocess
import sys
import tempfile
import time

WRAPPER = pathlib.Path(__file__).resolve().parent.parent / "claude-wt-new"
SID = "11111111-2222-4333-8444-555555555555"
HEAD_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
OTHER = "99999999-bbbb-4ccc-8ddd-eeeeeeeeeeee"

FAKE = """#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:] == ["agents", "--json"]:
    path = os.environ.get("FAKE_AGENTS", "")
    if not path:
        sys.exit(1)
    sys.stdout.write(open(path, encoding="utf-8").read())
    sys.exit(0)
with open(os.environ["FAKE_OUT"], "w", encoding="utf-8") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(),
               "env": sorted(k for k in os.environ if "CLAUDE" in k)}, fh)
"""


class Env:
    """Подставной HOME, где голова HEAD_ID жива и помечена."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.root = root
        self.children = root / "children"
        self.heads = root / "heads"
        self.heads.mkdir()
        self.agents = root / "agents.json"
        self.out = root / "fake.json"
        self.fake = root / "fake-claude"
        self.fake.write_text(FAKE, encoding="utf-8")
        self.fake.chmod(0o755)
        self.proj = root / "my project"
        self.proj.mkdir()
        self.prompt = root / "prompt.txt"
        self.prompt.write_text("скажи ок", encoding="utf-8")
        self.mark(HEAD_ID, name="head-x")
        self.alive(HEAD_ID)

    def mark(self, sid, **rec):
        body = dict({"sessionId": sid, "name": "h", "cwd": "/", "createdAt": 1}, **rec)
        (self.heads / (sid + ".json")).write_text(json.dumps(body), encoding="utf-8")

    def alive(self, *sids):
        self.agents.write_text(json.dumps(
            [{"pid": 1, "kind": "interactive", "sessionId": s, "name": "x",
              "status": "idle"} for s in sids]), encoding="utf-8")

    def env(self, extra_env=None):
        # Без переменных той сессии, что гоняет тест: иначе ответ зависел бы
        # от того, кто его запустил.
        env = {k: v for k, v in os.environ.items() if "CLAUDE" not in k}
        env.update(extra_env or {})
        env.update(CCFZF_CLAUDE_COMMAND=str(self.fake),
                   CCFZF_CHILDREN_DIR=str(self.children),
                   CCFZF_HEADS_DIR=str(self.heads),
                   FAKE_OUT=str(self.out),
                   FAKE_AGENTS=str(self.agents),
                   HOME=str(self.root),
                   SHELL="/bin/bash")
        return env

    def run(self, *args, extra_env=None):
        return subprocess.run([str(WRAPPER), *map(str, args)], env=self.env(extra_env),
                              capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL)

    def good(self, **over):
        a = {"cwd": self.proj, "name": "t", "sid": SID, "prompt": self.prompt,
             "mode": "-", "head": "head-x", "head_id": HEAD_ID}
        a.update(over)
        return [a[k] for k in ("cwd", "name", "sid", "prompt", "mode", "head", "head_id")]

    def called(self):
        if not self.out.exists():
            return None
        return json.loads(self.out.read_text(encoding="utf-8"))

    def record(self, sid=SID):
        p = self.children / (sid + ".json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def nothing_happened(self, label):
        assert self.called() is None, label
        assert self.record() is None, label
        left = [p.name for p in self.children.iterdir()] if self.children.exists() else []
        assert not [n for n in left if SID in n], (label, left)


def test_full_contract():
    e = Env()
    r = e.run(*e.good(name="t-child", mode="plan"))
    assert r.returncode == 0, r.stderr
    c = e.called()
    assert c["argv"] == ["-n", "t-child", "--session-id", SID,
                         "--permission-mode", "plan", "--", "скажи ок"], c
    assert c["cwd"] == str(e.proj.resolve()), c
    rec = e.record()
    created = rec.pop("createdAt")
    assert isinstance(created, int) and created > 1_700_000_000, created
    assert rec == {"sessionId": SID, "name": "t-child", "head": "head-x",
                   "headId": HEAD_ID, "cwd": str(e.proj.resolve())}, rec


def test_head_name_comes_from_the_mark_when_not_given():
    e = Env()
    r = e.run(*e.good(head="-"))
    assert r.returncode == 0, r.stderr
    assert e.called()["argv"] == ["-n", "t", "--session-id", SID, "--", "скажи ок"]
    assert e.record()["head"] == "head-x", e.record()


def test_prompt_verbatim():
    e = Env()
    text = "-не флаг\n'кавычки' \"двойные\" $(echo no) `echo no` $HOME\n"
    e.prompt.write_text(text, encoding="utf-8")
    r = e.run(*e.good())
    assert r.returncode == 0, r.stderr
    # $(cat) срезает хвостовые переводы строк — как и обещано контрактом.
    assert e.called()["argv"][-1] == text.rstrip("\n")


def test_no_prompt():
    for make in ("empty", "dash"):
        e = Env()
        if make == "empty":
            e.prompt.write_text("\n", encoding="utf-8")
            arg = e.prompt
        else:
            arg = "-"
        r = e.run(*e.good(prompt=arg))
        assert r.returncode == 0, r.stderr
        assert e.called()["argv"] == ["-n", "t", "--session-id", SID], make


def test_the_parent_session_does_not_leak_in():
    """Запуск из шелла другой сессии Claude Code передал бы ей своё окружение,
    и новая сессия не зарегистрировалась бы вовсе: нет её ни в
    ~/.claude/sessions, ни в ListAgents."""
    e = Env()
    leaked = {"CLAUDE_CODE_SESSION_ID": SID, "CLAUDE_CODE_CHILD_SESSION": "1",
              "CLAUDE_CODE_MESSAGING_SOCKET": "/run/x.sock", "CLAUDECODE": "1",
              "CLAUDE_PID": "123", "CLAUDE_EFFORT": "high",
              "CLAUDE_PLUGIN_DATA": "/x", "CLAUDE_PROJECT_DIR": "/y",
              "MY_CLAUDE_NOTE": "keep"}
    r = e.run(*e.good(), extra_env=leaked)
    assert r.returncode == 0, r.stderr
    assert e.called()["env"] == ["CCFZF_CLAUDE_COMMAND", "MY_CLAUDE_NOTE"], e.called()


def test_bad_arguments_start_nothing():
    e = Env()
    good = e.good()
    cases = {
        "too few": good[:6],
        "too many": good + ["x"],
        "no cwd": e.good(cwd=e.root / "nope"),
        "empty name": e.good(name=""),
        "dash name": e.good(name="-"),
        "newline name": e.good(name="a\nb"),
        "bad sid": e.good(sid="123"),
        "no prompt file": e.good(prompt=e.root / "nope.txt"),
        "bad mode": e.good(mode="plan; rm -rf"),
        "bad head id": e.good(head_id="xyz"),
    }
    for label, args in cases.items():
        r = e.run(*args)
        assert r.returncode == 2, (label, r.returncode, r.stderr)
        assert "claude-wt-new:" in r.stderr, (label, r.stderr)
        e.nothing_happened(label)


def test_only_a_live_marked_head_that_is_no_child_may_open_one():
    def no_head_id(e):
        return e.good(head_id="-")

    def no_mark(e):
        (e.heads / (HEAD_ID + ".json")).unlink()
        return e.good()

    def mark_of_another(e):
        e.mark(HEAD_ID, sessionId=OTHER)
        return e.good()

    def broken_mark(e):
        (e.heads / (HEAD_ID + ".json")).write_text("{not json", encoding="utf-8")
        return e.good()

    def dead_head(e):
        e.alive(OTHER)
        return e.good()

    def head_is_a_child(e):
        e.children.mkdir()
        (e.children / (HEAD_ID + ".json")).write_text(
            json.dumps({"sessionId": HEAD_ID, "name": "h", "headId": OTHER}),
            encoding="utf-8")
        return e.good()

    def agents_unavailable(e):
        e.agents.write_text("not json", encoding="utf-8")
        return e.good()

    for case in (no_head_id, no_mark, mark_of_another, broken_mark, dead_head,
                 head_is_a_child, agents_unavailable):
        e = Env()
        r = e.run(*case(e))
        assert r.returncode == 3, (case.__name__, r.returncode, r.stderr)
        assert "claude-wt-new:" in r.stderr, (case.__name__, r.stderr)
        e.nothing_happened(case.__name__)


def test_a_refusal_stays_on_screen_in_a_terminal():
    """В окне WT отказ должен остаться видимым: без паузы окно закрылось бы
    раньше, чем человек прочтёт причину."""
    e = Env()
    master, slave = pty.openpty()
    p = subprocess.Popen([str(WRAPPER), *map(str, e.good(head_id="-"))],
                         env=e.env(), stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    seen = b""
    deadline = time.time() + 10
    while b"Enter" not in seen and time.time() < deadline:
        if select.select([master], [], [], 0.5)[0]:
            seen += os.read(master, 4096)
    assert b"claude-wt-new:" in seen and b"Enter" in seen, seen
    time.sleep(0.5)
    assert p.poll() is None, "closed without waiting"
    os.write(master, b"\n")
    assert p.wait(timeout=10) == 3
    os.close(master)
    e.nothing_happened("pty")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    sys.exit(0)
