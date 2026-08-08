"""Тесты файла оконного трекера. Запуск: python3 tests/test_windows_file.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "bbbbbbbb-1111-2222-3333-444444444444"
NOW = 1785958293


def _read(obj, now=NOW):
    """read_windows принимает путь, поэтому файл каждому тесту пишется свой."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "windows.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return CC["read_windows"](path, now)


def _payload(win, snaps=None):
    out = {"generated": NOW - 1, "host": "pc", "pid": 42, "windows": {UUID_A: win}}
    if snaps is not None:
        out["snapshots"] = snaps
    return out


SNAP = {"id": "snap-1", "created": NOW - 3600,
        "sessions": [{"id": UUID_A, "title": "ccfzf", "cwd": "/home/user/projects/js/ccfzf-picker"}]}


def test_focused_at_reaches_the_reader():
    # Отметку «человек посмотрел на окно» ставит трекер: у читателя окон нет
    # вовсе, и без неё его список зовёт к сессии, на которую уже сходили.
    windows, host, pid, _ = _read(_payload({"title": "ccfzf", "desktop": 2,
                                            "lastSeen": NOW - 5, "focusedAt": NOW - 9}))
    assert windows[UUID_A]["focusedAt"] == NOW - 9, windows[UUID_A]
    assert host == "pc" and pid == 42, (host, pid)


def test_focus_stamp_missing_is_zero_not_absent():
    # Трекер прежней версии поля не пишет. Ноль читается как «не смотрели», а
    # отсутствие ключа стоило бы читателю проверки на каждом использовании.
    windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": None, "lastSeen": 0}))
    assert windows[UUID_A]["focusedAt"] == 0, windows[UUID_A]


def test_junk_focus_stamp_does_not_cost_the_window():
    # Пометка об окне дороже отметки о просмотре: мусор в одном поле не повод
    # терять запись целиком.
    windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": 1,
                                       "lastSeen": NOW, "focusedAt": "вчера"}))
    assert windows[UUID_A]["focusedAt"] == 0, windows[UUID_A]
    assert windows[UUID_A]["title"] == "ccfzf", windows[UUID_A]


def test_stale_file_is_dropped_whole():
    # Срок годности проверяется до полей: демон, который умер, не должен
    # оставлять после себя ни пометок об окнах, ни отметок о просмотре.
    payload = _payload({"title": "ccfzf", "desktop": 1, "lastSeen": 0, "focusedAt": NOW})
    payload["generated"] = NOW - CC["WINDOWS_TTL"] - 1
    assert _read(payload) == ({}, "", 0, [])


def test_a_second_window_keeps_its_own_stamp():
    payload = _payload({"title": "a", "desktop": 1, "lastSeen": 0, "focusedAt": 10})
    payload["windows"][UUID_B] = {"title": "b", "desktop": 1, "lastSeen": 0, "focusedAt": 20}
    windows, _, _, _ = _read(payload)
    assert windows[UUID_A]["focusedAt"] == 10, windows[UUID_A]
    assert windows[UUID_B]["focusedAt"] == 20, windows[UUID_B]


def test_snapshots_reach_the_reader():
    # Снимки раскладки живут на машине трекера; у читателя своего доступа к
    # ним нет, и приезжают они тем же файлом, что и окна.
    _, _, _, snaps = _read(_payload({"title": "ccfzf", "desktop": 2,
                                     "lastSeen": NOW - 5, "focusedAt": 0}, [SNAP]))
    assert len(snaps) == 1, snaps
    assert snaps[0]["id"] == "snap-1", snaps[0]
    assert snaps[0]["sessions"][0]["cwd"].endswith("ccfzf-picker"), snaps[0]


def test_snapshots_missing_is_empty_list():
    # Трекер прежней версии поля не пишет. Пустой список стоит читателю
    # дешевле, чем проверка на None при каждом использовании.
    _, _, _, snaps = _read(_payload({"title": "ccfzf", "desktop": 2,
                                     "lastSeen": NOW - 5, "focusedAt": 0}))
    assert snaps == [], snaps


