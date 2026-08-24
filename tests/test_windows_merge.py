"""Слияние нескольких файлов трекеров. Запуск: python3 tests/test_windows_merge.py"""
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


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def _file(host, windows, pid=42, focus=None, projects=None, snapshots=None,
          open_session=None, mqtt_base=None, http=None):
    out = {"generated": NOW - 1, "host": host, "pid": pid, "windows": windows}
    if focus is not None:
        out["focus"] = focus
    if projects is not None:
        out["projects"] = projects
    if snapshots is not None:
        out["snapshots"] = snapshots
    if open_session is not None:
        out["openSession"] = open_session
    if mqtt_base is not None:
        out["mqttBase"] = mqtt_base
    if http is not None:
        out["http"] = http
    return out


def _win(title, last_seen=NOW - 5):
    return {"title": title, "desktop": None, "lastSeen": last_seen, "focusedAt": 0}


def _merge(legacy=None, dir_files=None, now=NOW):
    """read_window_sources принимает путь к файлу и путь к каталогу."""
    with tempfile.TemporaryDirectory() as d:
        file_path = ""
        if legacy is not None:
            file_path = os.path.join(d, "legacy.json")
            _write(file_path, legacy)
        dir_path = os.path.join(d, "windows")
        os.makedirs(dir_path)
        for name, obj in (dir_files or {}).items():
            _write(os.path.join(dir_path, name), obj)
        return CC["read_window_sources"](file_path, dir_path, now)


def test_windows_from_two_trackers_land_in_one_map():
    # Ради этого всё и затевается: две машины, один список. Без слияния окна
    # второго трекера не видны никому — поле `window` есть только у сессий с
    # окнами того трекера, чей файл прочитали единственным.
    windows, _, _, _, _, _ = _merge(
        legacy=_file("windows-box", {UUID_A: _win("ccfzf")}),
        dir_files={"mac-host.json": _file("mac-host", {UUID_B: _win("other")}, pid=7)},
    )
    assert set(windows) == {UUID_A, UUID_B}, windows
    assert windows[UUID_A][0]["host"] == "windows-box", windows[UUID_A]
    assert windows[UUID_B][0]["host"] == "mac-host", windows[UUID_B]
    assert windows[UUID_B][0]["pid"] == 7, windows[UUID_B]


def test_two_windows_of_one_session_are_kept_newest_look_first():
    # Ровно нынешняя гонка, записанная тестом: у windows-box запись свежее по
    # `lastSeen` (его демон тикнул только что), но на окно ни разу не смотрели;
    # у mac-host тик старее, а взгляд был. Побеждает взгляд — он отметка
    # человека, а `lastSeen` отметка трекера.
    windows, _, _, _, _, _ = _merge(
        legacy=_file("windows-box", {UUID_A: dict(_win("ccfzf", NOW - 2), focusedAt=0)}),
        dir_files={"mac.json": _file(
            "mac-host", {UUID_A: dict(_win("ccfzf", NOW - 40), focusedAt=NOW - 60)})},
    )
    assert [w["host"] for w in windows[UUID_A]] == ["mac-host", "windows-box"], windows[UUID_A]


def test_windows_order_is_stable_when_keys_are_equal():
    # На два окна, на которые не смотрели ни разу и чьи трекеры тикнули в одну
    # секунду, первых двух ключей не хватает. Без третьего порядок зависел бы
    # от порядка чтения файлов, а читатель перерисовывает список раз в секунду —
    # дрожь была бы видна глазом.
    windows, _, _, _, _, _ = _merge(
        legacy=_file("zeta-box", {UUID_A: _win("ccfzf")}),
        dir_files={"alpha.json": _file("alpha-box", {UUID_A: _win("ccfzf")})},
    )
    assert [w["host"] for w in windows[UUID_A]] == ["alpha-box", "zeta-box"], windows[UUID_A]


def test_window_carries_focus_ability_of_its_own_tracker():
    # Машина строки и умение её трекера — разные вопросы, и оба нужны построчно.
    # Одно верхнее поле на весь ответ не отвечает ни на один из них.
    windows, _, _, _, _, _ = _merge(
        legacy=_file("windows-box", {UUID_A: _win("ccfzf")}),
        dir_files={"mac-host.json": _file("mac-host", {UUID_B: _win("other")}, focus=False)},
    )
    assert windows[UUID_A][0]["canFocus"] is True, windows[UUID_A]
    assert windows[UUID_B][0]["canFocus"] is False, windows[UUID_B]


