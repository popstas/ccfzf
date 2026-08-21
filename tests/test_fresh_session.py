"""Живая сессия, у которой транскрипта ещё нет.

Файл `<id>.jsonl` заводит не старт сессии, а первая запись в ход: между
запуском `claude` и первым промптом человека транскрипта не существует вовсе.
Список же собирается из файлов, поэтому такая сессия не попадала в него ничем
— ни строкой, ни живостью, — а её процесс, у которого нет id в argv, уходил
гадать по каталогу (`fresh_ids`) и в лучшем случае не находил ничего, а в
худшем забирал чужой транскрипт.

Обе дыры закрывает реестр `~/.claude/sessions/<pid>.json`: его пишет сам агент
в момент старта, и в нём назван и id, и каталог, и имя.

Запуск: python3 tests/test_fresh_session.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "bbbbbbbb-1111-2222-3333-444444444444"


def _dir(records):
    """Каталог реестра из списка (имя файла, запись)."""
    d = tempfile.mkdtemp()
    for name, body in records:
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(body if isinstance(body, str) else json.dumps(body))
    return d


def _record(pid, sid, cwd="/p", **extra):
    rec = {"pid": pid, "sessionId": sid, "cwd": cwd,
           "procStart": "111", "kind": "interactive"}
    rec.update(extra)
    return rec


# ── Кто чем занят, по словам самого агента ─────────────────────────────────


def test_the_registry_is_indexed_by_pid():
    d = _dir([("10.json", _record(10, UUID_A, name="one"))])
    assert CC["registry_by_pid"](d) == {
        10: {"sid": UUID_A, "cwd": "/p", "name": "one"},
    }


def test_a_record_without_a_name_reads_as_nameless():
    """Имя необязательно: у прежних версий агента его в записи нет вовсе,
    а строка без заголовка уже бывает и живёт."""
    d = _dir([("10.json", _record(10, UUID_A))])
    assert CC["registry_by_pid"](d)[10]["name"] == ""


def test_the_claim_takes_the_id_when_the_directory_matches():
    by_pid = CC["registry_by_pid"](_dir([("10.json", _record(10, UUID_A))]))
    assert CC["registry_claim"](10, "/p", by_pid) == UUID_A


def test_the_claim_takes_a_pid_given_as_a_string():
    """`all_pids()` отдаёт имена каталогов /proc, то есть строки, а реестр
    ключуется числом. Несовпадение типов здесь молчит: запись просто не
    находится, и сессия уходит гадать по каталогу как прежде."""
    by_pid = CC["registry_by_pid"](_dir([("10.json", _record(10, UUID_A))]))
    assert CC["registry_claim"]("10", "/p", by_pid) == UUID_A


def test_the_claim_is_silent_for_a_pid_that_is_not_a_number():
    by_pid = CC["registry_by_pid"](_dir([("10.json", _record(10, UUID_A))]))
    assert CC["registry_claim"]("", "/p", by_pid) == ""


def test_the_claim_is_silent_when_the_directory_differs():
    """Реестр за собой никто не чистит, а номера переиспользуются: запись
    вчерашнего покойника совпала бы с сегодняшним процессом по одному лишь
    номеру. Каталог мы всё равно читаем — ради `fresh_ids`."""
    by_pid = CC["registry_by_pid"](_dir([("10.json", _record(10, UUID_A))]))
    assert CC["registry_claim"](10, "/other", by_pid) == ""


def test_the_claim_is_silent_for_a_process_the_registry_does_not_know():
    """Прежние версии агента реестра не вели вовсе, и на такой машине
    единственной дорогой остаётся прежняя догадка по каталогу."""
    by_pid = CC["registry_by_pid"](_dir([("10.json", _record(10, UUID_A))]))
    assert CC["registry_claim"](11, "/p", by_pid) == ""


def test_the_claim_is_silent_without_a_directory():
    """Каталог процесса читается не всегда, и пустота не должна совпасть
    с пустотой в записи."""
    by_pid = CC["registry_by_pid"](_dir([("10.json", _record(10, UUID_A, cwd="/p"))]))
    assert CC["registry_claim"](10, "", by_pid) == ""


# ── Строка сессии, у которой файла ещё нет ────────────────────────────────


def _procs(sid, pid=10, cwd="/p"):
    return {sid: {"pid": pid, "tty": "", "tmux": None, "zellij": None, "cwd": cwd}}


def _by_pid(pid=10, sid=UUID_A, cwd="/p", name="one"):
    return {pid: {"sid": sid, "cwd": cwd, "name": name}}


def test_a_session_without_a_transcript_gets_a_row():
    rows = CC["fileless_sessions"](_by_pid(), _procs(UUID_A), set(),
                                   created_of=lambda pid: 1700)
    assert [r[0] for r in rows] == [
        os.path.join(CC["PROJECTS_DIR"], CC["mangle"]("/p"), UUID_A + ".jsonl"),
    ], rows


def test_the_row_is_dated_by_the_birth_of_its_process():
    """Своего времени у сессии без файла нет, а рождение процесса и есть
    её начало — тем же читателем, каким датируется зелийная строка."""
    rows = CC["fileless_sessions"](_by_pid(), _procs(UUID_A), set(),
                                   created_of=lambda pid: 1700)
    assert rows[0][1] == 1700, rows


def test_the_row_carries_the_directory_and_the_registry_name():
    rows = CC["fileless_sessions"](_by_pid(), _procs(UUID_A), set(),
                                   created_of=lambda pid: 1700)
    assert rows[0][2] == "/p", rows
    assert rows[0][3] == "one", rows


def test_a_session_whose_transcript_exists_gets_no_second_row():
    """Первая же запись в ход заводит файл, и строка обязана переехать в
    обычную ветку целиком, а не встать рядом двойником."""
    rows = CC["fileless_sessions"](_by_pid(), _procs(UUID_A), {UUID_A},
                                   created_of=lambda pid: 1700)
    assert rows == [], rows


def test_a_registry_record_whose_process_is_not_running_gets_no_row():
    """Живость здесь не спрашивается отдельно и не сверяется `procStart`:
    в `procs` попадают только те процессы, которые обход нашёл сам."""
    rows = CC["fileless_sessions"](_by_pid(), {}, set(),
                                   created_of=lambda pid: 1700)
    assert rows == [], rows


def test_a_record_the_process_was_not_attributed_to_gets_no_row():
    """Тот же pid, но обход отдал его другой сессии — переезд по хуку
    (`reattribute_by_pid`) знает про смену id на ходу, а реестр отстаёт."""
    rows = CC["fileless_sessions"](_by_pid(), _procs(UUID_B), set(),
                                   created_of=lambda pid: 1700)
    assert rows == [], rows


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