def test_junk_snapshots_cost_the_field_not_the_list():
    # Порченая добавка не имеет права стоить списка сессий — это правило всей
    # read_windows, и снимки из него не исключение.
    windows, host, pid, snaps = _read(_payload(
        {"title": "ccfzf", "desktop": 2, "lastSeen": NOW - 5, "focusedAt": 0},
        "не список"))
    assert snaps == [], snaps
    assert windows[UUID_A]["title"] == "ccfzf", windows
    assert host == "pc" and pid == 42, (host, pid)


def test_snapshot_entries_are_checked_one_by_one():
    # Одна кривая запись выбрасывается, соседние остаются: снимков двадцать,
    # и терять девятнадцать из-за одной было бы обидно.
    _, _, _, snaps = _read(_payload(
        {"title": "ccfzf", "desktop": 2, "lastSeen": NOW - 5, "focusedAt": 0},
        [SNAP, {"id": 42}, {"sessions": []}, "строка"]))
    assert [s["id"] for s in snaps] == ["snap-1"], snaps


def test_sessions_inside_a_snapshot_are_checked_one_by_one():
    # Второй уровень отбраковки: снимок годен, а часть его сессий — нет.
    # Внешний уровень такую запись не увидит вовсе, и без этого теста
    # внутренний держался бы только на чтении глазами. Терять весь снимок из-за
    # одной кривой сессии — та же обида, что терять весь список из-за снимка.
    _, _, _, snaps = _read(_payload(
        {"title": "ccfzf", "desktop": 2, "lastSeen": NOW - 5, "focusedAt": 0},
        [{"id": "snap-junk", "created": NOW - 3600, "sessions": [
            {"id": UUID_A, "title": "ccfzf", "cwd": "/home/user/projects/js/ccfzf-picker"},
            {"id": 42},          # id не строка
            {"id": ""},          # id пустой — по такому окно не найти
            {"title": "нет id"},  # id вовсе нет
            "строка",            # запись не словарь
            {"id": UUID_B, "title": "второй", "cwd": "/home/user/projects/shell/ccfzf"},
        ]},
         SNAP]))
    # Соседний снимок цел, порядок сохранён.
    assert [s["id"] for s in snaps] == ["snap-junk", "snap-1"], snaps
    assert [m["id"] for m in snaps[0]["sessions"]] == [UUID_A, UUID_B], snaps[0]
    assert snaps[1]["sessions"][0]["id"] == UUID_A, snaps[1]


def test_junk_fields_of_a_snapshot_session_cost_only_themselves():
    # Правило «порченое поле стоит поля, а не записи» действует и на самом
    # нижнем уровне: сессию находят по id, и ради кривого title её терять не за
    # что. Пустая строка на месте мусора избавляет читателя от проверки типа.
    _, _, _, snaps = _read(_payload(
        {"title": "ccfzf", "desktop": 2, "lastSeen": NOW - 5, "focusedAt": 0},
        [{"id": "snap-2", "created": NOW - 60,
          "sessions": [{"id": UUID_A, "title": 7, "cwd": None}]}]))
    assert snaps[0]["sessions"] == [{"id": UUID_A, "title": "", "cwd": ""}], snaps[0]


def test_snapshot_with_junk_sessions_field_keeps_its_head():
    # `sessions` не список — это уже не «часть записей порченая», а порченое
    # поле: сам снимок остаётся, сессий у него ноль.
    _, _, _, snaps = _read(_payload(
        {"title": "ccfzf", "desktop": 2, "lastSeen": NOW - 5, "focusedAt": 0},
        [{"id": "snap-3", "created": NOW - 60, "sessions": "не список"}]))
    assert [s["id"] for s in snaps] == ["snap-3"], snaps
    assert snaps[0]["sessions"] == [], snaps[0]


def test_stale_file_gives_no_snapshots_either():
    # Правило TTL общее: протухший файл не даёт ни окон, ни снимков. Отдельной
    # ветки для снимков нет намеренно — она разошлась бы с окнами.
    windows, _, _, snaps = _read({"generated": NOW - 10_000, "host": "pc", "pid": 42,
                                  "windows": {UUID_A: {"title": "x"}},
                                  "snapshots": [SNAP]}, now=NOW)
    assert windows == {} and snaps == [], (windows, snaps)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print("ok   " + name)
        except AssertionError as e:
            fails += 1
            print("FAIL " + name + ": " + str(e))
    total = len([n for n in globals() if n.startswith("test_")])
    print("%d/%d passed" % (total - fails, total))
    sys.exit(1 if fails else 0)