def test_same_session_in_two_trackers_goes_to_the_fresher_one():
    # Одна сессия, открытая с обеих машин. Спор разрешается свежестью, а не
    # порядком чтения: порядок задан нами и о том, где сессию видели последней,
    # не знает ничего.
    windows, _, _, _, _, _ = _merge(
        legacy=_file("windows-box", {UUID_A: _win("ccfzf", last_seen=NOW - 90)}),
        dir_files={"mac-host.json": _file("mac-host", {UUID_A: _win("ccfzf", last_seen=NOW - 2)})},
    )
    assert windows[UUID_A][0]["host"] == "mac-host", windows[UUID_A]


def test_stale_source_drops_whole_and_alone():
    # Протухший файл выбрасывается целиком и в одиночку: соседний трекер жив, и
    # его окна обязаны пережить смерть чужого демона.
    stale = _file("windows-box", {UUID_A: _win("ccfzf")})
    stale["generated"] = NOW - 100000
    windows, _, _, _, _, hosts = _merge(
        legacy=stale,
        dir_files={"mac-host.json": _file("mac-host", {UUID_B: _win("other")})},
    )
    assert set(windows) == {UUID_B}, windows
    assert [h["host"] for h in hosts] == ["mac-host"], hosts


def test_hosts_list_names_every_live_tracker():
    # Пикеру нужно отличать «моей машины среди трекеров нет» от «есть, но окон
    # у неё сейчас нет». По окнам этого не понять: у здорового трекера без
    # открытых терминалов список окон пуст.
    _, _, _, _, _, hosts = _merge(
        legacy=_file("windows-box", {UUID_A: _win("ccfzf")}),
        dir_files={"mac-host.json": _file("mac-host", {}, pid=7, focus=False)},
    )
    assert hosts == [
        {"host": "windows-box", "pid": 42, "canFocus": True,
         "openSession": True, "mqttBase": "", "http": None},
        {"host": "mac-host", "pid": 7, "canFocus": False,
         "openSession": True, "mqttBase": "", "http": None},
    ], hosts


def test_http_endpoint_reaches_the_host_record():
    # Ради этого поля вся правка: по нему читатель решает, идти ли напрямую.
    # Живёт оно в записи машины, а не окна: адрес — свойство машины, и у строки
    # проекта окна нет вовсе, а спросить «куда просить» надо и про неё.
    _, _, _, _, _, hosts = _merge(
        legacy=_file("windows-box", {UUID_A: _win("ccfzf")}, http={"port": 9722}),
    )
    assert hosts[0]["http"] == {"port": 9722}, hosts


def test_missing_http_reads_as_no_endpoint():
    # Трекер прежней версии его не пишет вовсе, и это обязано читаться как
    # «адреса не знаю» — читатель тогда откатывается на MQTT, как раньше.
    _, _, _, _, _, hosts = _merge(
        legacy=_file("windows-box", {UUID_A: _win("ccfzf")}),
    )
    assert hosts[0]["http"] is None, hosts


def test_junk_http_reads_as_no_endpoint():
    # Недоверие к файлу такое же, как к остальным полям: третьей ветки
    # поведения мусор не заводит.
    for junk in ["9722", {"port": "9722"}, {"port": 0}, {}, 17, None]:
        _, _, _, _, _, hosts = _merge(
            legacy=_file("windows-box", {UUID_A: _win("ccfzf")}, http=junk),
        )
        assert hosts[0]["http"] is None, (junk, hosts)


def test_top_level_fields_follow_the_tracker_that_has_hotkeys():
    # Верхние windowHost/windowPid/projects кормят проектные хоткеи, и пикер
    # сверяет с ними своё имя. Взять их у первого попавшегося источника значило
    # бы, что клавиши пропадают, стоит соседнему трекеру подняться раньше.
    _, host, pid, _, projects, _ = _merge(
        legacy=_file("mac-host", {}, pid=7),
        dir_files={"windows-box.json": _file(
            "windows-box", {UUID_A: _win("ccfzf")}, pid=42,
            projects=[{"cwd": "/projects/js/ccfzf-picker", "name": "picker", "hotkey": "Ctrl+F11"}])},
    )
    assert host == "windows-box" and pid == 42, (host, pid)
    assert [p["hotkey"] for p in projects] == ["Ctrl+F11"], projects


