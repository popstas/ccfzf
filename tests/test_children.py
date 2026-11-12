"""Дочерние сессии: `head`/`headId` в строке --state из записей claude-wt-new.

Запуск: python3 tests/test_children.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from test_state_mode import A, B, _facts_env, build_home, run_state

CC = harness.load()
HEAD_ID = "cccccccc-1111-2222-3333-444444444444"


def write_child(d, sid, **rec):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, sid + ".json"), "w", encoding="utf-8") as fh:
        json.dump(dict({"sessionId": sid, "name": "t-child"}, **rec), fh)


def test_state_names_the_head_of_a_child():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        # Умолчание каталога — ~/.ccfzf/children, то есть HOME подставной.
        write_child(os.path.join(tmp, ".ccfzf", "children"), A,
                    head="head-x", headId=HEAD_ID)
        got = {s["id"]: s for s in run_state(tmp, "")["sessions"]}
        assert got[A]["head"] == "head-x", got[A]
        assert got[A]["headId"] == HEAD_ID, got[A]
        # Обычная сессия — без ключей, как у todo и comment.
        assert "head" not in got[B] and "headId" not in got[B], got[B]
        # `parent` занят фоновыми форками и записью не трогается.
        assert got[A]["parent"] == "", got[A]


def test_an_adopted_session_and_a_grandchild_carry_their_heads():
    """Привязанный исполнитель (head-adopt) открывался не через session-new и
    окна в трекере может не иметь — head ему всё равно отдаётся. Внук и его
    head-ребёнок несут каждый своего."""
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        d = os.path.join(tmp, ".ccfzf", "children")
        write_child(d, A, head="new-h", headId=B, adopted=True,
                    prevHeadId=HEAD_ID, prevHead="old-h", cwd="/x", createdAt=1)
        write_child(d, B, head="top", headId=HEAD_ID)
        got = {s["id"]: s for s in run_state(tmp, "")["sessions"]}
        assert got[A]["head"] == "new-h" and got[A]["headId"] == B, got[A]
        assert got[B]["head"] == "top" and got[B]["headId"] == HEAD_ID, got[B]
        # Служебные поля привязки в строку не попадают: белый список.
        for key in ("adopted", "prevHeadId", "prevHead"):
            assert key not in got[A], (key, got[A])


def test_the_directory_is_configurable_and_can_be_off():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        other = os.path.join(tmp, "elsewhere")
        write_child(other, A, head="h")
        got = run_state(tmp, "", env_extra={"CCFZF_CHILDREN_DIR": other})
        assert got["sessions"][0]["head"] == "h"
        got = run_state(tmp, "", env_extra={"CCFZF_CHILDREN_DIR": ""})
        assert "head" not in got["sessions"][0]


def test_the_python_block_finds_the_default_directory_itself():
    """Пикер на Windows зовёт блок без bash — умолчание обязано совпасть."""
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        write_child(os.path.join(tmp, ".ccfzf", "children"), A, head="h")
        py = os.path.join(tmp, "ccfzf.py")
        with open(py, "w", encoding="utf-8") as fh:
            fh.write(harness.block())
        env = dict(os.environ)
        env.update(_facts_env(tmp, ""))
        r = subprocess.run([sys.executable, py, "--state"],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["sessions"][0]["head"] == "h"


def test_read_children_whitelists():
    with tempfile.TemporaryDirectory() as d:
        write_child(d, A, head="h", headId=HEAD_ID, cwd="/x", createdAt=1)
        write_child(d, B, head=["не строка"], headId="не uuid")
        # Имя файла не uuid, кривой json, чужой sessionId внутри.
        with open(os.path.join(d, "notes.json"), "w") as fh:
            fh.write("{}")
        bad = "dddddddd-1111-2222-3333-444444444444"
        with open(os.path.join(d, bad + ".json"), "w") as fh:
            fh.write("{not json")
        lie = "eeeeeeee-1111-2222-3333-444444444444"
        write_child(d, lie, sessionId=A, head="чужая")
        got = CC["read_children"](d, {A, B, bad, lie})
        assert got == {A: {"head": "h", "headId": HEAD_ID}}, got
        # Читаются только спрошенные: незнакомые id не открываются вовсе.
        assert CC["read_children"](d, {B}) == {}
        assert CC["read_children"](os.path.join(d, "нет"), {A}) == {}
        assert CC["read_children"]("", {A}) == {}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
