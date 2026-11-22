"""Тип проекта и проект-владелец сессии. Запуск: python3 tests/test_project_type.py

Тип живёт в `claudeWt.projects` у windows11-manager и приезжает файлом трекера
(`projects[].type`). Здесь он клеится к строке проекта и к каждой сессии —
через проект-владелец (`projectCwd`): пикер знает только точное совпадение
`cwd`, а сессия из worktree живёт в подкаталоге проекта.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
NOW = 1785958293


def _read_projects(projects):
    payload = {"generated": NOW - 1, "host": "box", "pid": 7, "windows": {},
               "projects": projects}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "windows.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return CC["read_windows"](path, NOW)[4]


def test_a_tracker_entry_with_only_a_type_is_kept():
    # Менеджер шлёт проект с одним типом — без hotkey и icon. Прежний фильтр
    # `hotkey or icon` выбрасывал его молча, и тип терялся на этом звене.
    got = _read_projects([
        {"cwd": "/p/site", "name": "site", "type": "work"},
        {"cwd": "/p/home", "name": "home", "hotkey": "Ctrl+F11", "type": "home"},
        {"cwd": "/p/none", "name": "none"},
        {"cwd": "/p/junk", "name": "junk", "type": 5},
        {"cwd": "/p/blank", "name": "blank", "type": "  "},
    ])
    assert got == [
        {"cwd": "/p/site", "name": "site", "type": "work"},
        {"cwd": "/p/home", "name": "home", "hotkey": "Ctrl+F11", "type": "home"},
    ], got


def test_type_is_normalized_on_read():
    # Менеджер уже нормализует, но файл приезжает с другой машины: ` Work `
    # от трекера прошлой версии не должно стать третьим типом рядом с `work`.
    got = _read_projects([{"cwd": "/p/site", "name": "site", "type": " Work "}])
    assert got == [{"cwd": "/p/site", "name": "site", "type": "work"}], got


def test_project_row_carries_its_type():
    rows = [{"path": "/p/site", "name": "site", "mark": True, "n": 1, "live": 0, "mtime": 5.0},
            {"path": "/p/other", "name": "other", "mark": True, "n": 1, "live": 0, "mtime": 4.0}]
    out = CC["merge_project_hotkeys"](rows, [{"cwd": "/p/site", "name": "site", "type": "work"}])
    assert out[0]["type"] == "work", out
    assert "type" not in out[1], out


def test_type_alone_does_not_invent_a_project_row():
    # Строку заводит только хоткей: клавише нужна строка, типу — нет.
    out = CC["merge_project_hotkeys"]([], [{"cwd": "/p/site", "name": "site", "type": "work"}])
    assert out == [], out


def test_synthetic_hotkey_row_carries_its_type():
    out = CC["merge_project_hotkeys"](
        [], [{"cwd": "/p/cold", "name": "cold", "hotkey": "Ctrl+F12", "type": "home"}])
    assert out[0]["hotkey"] == "Ctrl+F12" and out[0]["type"] == "home", out


PROJECTS = [{"cwd": "/p/site", "name": "site", "type": "work"},
            {"cwd": "/p/site/sub", "name": "sub"},
            {"cwd": "/a/b", "name": "b", "type": "home"}]


def test_session_in_a_worktree_belongs_to_the_ancestor_project():
    owner = CC["project_owner"]("/p/site/.worktrees/feat", PROJECTS, {})
    assert owner == "/p/site", owner


def test_nearest_project_wins_over_a_farther_one():
    owner = CC["project_owner"]("/p/site/sub/wt", PROJECTS, {})
    assert owner == "/p/site/sub", owner


def test_project_itself_is_its_own_owner():
    assert CC["project_owner"]("/p/site", PROJECTS, {}) == "/p/site"


def test_prefix_without_a_segment_boundary_is_not_an_ancestor():
    # /a/bc — не потомок /a/b: сравнение по сегментам пути, а не по строке.
    assert CC["project_owner"]("/a/bc", PROJECTS, {}) == "/a/bc"


def test_trailing_slash_in_a_project_cwd_does_not_hide_it():
    assert CC["project_owner"]("/q/x/wt", [{"cwd": "/q/x/", "name": "x"}], {}) == "/q/x"


def test_outside_projects_the_nearest_mark_owns_the_session():
    marks = {"/m/vault": "vault", "/m": "m"}
    assert CC["project_owner"]("/m/vault/notes", PROJECTS, marks) == "/m/vault"


def test_without_projects_or_marks_the_session_owns_itself():
    assert CC["project_owner"]("/lonely/dir", PROJECTS, {"/m": "m"}) == "/lonely/dir"


def test_project_type_of_owner():
    assert CC["project_type_of"]("/p/site", PROJECTS) == "work"
    assert CC["project_type_of"]("/p/site/sub", PROJECTS) == ""
    assert CC["project_type_of"]("/m/vault", PROJECTS) == ""


def test_session_record_drops_an_empty_project_type():
    # Пустые поля в ответ не пишутся (state_record): у сессии без типа ключа
    # projectType нет, а projectCwd есть всегда.
    rec = CC["state_record"]({"id": "x", "cwd": "/m/vault/notes", "title": "t", "mtime": 1,
                              "live": False, "kind": "interactive",
                              "projectCwd": "/m/vault", "projectType": ""})
    assert rec["projectCwd"] == "/m/vault" and "projectType" not in rec, rec


SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccfzf")
SID = "dddddddd-1111-2222-3333-444444444444"


def _session_in(tmp, cwd):
    d = os.path.join(tmp, ".claude", "projects", re.sub(r"[^a-zA-Z0-9]", "-", cwd))
    os.makedirs(d, exist_ok=True)
    os.makedirs(cwd, exist_ok=True)
    with open(os.path.join(d, SID + ".jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"cwd": cwd, "type": "user",
                             "message": {"role": "user", "content": "hello"}}) + "\n")


def _state(tmp, wdir):
    env = dict(os.environ)
    env.update({"HOME": tmp, "FZF_MARKS_FILE": os.path.join(tmp, "no-marks"),
                "CCFZF_SESSIONS_FILE": os.path.join(tmp, "dump.json"),
                "CCFZF_PROJECTS_FILE": "", "CCFZF_WINDOWS_FILE": "",
                "CCFZF_WINDOWS_DIR": wdir,
                "CCFZF_FACTS_FILE": os.path.join(tmp, "facts.json"),
                "XDG_CACHE_HOME": os.path.join(tmp, "cache")})
    r = subprocess.run(["bash", SRC, "--state"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return json.loads(r.stdout)


def test_state_glues_the_ancestor_project_and_its_type_to_the_session():
    # Сквозной прогон: сессия в worktree проекта получает его cwd и тип, а
    # строка проекта — свой тип. Проводку между функциями ловит только так.
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "proj")
        _session_in(tmp, os.path.join(proj, ".worktrees", "feat"))
        os.makedirs(os.path.join(proj, "docs"), exist_ok=True)
        wdir = os.path.join(tmp, "windows")
        os.makedirs(wdir)
        with open(os.path.join(wdir, "box.json"), "w", encoding="utf-8") as fh:
            json.dump({"generated": int(time.time()), "host": "box", "pid": 7, "windows": {},
                       "projects": [{"cwd": proj, "name": "proj", "hotkey": "Ctrl+F11",
                                     "type": "work"}]}, fh)
        out = _state(tmp, wdir)
        row = [s for s in out["sessions"] if s["id"] == SID][0]
        assert row["projectCwd"] == proj and row["projectType"] == "work", row
        prow = [p for p in out["projects"] if p["path"] == proj][0]
        assert prow["type"] == "work", prow


def test_state_without_a_tracker_still_names_the_owner():
    # Старый менеджер или его нет вовсе: типа нет, а владелец — сам cwd.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.path.join(tmp, "alone")
        _session_in(tmp, cwd)
        out = _state(tmp, os.path.join(tmp, "no-windows"))
        row = [s for s in out["sessions"] if s["id"] == SID][0]
        assert row["projectCwd"] == cwd and "projectType" not in row, row


if __name__ == "__main__":
    fails = 0
    names = [n for n in globals() if n.startswith("test_")]
    for name in sorted(names):
        try:
            globals()[name]()
            print("ok   " + name)
        except (AssertionError, KeyError) as e:
            fails += 1
            print("FAIL " + name + ": " + repr(e))
    print("%d/%d passed" % (len(names) - fails, len(names)))
    sys.exit(1 if fails else 0)
