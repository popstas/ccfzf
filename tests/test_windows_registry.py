"""Реестр сессий Claude Code — источник связки «процесс ↔ сессия» на Windows.

Разбора процессов там нет вовсе: рабочего каталога `Win32_Process` не отдаёт,
а без него `fresh_ids` кормить нечем. Зато Claude Code сам пишет
`~/.claude/sessions/<pid>.json`, и в нём лежит всё нужное.

Запуск: python3 tests/test_windows_registry.py
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
    """Каталог реестра из списка (имя файла, содержимое)."""
    d = tempfile.mkdtemp()
    for name, body in records:
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(body if isinstance(body, str) else json.dumps(body))
    return d


def _record(pid, sid, cwd="<drive>:\\projects\\some-project", **extra):
    rec = {"pid": pid, "sessionId": sid, "cwd": cwd,
           "procStart": "134317286687059374", "kind": "interactive"}
    rec.update(extra)
    return rec


def test_a_record_is_read_whole():
    d = _dir([("10980.json", _record(10980, UUID_A))])
    assert CC["registry_records"](d) == [
        {"sid": UUID_A, "pid": 10980, "cwd": "<drive>:\\projects\\some-project",
         "procStart": "134317286687059374"},
    ]


def test_an_absent_directory_reads_as_no_sessions():
    """Пустота, а не отказ: на машине без единой местной сессии каталога нет."""
    assert CC["registry_records"]("/nonexistent-registry-for-tests") == []


def test_broken_and_foreign_files_are_skipped_one_by_one():
    """Разбор терпимый, как у файла окон: одна кривая запись не роняет ответ."""
    d = _dir([
        ("1.json", "{не json"),
        ("2.json", "[]"),
        ("3.json", _record(3, "not-a-uuid")),
        ("4.json", {"pid": 4, "sessionId": UUID_B}),
        ("5.json", _record(0, UUID_B)),
        ("6.key", "секрет"),
        ("7.json", _record(7, UUID_A)),
    ])
    assert [r["pid"] for r in CC["registry_records"](d)] == [7]


def test_a_record_without_a_start_time_is_dropped():
    """Без `procStart` живость не проверить, а «не проверили» здесь опасно:
    мёртвый процесс тоже отвечает пустотой, и запись сошлась бы с ним."""
    d = _dir([("8.json", _record(8, UUID_A, procStart=""))])
    assert CC["registry_records"](d) == []


def test_a_background_kind_is_not_a_session_here():
    """Форк не должен отобрать у родителя окно, а признака `bg-pty-host`,
    по которому его узнают на Linux, здесь нет вовсе."""
    d = _dir([("9.json", _record(9, UUID_A, kind="background"))])
    assert CC["registry_records"](d) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
