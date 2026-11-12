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
import json, os, sys, time
if sys.argv[1:] == ["agents", "--json"]:
    path = os.environ.get("FAKE_AGENTS", "")
    if not path:
        sys.exit(1)
    sys.stdout.write(open(path, encoding="utf-8").read())
    sys.exit(0)
with open(os.environ["FAKE_OUT"], "w", encoding="utf-8") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(),
               "env": sorted(k for k in os.environ
                             if "CLAUDE" in k or k == "CCFZF_CHILD_CWD_ROOT")}, fh)
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
if os.environ.get("FAKE_SIGNAL"):
    import signal
    os.kill(os.getpid(), getattr(signal, os.environ["FAKE_SIGNAL"]))
    time.sleep(5)
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
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
        env = {k: v for k, v in os.environ.items()
               if "CLAUDE" not in k and k != "CCFZF_CHILD_CWD_ROOT"}
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
        "bypass mode": e.good(mode="bypassPermissions"),
        "bypass mode, other case": e.good(mode="BYPASSPERMISSIONS"),
        "bad head id": e.good(head_id="xyz"),
    }
    for label, args in cases.items():
        r = e.run(*args)
        assert r.returncode == 2, (label, r.returncode, r.stderr)
        assert "claude-wt-new:" in r.stderr, (label, r.stderr)
        e.nothing_happened(label)


def test_only_a_live_marked_head_may_open_one():
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

    def sid_is_running(e):
        e.alive(HEAD_ID, SID)
        return e.good()

    def sid_is_the_head(e):
        return e.good(sid=HEAD_ID)

    def agents_unavailable(e):
        e.agents.write_text("not json", encoding="utf-8")
        return e.good()

    for case in (no_head_id, no_mark, mark_of_another, broken_mark, dead_head,
                 sid_is_running, sid_is_the_head, agents_unavailable):
        e = Env()
        r = e.run(*case(e))
        assert r.returncode == 3, (case.__name__, r.returncode, r.stderr)
        assert "claude-wt-new:" in r.stderr, (case.__name__, r.stderr)
        e.nothing_happened(case.__name__)
        # nothing_happened смотрит только на SID, а здесь id ребёнка — сам head.
        assert e.record(HEAD_ID) is None, case.__name__


def test_a_child_that_is_a_head_opens_a_grandchild():
    """Иерархия head разрешена (Стас, 12.11): ребёнок со своей меткой head
    открывает внука, а его собственная запись о родителе остаётся как была."""
    e = Env()
    e.children.mkdir()
    own = {"sessionId": HEAD_ID, "name": "h", "head": "top", "headId": OTHER}
    (e.children / (HEAD_ID + ".json")).write_text(json.dumps(own), encoding="utf-8")
    r = e.run(*e.good())
    assert r.returncode == 0, r.stderr
    rec = e.record()
    assert rec["headId"] == HEAD_ID and rec["head"] == "head-x", rec
    assert e.record(HEAD_ID) == own, e.record(HEAD_ID)


def test_child_cwd_root():
    """Менеджер на Windows сравнивает строки и симлинков не видит, поэтому
    корень, если он передан, проверяется здесь по разрешённому пути."""
    def mk(e, *parts):
        d = e.root.joinpath(*parts)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def link(e, name, target):
        (e.root / name).symlink_to(target)
        return e.root / name

    cases = [
        # (метка, корень, cwd, код)
        ("empty", lambda e: "", lambda e: e.proj, 0),
        ("inside", lambda e: e.root, lambda e: e.proj, 0),
        ("trailing slash", lambda e: str(e.root) + "/", lambda e: e.proj, 0),
        ("root is a symlink", lambda e: link(e, "link", e.root), lambda e: e.proj, 0),
        ("root is /", lambda e: "/", lambda e: e.proj, 0),
        ("the root itself", lambda e: e.root, lambda e: e.root, 3),
        ("sibling prefix", lambda e: mk(e, "my"), lambda e: e.proj, 3),
        ("glob in root", lambda e: mk(e, "r*"), lambda e: mk(e, "rz", "a"), 3),
        ("symlink out", lambda e: mk(e, "in"),
         lambda e: (mk(e, "outside"), mk(e, "in"),
                    (e.root / "in" / "out").symlink_to(e.root / "outside"),
                    e.root / "in" / "out")[-1], 3),
        ("outside", lambda e: mk(e, "in"), lambda e: e.proj, 3),
        ("relative root", lambda e: "in", lambda e: e.proj, 2),
        ("no such root", lambda e: e.root / "nope", lambda e: e.proj, 2),
    ]
    for label, root, cwd, code in cases:
        e = Env()
        r = e.run(*e.good(cwd=cwd(e)), extra_env={"CCFZF_CHILD_CWD_ROOT": str(root(e))})
        assert r.returncode == code, (label, r.returncode, r.stderr)
        if code:
            assert "claude-wt-new:" in r.stderr, (label, r.stderr)
            e.nothing_happened(label)
        elif label == "inside":
            assert e.record()["cwd"] == str(e.proj.resolve()), e.record()


def test_the_root_does_not_reach_the_child():
    """Корень — условие этого запуска, а не окружение ребёнка: иначе его тесты
    и его собственные вызовы обёртки держались бы корня, которого им никто
    не давал."""
    e = Env()
    r = e.run(*e.good(), extra_env={"CCFZF_CHILD_CWD_ROOT": str(e.root)})
    assert r.returncode == 0, r.stderr
    assert "CCFZF_CHILD_CWD_ROOT" not in e.called()["env"], e.called()


def test_closing_claude_is_not_an_error():
    """Окно терминала (closeOnExit graceful) остаётся открытым на ненулевом
    коде. Сессию, закрытую сигналом, оно должно закрыть, а настоящую ошибку
    claude — показать."""
    cases = [({"FAKE_SIGNAL": "SIGTERM"}, 0), ({"FAKE_SIGNAL": "SIGHUP"}, 0),
             ({"FAKE_SIGNAL": "SIGINT"}, 0), ({"FAKE_EXIT": "143"}, 0),
             ({"FAKE_EXIT": "129"}, 0), ({"FAKE_EXIT": "130"}, 0),
             ({"FAKE_EXIT": "0"}, 0), ({"FAKE_EXIT": "1"}, 1),
             ({"FAKE_EXIT": "2"}, 2), ({"FAKE_EXIT": "137"}, 137)]
    for extra, want in cases:
        e = Env()
        r = e.run(*e.good(), extra_env=extra)
        assert r.returncode == want, (extra, r.returncode, r.stderr)
        assert e.called() is not None, extra


def test_a_hangup_of_the_whole_window_is_a_clean_exit():
    """Закрытое окно или оборванный ssh бьют сигналом всю группу процессов —
    и обёртку тоже, а не только claude."""
    import signal
    e = Env()
    p = subprocess.Popen([str(WRAPPER), *map(str, e.good())],
                         env=e.env({"FAKE_SLEEP": "20"}), start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    deadline = time.time() + 10
    while e.called() is None and time.time() < deadline:
        time.sleep(0.1)
    assert e.called() is not None
    os.killpg(p.pid, signal.SIGTERM)
    assert p.wait(timeout=10) == 0


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
