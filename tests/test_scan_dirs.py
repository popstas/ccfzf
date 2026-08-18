"""Обход ~/.claude/projects: какие каталоги вообще доезжают до списка.

Запуск: python3 tests/test_scan_dirs.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

A = "aaaaaaaa-1111-2222-3333-444444444444"


def write_dir(root, mangled, cwd, sid=A):
    """Каталог проекта с одним транскриптом, у которого в первой строке cwd."""
    d = os.path.join(root, mangled)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, sid + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"cwd": cwd, "type": "user",
                             "message": {"role": "user", "content": "hi"}}) + "\n")
    return d


def test_cwd_is_read_from_the_first_lines():
    with tempfile.TemporaryDirectory() as tmp:
        d = write_dir(tmp, "-p-one", "/p/one/")
        assert CC["dir_cwd"]([os.path.join(d, A + ".jsonl")]) == "/p/one"


def test_a_session_started_in_the_root_keeps_its_cwd():
    # `"/".rstrip("/")` — пустая строка, а пустой cwd для scan_dirs значит
    # «каталог не читается». Сессия, заведённая в `/` (так их заводит запуск
    # не из терминала), уносила с собой весь каталог `~/.claude/projects/-`:
    # пропадали все его сессии разом, молча и без единого признака.
    with tempfile.TemporaryDirectory() as tmp:
        d = write_dir(tmp, "-", "/")
        assert CC["dir_cwd"]([os.path.join(d, A + ".jsonl")]) == "/"


def test_scan_dirs_keeps_the_root_project():
    # Тот же случай сквозь настоящий обход: проверяется не значение cwd, а
    # то, что каталог вообще попал в список.
    with tempfile.TemporaryDirectory() as tmp:
        projects = os.path.join(tmp, "projects")
        write_dir(projects, "-", "/")
        write_dir(projects, "-p-one", "/p/one", sid=A.replace("a", "b"))
        saved = CC["PROJECTS_DIR"]
        CC["PROJECTS_DIR"] = projects
        try:
            got = sorted(x["cwd"] for x in CC["scan_dirs"]())
        finally:
            CC["PROJECTS_DIR"] = saved
        assert got == ["/", "/p/one"], got


def test_a_directory_without_any_cwd_is_still_dropped():
    # Оговорка про корень не отменяет отсева: каталог, в транскриптах
    # которого cwd нет вовсе, читать нечем — и он по-прежнему выбрасывается.
    with tempfile.TemporaryDirectory() as tmp:
        projects = os.path.join(tmp, "projects")
        d = os.path.join(projects, "-broken")
        os.makedirs(d)
        with open(os.path.join(d, A + ".jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user"}) + "\n")
        saved = CC["PROJECTS_DIR"]
        CC["PROJECTS_DIR"] = projects
        try:
            got = CC["scan_dirs"]()
        finally:
            CC["PROJECTS_DIR"] = saved
        assert got == [], got


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
