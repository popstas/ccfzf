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


def _payload(win):
    return {"generated": NOW - 1, "host": "pc", "pid": 42, "windows": {UUID_A: win}}


def test_focused_at_reaches_the_reader():
    # Отметку «человек посмотрел на окно» ставит трекер: у читателя окон нет
    # вовсе, и без неё его список зовёт к сессии, на которую уже сходили.
    windows, host, pid = _read(_payload({"title": "ccfzf", "desktop": 2,
                                         "lastSeen": NOW - 5, "focusedAt": NOW - 9}))
    assert windows[UUID_A]["focusedAt"] == NOW - 9, windows[UUID_A]
    assert host == "pc" and pid == 42, (host, pid)


def test_focus_stamp_missing_is_zero_not_absent():
    # Трекер прежней версии поля не пишет. Ноль читается как «не смотрели», а
    # отсутствие ключа стоило бы читателю проверки на каждом использовании.
    windows, _, _ = _read(_payload({"title": "ccfzf", "desktop": None, "lastSeen": 0}))
    assert windows[UUID_A]["focusedAt"] == 0, windows[UUID_A]


def test_junk_focus_stamp_does_not_cost_the_window():
    # Пометка об окне дороже отметки о просмотре: мусор в одном поле не повод
    # терять запись целиком.
    windows, _, _ = _read(_payload({"title": "ccfzf", "desktop": 1,
                                    "lastSeen": NOW, "focusedAt": "вчера"}))
    assert windows[UUID_A]["focusedAt"] == 0, windows[UUID_A]
    assert windows[UUID_A]["title"] == "ccfzf", windows[UUID_A]


def test_stale_file_is_dropped_whole():
    # Срок годности проверяется до полей: демон, который умер, не должен
    # оставлять после себя ни пометок об окнах, ни отметок о просмотре.
    payload = _payload({"title": "ccfzf", "desktop": 1, "lastSeen": 0, "focusedAt": NOW})
    payload["generated"] = NOW - CC["WINDOWS_TTL"] - 1
    assert _read(payload) == ({}, "", 0)


def test_a_second_window_keeps_its_own_stamp():
    payload = _payload({"title": "a", "desktop": 1, "lastSeen": 0, "focusedAt": 10})
    payload["windows"][UUID_B] = {"title": "b", "desktop": 1, "lastSeen": 0, "focusedAt": 20}
    windows, _, _ = _read(payload)
    assert windows[UUID_A]["focusedAt"] == 10, windows[UUID_A]
    assert windows[UUID_B]["focusedAt"] == 20, windows[UUID_B]


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
