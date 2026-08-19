"""Комментарии к сессиям — общий список на машине агрегатора.

Запуск: python3 tests/test_comments.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccfzf")
SID = "aaaaaaaa-1111-2222-3333-444444444444"
OTHER = "bbbbbbbb-1111-2222-3333-444444444444"


def test_a_comment_is_written_and_read_back():
    # Файл живёт на машине агрегатора, а её пикеры всех машин уже читают по
    # ssh: общим список выходит сам, без второго транспорта.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.json")
        CC["set_comment"](p, SID, "чинит окна", 100.0, "mac")
        got = CC["read_comments"](p)
        assert got == {SID: {"text": "чинит окна", "at": 100.0, "host": "mac"}}, got


def test_an_empty_comment_removes_the_entry():
    # Иначе убрать комментарий было бы нечем: отдельного «удалить» у него нет,
    # и пустая строка — единственный жест, который человек делает сам.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.json")
        CC["set_comment"](p, SID, "чинит окна", 100.0, "mac")
        CC["set_comment"](p, SID, "   ", 200.0, "mac")
        assert CC["read_comments"](p) == {}


def test_writing_one_comment_keeps_the_others():
    # Файл общий, и пишут в него с разных машин. Перезапись целиком стирала бы
    # чужие записи молча.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.json")
        CC["set_comment"](p, SID, "раз", 100.0, "mac")
        CC["set_comment"](p, OTHER, "два", 101.0, "pc")
        got = CC["read_comments"](p)
        assert set(got) == {SID, OTHER}, got
        assert got[OTHER]["host"] == "pc", got


def test_only_a_session_id_is_accepted():
    # Ключ уезжает в имя поля json и приезжает обратно на чужую машину. Чужая
    # строка вместо id — не «странная запись», а мусор, который потом некому
    # опознать.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.json")
        assert CC["set_comment"](p, "../../etc/passwd", "нет", 100.0, "mac") is False
        assert CC["read_comments"](p) == {}


def test_a_long_comment_is_cut():
    # «3–4 слова» — так задумано, но пишет человек, и предел нужен файлу, а не
    # ему: строка приезжает в список на каждой машине.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.json")
        CC["set_comment"](p, SID, "я" * 500, 100.0, "mac")
        assert len(CC["read_comments"](p)[SID]["text"]) == 200


def test_a_missing_or_broken_file_reads_empty():
    # Ни ошибки, ни падения: файла нет до первого комментария, а испорченный
    # не должен уносить с собой весь ответ --state.
    with tempfile.TemporaryDirectory() as d:
        assert CC["read_comments"](os.path.join(d, "нет.json")) == {}
        p = os.path.join(d, "bad.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{не json")
        assert CC["read_comments"](p) == {}


def test_entries_that_are_not_shaped_right_are_dropped():
    # Файл приезжает с чужой машины и пишется чужой версией ccfzf: разбор
    # белым списком, как у записи окна.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({SID: {"text": "ок", "at": 1, "host": "mac"},
                       OTHER: "просто строка",
                       "не-id": {"text": "ок"}}, fh)
        assert list(CC["read_comments"](p)) == [SID]


def test_a_comment_does_not_need_fzf():
    # Интерфейса тут нет вовсе, и fzf режиму не нужен ничем — а проверка
    # зависимостей требовала его заодно с интерактивной веткой. Ловилось это
    # только на машине без fzf: на маке ccfzf распакован пикером ради `--state`
    # (тому хватает python3), и комментарий к местной сессии падал
    # `ccfzf: fzf not found` с кодом 127 — молча для пикера, потому что читает
    # он только код возврата.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.json")
        # PATH без fzf, но с python3: имитируем ровно ту машину. Каталог самого
        # python3 берётся из его настоящего расположения — жёсткий /usr/bin на
        # маке с homebrew-питоном ничего бы не доказал.
        keep = [os.path.dirname(shutil.which("python3")), "/usr/bin", "/bin"]
        env = dict(os.environ, PATH=os.pathsep.join(keep), CCFZF_COMMENTS_FILE=p)
        assert shutil.which("fzf", path=env["PATH"]) is None, env["PATH"]
        r = subprocess.run(["bash", SRC, "--comment", SID, "mac"],
                           input="без fzf", capture_output=True, text=True, env=env)
        assert r.returncode == 0, (r.returncode, r.stderr)
        assert CC["read_comments"](p)[SID]["text"] == "без fzf", CC["read_comments"](p)


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
