"""Сессии из git worktree принадлежат основному проекту.

Запуск: python3 tests/test_worktree_owner.py

Worktree рядом с клоном (`<repo>.<feat>`) — не потомок проекта, и по одним
предкам `cwd` владелец у его сессий был бы сам worktree: без типа, своей
строкой проекта. Здесь — распознавание по `.git` (worktree, подмодуль, клон),
владелец через основной репо, память о worktree, которого уже нет, и поля
`worktree`/`projectCwd` в `--state` и в дампе.

Фикстуры — настоящие репозитории git во временных каталогах: форма `.git`,
`gitdir:` и `commondir` берётся у самого git, а не переписана руками.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccfzf")
SID = "eeeeeeee-1111-2222-3333-444444444444"
SID2 = "ffffffff-1111-2222-3333-444444444444"


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "protocol.file.allow=always", "-c", "init.defaultBranch=main",
                        *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout


def repo(path):
    os.makedirs(path)
    git(path, "init", "-q")
    with open(os.path.join(path, "f"), "w") as fh:
        fh.write("x\n")
    os.makedirs(os.path.join(path, "sub"))
    with open(os.path.join(path, "sub", "g"), "w") as fh:
        fh.write("y\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "init")
    return path


def fresh(tmp):
    """Чистая память и кэш, память — во временном каталоге."""
    CC["WORKTREES_FILE"] = os.path.join(tmp, "mem", "worktrees.json")
    CC["WT_CACHE"].clear()
    CC["WT_MEMORY"].clear()
    CC["WT_MEMORY_LOADED"][0] = False


def test_a_worktree_knows_its_main_repo_and_branch():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(tmp, "proj.feat")
        git(main, "worktree", "add", "-q", "-b", "feat/x", wt)
        got = CC["worktree_of"](wt)
        assert got == {"path": wt, "branch": "feat/x", "main": main}, got
        # Из подкаталога — тот же корень worktree.
        assert CC["worktree_of"](os.path.join(wt, "sub")) == got


def test_a_detached_head_has_an_empty_branch():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(tmp, "proj.detached")
        git(main, "worktree", "add", "-q", "--detach", wt)
        got = CC["worktree_of"](wt)
        assert got == {"path": wt, "branch": "", "main": main}, got


def test_a_worktree_inside_the_repo_is_recognized_too():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(main, ".worktrees", "inner")
        git(main, "worktree", "add", "-q", "-b", "inner", wt)
        assert CC["worktree_of"](wt) == {"path": wt, "branch": "inner", "main": main}


def test_a_submodule_is_not_a_worktree():
    # У подмодуля тоже файл `.git` с `gitdir:`, но в его gitdir нет
    # `commondir`. Принять его за worktree — увезти его сессии в чужой проект.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        lib = repo(os.path.join(tmp, "lib"))
        main = repo(os.path.join(tmp, "proj"))
        git(main, "submodule", "add", "-q", lib, "vendor/lib")
        sm = os.path.join(main, "vendor", "lib")
        assert os.path.isfile(os.path.join(sm, ".git"))
        assert CC["worktree_of"](sm) is None
        assert CC["worktree_of"](os.path.join(sm, "sub")) is None


def test_a_plain_clone_and_a_non_repo_are_not_worktrees():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        assert CC["worktree_of"](main) is None
        assert CC["worktree_of"](os.path.join(main, "sub")) is None
        os.makedirs(os.path.join(tmp, "plain"))
        assert CC["worktree_of"](os.path.join(tmp, "plain")) is None


def test_a_removed_worktree_is_remembered():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(tmp, "proj.gone")
        git(main, "worktree", "add", "-q", "-b", "gone", wt)
        CC["worktree_of"](wt)
        with open(CC["WORKTREES_FILE"], encoding="utf-8") as fh:
            mem = json.load(fh)
        assert mem[wt]["main"] == main and mem[wt]["branch"] == "gone", mem
        git(main, "worktree", "remove", "--force", wt)
        assert not os.path.exists(wt)
        # Новый процесс: ни кэша, ни памяти в нём ещё нет — только файл.
        CC["WT_CACHE"].clear()
        CC["WT_MEMORY"].clear()
        CC["WT_MEMORY_LOADED"][0] = False
        assert CC["worktree_of"](wt) == {"path": wt, "branch": "gone", "main": main}
        assert CC["worktree_of"](os.path.join(wt, "sub"))["path"] == wt


def test_memory_is_not_rewritten_on_every_call():
    # `--state` зовётся раз в секунду: запись — только когда есть что менять.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(tmp, "proj.feat")
        git(main, "worktree", "add", "-q", "-b", "feat", wt)
        CC["worktree_of"](wt)
        before = os.stat(CC["WORKTREES_FILE"]).st_mtime_ns
        CC["WT_CACHE"].clear()
        CC["WT_MEMORY"].clear()
        CC["WT_MEMORY_LOADED"][0] = False
        time.sleep(0.01)
        CC["worktree_of"](wt)
        assert os.stat(CC["WORKTREES_FILE"]).st_mtime_ns == before


def test_owner_and_type_come_from_the_main_repo():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(tmp, "proj.feat")
        git(main, "worktree", "add", "-q", "-b", "feat", wt)
        projects = [{"cwd": main, "name": "proj", "type": "home"}]
        owner = CC["project_owner"](wt, projects, {})
        assert owner == main, owner
        assert CC["project_type_of"](owner, projects) == "home"
        # Подкаталог worktree — подкаталог основного; его владелец — проект.
        assert CC["project_owner"](os.path.join(wt, "sub"), projects, {}) == main
        # Без записи в projects владелец — сам основной репо, не worktree.
        assert CC["project_owner"](wt, [], {}) == main
        assert CC["owners_of"](wt, {}) == {main}
        # Закладка на основном — тоже владелец, как у его подкаталогов.
        assert CC["owners_of"](os.path.join(wt, "sub"), {main: "proj"}) == \
            {os.path.join(main, "sub"), main}


def test_an_own_record_of_the_worktree_wins_over_inheritance():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(tmp, "proj.long")
        git(main, "worktree", "add", "-q", "-b", "long", wt)
        projects = [{"cwd": main, "name": "proj", "type": "home"},
                    {"cwd": wt, "name": "long", "type": "work"}]
        assert CC["project_owner"](wt, projects, {}) == wt
        assert CC["project_owner"](os.path.join(wt, "sub"), projects, {}) == wt
        assert CC["owners_of"](wt, {}, projects) == {wt}
        # Закладка на worktree — тоже своя запись.
        assert CC["owners_of"](wt, {wt: "long"}) == {wt}
        assert CC["project_owner"](wt, [], {wt: "long"}) == wt


def test_project_rows_have_no_row_for_a_worktree():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        fresh(tmp)
        main = repo(os.path.join(tmp, "proj"))
        wt = os.path.join(tmp, "proj.feat")
        git(main, "worktree", "add", "-q", "-b", "feat", wt)
        dirs = [{"cwd": wt, "files": [("/d/%s.jsonl" % SID, 10.0)]},
                {"cwd": main, "files": [("/d/%s.jsonl" % SID2, 5.0)]}]
        rows = CC["project_rows"](dirs, {SID}, {}, age_of=lambda p: 0.0,
                                  todo_at=lambda p: None)
        paths = [r["path"] for r in rows]
        assert paths == [main], paths
        assert rows[0]["n"] == 2 and rows[0]["live"] == 1, rows


def test_dump_record_carries_project_cwd_and_worktree_only_when_set():
    base = {"id": "a", "title": "t", "cwd": "/w", "live": False, "mtime": 1.0,
            "kind": "interactive", "parent": "", "activityAt": 0, "shell": False}
    assert CC["dump_record"](dict(base, projectCwd="", projectType="")) == base
    got = CC["dump_record"](dict(base, projectCwd="/m", projectType="home",
                                 worktree={"path": "/w", "branch": ""}))
    assert got == dict(base, projectCwd="/m", worktree={"path": "/w", "branch": ""}), got


def _session_in(tmp, cwd, sid):
    d = os.path.join(tmp, ".claude", "projects", re.sub(r"[^a-zA-Z0-9]", "-", cwd))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"cwd": cwd, "type": "user",
                             "message": {"role": "user", "content": "hello"}}) + "\n")


def _env(tmp, wdir):
    env = dict(os.environ)
    env.update({"HOME": tmp, "FZF_MARKS_FILE": os.path.join(tmp, "no-marks"),
                "CCFZF_SESSIONS_FILE": os.path.join(tmp, "dump.json"),
                "CCFZF_PROJECTS_FILE": "", "CCFZF_WINDOWS_FILE": "",
                "CCFZF_WINDOWS_DIR": wdir, "CCFZF_STATE_DUMP_MAX_AGE": "0",
                "CCFZF_FACTS_FILE": os.path.join(tmp, "facts.json"),
                "XDG_CACHE_HOME": os.path.join(tmp, "cache")})
    env.pop("CCFZF_WORKTREES_FILE", None)
    return env


def _fixture(tmp):
    main = repo(os.path.join(tmp, "proj"))
    wt = os.path.join(tmp, "proj.feat")
    git(main, "worktree", "add", "-q", "-b", "feat/x", wt)
    _session_in(tmp, wt, SID)
    _session_in(tmp, main, SID2)
    wdir = os.path.join(tmp, "windows")
    os.makedirs(wdir)
    with open(os.path.join(wdir, "box.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": int(time.time()), "host": "box", "pid": 7, "windows": {},
                   "projects": [{"cwd": main, "name": "proj", "type": "home"}]}, fh)
    return main, wt, wdir


def test_state_and_its_dump_carry_the_worktree_and_its_owner():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        main, wt, wdir = _fixture(tmp)
        r = subprocess.run(["bash", SRC, "--state"], capture_output=True, text=True,
                           env=_env(tmp, wdir))
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        rows = {s["id"]: s for s in out["sessions"]}
        w = rows[SID]
        assert w["projectCwd"] == main and w["projectType"] == "home", w
        assert w["worktree"] == {"path": wt, "branch": "feat/x"}, w
        m = rows[SID2]
        assert "worktree" not in m and "projectCwd" not in m, m
        paths = [p["path"] for p in out["projects"]]
        assert wt not in paths and main in paths, paths
        # Память — под ~/.ccfzf/ домашнего каталога прогона.
        assert os.path.isfile(os.path.join(tmp, ".ccfzf", "worktrees.json"))

        with open(os.path.join(tmp, "dump.json"), encoding="utf-8") as fh:
            dump = {s["id"]: s for s in json.load(fh)["sessions"]}
        assert dump[SID]["projectCwd"] == main, dump[SID]
        assert dump[SID]["worktree"] == {"path": wt, "branch": "feat/x"}, dump[SID]
        assert "projectCwd" not in dump[SID2] and "worktree" not in dump[SID2], dump[SID2]


def test_dump_mode_writes_the_same_fields():
    # Дамп пишут оба режима; поле, которое знает только `state`, пропадало
    # бы из файла после каждого ручного `--dump`.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        main, wt, wdir = _fixture(tmp)
        r = subprocess.run(["bash", SRC, "--dump"], capture_output=True, text=True,
                           env=_env(tmp, wdir))
        assert r.returncode == 0, r.stderr
        with open(os.path.join(tmp, "dump.json"), encoding="utf-8") as fh:
            dump = {s["id"]: s for s in json.load(fh)["sessions"]}
        assert dump[SID]["projectCwd"] == main, dump[SID]
        assert dump[SID]["worktree"] == {"path": wt, "branch": "feat/x"}, dump[SID]
        assert "projectCwd" not in dump[SID2], dump[SID2]


def test_state_keeps_a_removed_worktree_under_its_main_project():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        main, wt, wdir = _fixture(tmp)
        env = _env(tmp, wdir)
        r = subprocess.run(["bash", SRC, "--state"], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        git(main, "worktree", "remove", "--force", wt)
        r = subprocess.run(["bash", SRC, "--state"], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        w = {s["id"]: s for s in out["sessions"]}[SID]
        assert w["projectCwd"] == main and w["worktree"]["branch"] == "feat/x", w
        assert wt not in [p["path"] for p in out["projects"]]


if __name__ == "__main__":
    if not shutil.which("git"):
        print("git not found")
        sys.exit(1)
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
