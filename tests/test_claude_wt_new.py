"""claude-wt-new: разбор аргументов, запись о дочерней сессии и команда claude.

Сам claude не запускается: его место занимает подставной скрипт
(`CCFZF_CLAUDE_COMMAND`), который пишет в файл свой argv и каталог, где его
запустили. Каталог записей — временный (`CCFZF_CHILDREN_DIR`), шелл — bash без
чужого rc, чтобы тест не зависел от машины.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

WRAPPER = pathlib.Path(__file__).resolve().parent.parent / "claude-wt-new"
SID = "11111111-2222-4333-8444-555555555555"
HEAD_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

FAKE = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_OUT"], "w", encoding="utf-8") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd()}, fh)
"""


class Env:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.root = root
        self.children = root / "children"
        self.out = root / "fake.json"
        self.fake = root / "fake-claude"
        self.fake.write_text(FAKE, encoding="utf-8")
        self.fake.chmod(0o755)
        self.proj = root / "my project"
        self.proj.mkdir()
        self.prompt = root / "prompt.txt"
        self.prompt.write_text("скажи ок", encoding="utf-8")
        # Пустой rc: `bash -i` иначе прочёл бы ~/.bashrc машины.
        (root / "rc").write_text("", encoding="utf-8")

    def run(self, *args):
        env = dict(os.environ,
                   CCFZF_CLAUDE_COMMAND=str(self.fake),
                   CCFZF_CHILDREN_DIR=str(self.children),
                   FAKE_OUT=str(self.out),
                   HOME=str(self.root),
                   SHELL="/bin/bash")
        return subprocess.run([str(WRAPPER), *map(str, args)], env=env,
                              capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL)

    def called(self):
        if not self.out.exists():
            return None
        return json.loads(self.out.read_text(encoding="utf-8"))

    def record(self, sid=SID):
        p = self.children / (sid + ".json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def test_full_contract():
    e = Env()
    r = e.run(e.proj, "t-child", SID, e.prompt, "plan", "head-x", HEAD_ID)
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


def test_dashes_mean_empty():
    e = Env()
    r = e.run(e.proj, "t-child", SID, e.prompt, "-", "-", "-")
    assert r.returncode == 0, r.stderr
    assert e.called()["argv"] == ["-n", "t-child", "--session-id", SID,
                                  "--", "скажи ок"]
    rec = e.record()
    assert "head" not in rec and "headId" not in rec, rec


def test_prompt_verbatim():
    e = Env()
    text = "-не флаг\n'кавычки' \"двойные\" $(echo no) `echo no` $HOME\n"
    e.prompt.write_text(text, encoding="utf-8")
    r = e.run(e.proj, "t", SID, e.prompt, "-", "-", "-")
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
        r = e.run(e.proj, "t", SID, arg, "-", "-", "-")
        assert r.returncode == 0, r.stderr
        assert e.called()["argv"] == ["-n", "t", "--session-id", SID], make


def test_bad_arguments_start_nothing():
    e = Env()
    good = [e.proj, "t", SID, e.prompt, "-", "h", HEAD_ID]
    cases = {
        "too few": good[:6],
        "too many": good + ["x"],
        "no cwd": [e.root / "nope"] + good[1:],
        "empty name": [e.proj, ""] + good[2:],
        "dash name": [e.proj, "-"] + good[2:],
        "newline name": [e.proj, "a\nb"] + good[2:],
        "bad sid": [e.proj, "t", "123"] + good[3:],
        "no prompt file": good[:3] + [e.root / "nope.txt"] + good[4:],
        "bad mode": good[:4] + ["plan; rm -rf"] + good[5:],
        "bad head id": good[:6] + ["xyz"],
    }
    for label, args in cases.items():
        r = e.run(*args)
        assert r.returncode == 2, (label, r.returncode, r.stderr)
        assert "claude-wt-new:" in r.stderr, (label, r.stderr)
        assert e.called() is None, label
        assert not e.children.exists() or not any(e.children.iterdir()), label


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    sys.exit(0)
