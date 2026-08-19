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
    """read_windows принимает путь, поэтому файл каждому тесту пишется свой.
    Отдаёт первые четыре значения: проекты спрашивает _read_projects."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "windows.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return CC["read_windows"](path, now)[:4]


def _read_projects(obj, now=NOW):
    """Пятое значение read_windows. Отдельным помощником: прежние тесты
    распаковывают четыре, и переписывать их ради нового поля незачем."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "windows.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return CC["read_windows"](path, now)[4]


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


def test_terminal_name_reaches_the_reader():
    # Имя приложения — единственное, чем читатель отличает Windows Terminal от
    # WezTerm в строке: окно есть у обоих, и пометка ▣ у них одна и та же.
    windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": 1,
                                       "lastSeen": NOW, "app": "WindowsTerminal.exe"}))
    assert windows[UUID_A]["app"] == "WindowsTerminal.exe", windows[UUID_A]


def test_terminal_name_missing_is_empty_not_absent():
    # Трекер прежней версии поля не пишет. Пустая строка читается как «не
    # назвал», а отсутствие ключа стоило бы читателю проверки на каждом
    # использовании — то же правило, что у focusedAt.
    windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": None, "lastSeen": 0}))
    assert windows[UUID_A]["app"] == "", windows[UUID_A]


def test_junk_terminal_name_does_not_cost_the_window():
    # Файл пишет чужая машина: порченое поле стоит поля, а не пометки об окне.
    windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": 1,
                                       "lastSeen": NOW, "app": {"нет": "строки"}}))
    assert windows[UUID_A]["app"] == "", windows[UUID_A]
    assert windows[UUID_A]["title"] == "ccfzf", windows[UUID_A]


def test_minimized_reaches_the_reader():
    # Свёрнутость видит только трекер: у читателя окон нет вовсе, а гасить по
    # ней строку и выкидывать её из раскладки — его работа.
    windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": 1,
                                       "lastSeen": NOW, "minimized": True}))
    assert windows[UUID_A]["minimized"] is True, windows[UUID_A]


def test_minimized_missing_is_false_not_absent():
    # Трекер прежней версии поля не пишет. `false` читается как «окно
    # обычное», а отсутствие ключа стоило бы читателю проверки на каждом
    # использовании — то же правило, что у focusedAt и app.
    windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": None, "lastSeen": 0}))
    assert windows[UUID_A]["minimized"] is False, windows[UUID_A]


def test_junk_minimized_reads_as_an_ordinary_window():
    # Файл пишет чужая машина. Ошибиться можно в обе стороны, и стороны эти
    # неравны: гашёная строка у открытого окна уводит человека от работающей
    # сессии, а негашёная у свёрнутого стоит одного лишнего взгляда.
    for junk in ("true", 1, {"да": "нет"}, [], None):
        windows, _, _, _ = _read(_payload({"title": "ccfzf", "desktop": 1,
                                           "lastSeen": NOW, "minimized": junk}))
        assert windows[UUID_A]["minimized"] is False, (junk, windows[UUID_A])
        assert windows[UUID_A]["title"] == "ccfzf", (junk, windows[UUID_A])


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


def test_project_hotkeys_reach_the_reader():
    # Единственный источник хоткеев — конфиг windows11-manager, и другого пути
    # к читателю у них нет: пикер про менеджер не знает ничего.
    payload = _payload({"title": "ccfzf", "desktop": 1, "lastSeen": NOW - 5})
    payload["projects"] = [{"cwd": "/p/home", "name": "home", "hotkey": "Ctrl+F11"}]
    assert _read_projects(payload) == [
        {"cwd": "/p/home", "name": "home", "hotkey": "Ctrl+F11"}], _read_projects(payload)


def test_junk_projects_cost_the_field_not_the_list():
    # Правило то же, что у окон и снимков: порченая добавка не стоит списка
    # сессий. Запись без cwd или без хоткея не значит ничего.
    payload = _payload({"title": "ccfzf", "desktop": 1, "lastSeen": NOW - 5})
    payload["projects"] = ["not a dict", {"cwd": "/p/one"}, {"hotkey": "Ctrl+F1"},
                           {"cwd": "/p/two", "hotkey": "Ctrl+F2"}]
    assert _read_projects(payload) == [
        {"cwd": "/p/two", "name": "", "hotkey": "Ctrl+F2"}], _read_projects(payload)