def test_missing_directory_is_not_an_error():
    # Каталога может не быть вовсе — на машине, где никто не переезжал на новую
    # схему. Это норма, а не отказ: единственный файл остаётся источником.
    with tempfile.TemporaryDirectory() as d:
        file_path = os.path.join(d, "legacy.json")
        _write(file_path, _file("windows-box", {UUID_A: _win("ccfzf")}))
        windows, host, _, _, _, _ = CC["read_window_sources"](
            file_path, os.path.join(d, "nope"), NOW)
    assert set(windows) == {UUID_A} and host == "windows-box", (windows, host)


def test_sources_are_ordered_file_then_directory_by_name():
    # Порядок задан, а не случаен: из него берутся верхние поля ответа, и без
    # него они прыгали бы от запуска к запуску.
    with tempfile.TemporaryDirectory() as d:
        dir_path = os.path.join(d, "windows")
        os.makedirs(dir_path)
        for name in ["b.json", "a.json", "skip.txt"]:
            _write(os.path.join(dir_path, name), {})
        got = CC["window_sources"](os.path.join(d, "legacy.json"), dir_path)
    assert [os.path.basename(p) for p in got] == ["legacy.json", "a.json", "b.json"], got


def test_window_carries_the_address_of_its_own_tracker():
    # Подъём просят у той машины, где стоит окно, а адрес у каждой свой.
    # Верхнего поля тут не хватило бы: оно называет одну машину, а окна
    # приезжают от нескольких.
    windows, _, _, _, _, _ = _merge(
        legacy=_file("windows-box", {UUID_A: _win("ccfzf")},
                     mqtt_base="home/room/pc/windows"),
        dir_files={"mac-host.json": _file("mac-host", {UUID_B: _win("other")},
                                          mqtt_base="home/room/mac/windows")},
    )
    assert windows[UUID_A][0]["mqttBase"] == "home/room/pc/windows", windows[UUID_A]
    assert windows[UUID_B][0]["mqttBase"] == "home/room/mac/windows", windows[UUID_B]


def test_tracker_list_carries_address_and_open_ability():
    # Кто откроет терминал — вопрос про машину, и задаётся он этому списку.
    # У записи окна `openSession` не значил бы ничего: у строки проекта окна
    # нет вовсе, а спросить надо и про неё.
    _, _, _, _, _, hosts = _merge(
        legacy=_file("windows-box", {}, pid=42),
        dir_files={"mac-host.json": _file("mac-host", {}, pid=7,
                                          open_session=False,
                                          mqtt_base="home/room/mac/windows")},
    )
    assert hosts == [
        {"host": "windows-box", "pid": 42, "canFocus": True,
         "openSession": True, "mqttBase": "", "http": None},
        {"host": "mac-host", "pid": 7, "canFocus": True,
         "openSession": False, "mqttBase": "home/room/mac/windows", "http": None},
    ], hosts


def test_snapshot_carries_the_machine_that_took_it():
    # Восстанавливают снимок на той машине, где его сняли. Плоский список без
    # владельца заставил бы пикер угадывать — а промах здесь молчащий: у
    # публикации нет ответа.
    snap_pc = [{"id": "2026-08-14T01-00-00", "created": 100,
                "sessions": [{"id": UUID_A, "title": "ccfzf", "cwd": "/x"}]}]
    snap_mac = [{"id": "2026-08-14T02-00-00", "created": 200,
                 "sessions": [{"id": UUID_B, "title": "other", "cwd": "/y"}]}]
    _, _, _, snaps, _, _ = _merge(
        legacy=_file("windows-box", {}, snapshots=snap_pc),
        dir_files={"mac-host.json": _file("mac-host", {}, snapshots=snap_mac,
                                          mqtt_base="home/room/mac/windows")},
    )
    by_id = {s["id"]: s for s in snaps}
    assert by_id["2026-08-14T01-00-00"]["host"] == "windows-box", snaps
    assert by_id["2026-08-14T01-00-00"]["mqttBase"] == "", snaps
    assert by_id["2026-08-14T02-00-00"]["host"] == "mac-host", snaps
    assert by_id["2026-08-14T02-00-00"]["mqttBase"] == "home/room/mac/windows", snaps


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print("ok", name)
