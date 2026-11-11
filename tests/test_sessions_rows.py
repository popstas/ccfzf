"""Строки интерактивного списка сессий. Запуск: python3 tests/test_sessions_rows.py

Режим `sessions` — единственный, чей ответ читает не программа, а fzf, и
единственный, который до сих пор не был ничем накрыт. Стоило это дорого:
`tail_facts` со временем стала отдавать четыре значения вместо двух, все
остальные её вызовы поправили, а этот — нет, и список сессий падал
`ValueError: too many values to unpack` сразу после выбора проекта. Bash над
ним стоит под `set -e`, так что человек видел не ошибку, а мгновенный выход
в шелл.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness


def msg(text, role="user"):
    return {"type": role, "timestamp": "2026-08-18T10:00:00Z",
            "message": {"role": role, "content": [{"type": "text", "text": text}]}}


def setup(d, lines):
    """Проект с одной сессией: транскрипт, индекс и пустые метки."""
    proj = os.path.join(d, "proj")
    os.makedirs(proj)
    sess = os.path.join(d, "0000-1111.jsonl")
    with open(sess, "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o) + "\n")
    index = os.path.join(d, "index.json")
    with open(index, "w", encoding="utf-8") as fh:
        json.dump({"dirs": [{"cwd": proj, "files": [[sess, os.path.getsize(sess)]]}],
                   "live": []}, fh)
    marks = os.path.join(d, "marks")
    open(marks, "w").close()
    preview = os.path.join(d, "preview")
    os.makedirs(preview)
    return ["sessions", proj, preview, marks, index, "[]", "ctrl-d"], proj, preview


def test_a_session_gets_a_row():
    with tempfile.TemporaryDirectory() as d:
        argv, proj, _ = setup(d, [
            {"type": "custom-title", "customTitle": "Заголовок"},
            msg("первая просьба человека"),
        ])
        out, err = harness.run(argv)
        rows = [r.split("\t") for r in out.splitlines()]
        mine = [r for r in rows if r[0] == "0000-1111"]
        assert len(mine) == 1, out
        assert mine[0][1] == proj, mine
        assert "Заголовок" in mine[0][2], mine
        assert err.strip().splitlines()[-1] == "1", err


def test_the_service_rows_come_first():
    # Их три плюс по одной на настроенную команду проекта, и порядок этот
    # видит человек: новая сессия сверху, shell снизу.
    with tempfile.TemporaryDirectory() as d:
        argv, proj, _ = setup(d, [msg("привет")])
        argv[5] = '[["codex","ctrl-s"]]'
        out, _ = harness.run(argv)
        ids = [r.split("\t")[0] for r in out.splitlines()]
        assert ids[:4] == ["__new__", "__cmd1__", "__shell__", "0000-1111"], ids


def test_every_row_gets_a_preview_file():
    # fzf показывает превью командой `cat $tmp/{1}.txt`: строка без файла —
    # пустая панель под курсором.
    with tempfile.TemporaryDirectory() as d:
        argv, proj, preview = setup(d, [msg("первая просьба человека")])
        out, _ = harness.run(argv)
        for row in out.splitlines():
            sid = row.split("\t")[0]
            assert os.path.exists(os.path.join(preview, sid + ".txt")), sid


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