def test_projects_missing_is_empty_list():
    # Старый трекер про хоткеи не знает, и это не ошибка.
    assert _read_projects(_payload({"title": "ccfzf", "desktop": 1, "lastSeen": 0})) == []


def test_stale_file_gives_no_projects_either():
    # Протухший файл гасит хоткеи тем же порогом, что и окна: второго таймера
    # у них нет.
    payload = {"generated": NOW - 10_000, "host": "pc", "pid": 42,
               "windows": {UUID_A: {"title": "ccfzf", "desktop": 1}},
               "projects": [{"cwd": "/p/home", "name": "home", "hotkey": "Ctrl+F11"}]}
    assert _read_projects(payload) == []


def _read_focus(obj, now=NOW):
    """Шестое значение read_windows: умеет ли этот трекер поднимать окно."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "windows.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return CC["read_windows"](path, now)[5]


def test_focus_flag_absent_means_able():
    # Трекер прежней версии поля не пишет, а поднимать окна умеет и умел
    # всегда. Прочитать его отсутствие как «не умеет» значило бы выключить
    # подъём на Windows правкой, которая Windows не касается вовсе.
    assert _read_focus(_payload({"title": "ccfzf", "desktop": None, "lastSeen": 0})) is True


def test_focus_flag_false_is_respected():
    # Трекер, который окон не поднимает, говорит об этом сам. Без этого поля
    # заполненное имя машины в конфиге пикера включало бы ветку подъёма, и
    # просьба уезжала бы менеджеру на другой машине.
    payload = _payload({"title": "ccfzf", "desktop": None, "lastSeen": 0})
    payload["focus"] = False
    assert _read_focus(payload) is False


def test_focus_garbage_reads_as_able():
    # Недоверие к файлу здесь то же, что к остальным полям: мусор стоит себя,
    # а не ветки поведения. «Умеет» — то же умолчание, что и у отсутствия.
    for junk in ["no", 0, None, {}, []]:
        payload = _payload({"title": "ccfzf", "desktop": None, "lastSeen": 0})
        payload["focus"] = junk
        assert _read_focus(payload) is True, junk


def _read_caps(obj, now=NOW):
    """Седьмое и восьмое значения read_windows: берётся ли менеджер этой машины
    открывать сессии и по какому адресу его просить. Отдельным помощником, как
    и _read_projects: прежние тесты распаковывают четыре значения, и
    переписывать их ради новых полей незачем."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "windows.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        out = CC["read_windows"](path, now)
        return out[6], out[7]


def test_mqtt_base_reaches_the_reader():
    # Адрес, по которому у этой машины просят поднять окно. Знать его отсюда
    # неоткуда: топик живёт в конфиге трекера, а публикует читатель.
    payload = _payload({"title": "ccfzf", "desktop": None, "lastSeen": 0})
    payload["mqttBase"] = "home/room/mac/windows"
    _, base = _read_caps(payload)
    assert base == "home/room/mac/windows", base


def test_mqtt_base_missing_is_empty_not_absent():
    # Windows-трекер поля не пишет и не должен: пустая строка значит «спроси
    # свой конфиг», и читатель ведёт себя как до появления поля.
    _, base = _read_caps(_payload({"title": "ccfzf", "desktop": None, "lastSeen": 0}))
    assert base == "", base


def test_junk_mqtt_base_reads_as_missing():
    # Недоверие к файлу то же, что у остальных полей: мусор стоит поля, а не
    # списка окон.
    payload = _payload({"title": "ccfzf", "desktop": None, "lastSeen": 0})
    payload["mqttBase"] = 17
    _, base = _read_caps(payload)
    assert base == "", base


def test_open_session_defaults_to_yes():
    # Отсутствие поля — «берётся»: windows11-manager его не пишет и не должен,
    # открытие сессий там работало всегда.
    opens, _ = _read_caps(_payload({"title": "ccfzf", "desktop": None, "lastSeen": 0}))
    assert opens is True, opens


def test_open_session_can_say_no():
    # Мак сессий не открывает — их открывает сам пикер. Без этого признака
    # пикер на маке назначил бы менеджером мак и получил молчащий Enter.
    payload = _payload({"title": "ccfzf", "desktop": None, "lastSeen": 0})
    payload["openSession"] = False
    opens, _ = _read_caps(payload)
    assert opens is False, opens


def test_junk_open_session_reads_as_yes():
    payload = _payload({"title": "ccfzf", "desktop": None, "lastSeen": 0})
    payload["openSession"] = "нет"
    opens, _ = _read_caps(payload)
    assert opens is True, opens


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
