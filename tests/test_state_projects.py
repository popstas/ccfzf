"""Проекты в ответе --state. Запуск: python3 tests/test_state_projects.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()


def test_project_rows_shape_is_what_state_promises():
    # Ответ --state собирается проекцией project_rows, и имена полей в нём
    # свои: `sessions` вместо `n`. Тест сторожит саму проекцию — если у
    # project_rows переименуют ключ, здесь станет KeyError, а не тихо пустое
    # поле у читателя на другой машине.
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/a.jsonl", 1000.0)]}]
    rows = CC["project_rows"](dirs, set(), {})
    got = [{"path": r["path"], "name": r["name"], "mark": r["mark"],
            "sessions": r["n"], "live": r["live"], "mtime": r["mtime"]}
           for r in rows]
    assert got == [{"path": "/p/one", "name": "one", "mark": False,
                    "sessions": 1, "live": 0, "mtime": 1000.0}], got


def test_a_marked_project_without_sessions_is_still_listed():
    # Ради этого случая поле и добавляется: проект, где ни разу не запускали
    # claude, приходит только из marks, и по cwd сессий его не восстановить.
    rows = CC["project_rows"]([], set(), {"/p/empty": "empty"})
    assert [r["path"] for r in rows] == ["/p/empty"], rows
    assert rows[0]["n"] == 0 and rows[0]["live"] == 0, rows


def test_live_sessions_are_counted_per_project():
    sid = "aaaaaaaa-1111-2222-3333-444444444444"
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/%s.jsonl" % sid, 1000.0)]}]
    rows = CC["project_rows"](dirs, {sid}, {})
    assert rows[0]["live"] == 1, rows


def test_hotkey_sticks_to_the_row_it_belongs_to():
    # Клеится по path и только к своей строке: второй список проектов у
    # читателя завёлся бы ровно затем, чтобы разойтись с первым.
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/a.jsonl", 1000.0)]}]
    rows = CC["project_rows"](dirs, set(), {})
    out = CC["merge_project_hotkeys"](rows, [{"cwd": "/p/one", "name": "one",
                                              "hotkey": "Ctrl+F11"}])
    assert [r["path"] for r in out] == ["/p/one"], out
    assert out[0]["hotkey"] == "Ctrl+F11", out


def test_project_with_a_hotkey_and_nothing_else_gets_a_row():
    # Ради этого случая всё и делается: у проекта, в котором давно не работали,
    # ни сессий, ни закладки нет — и его хоткей пропал бы именно тогда, когда он
    # и нужен.
    out = CC["merge_project_hotkeys"]([], [{"cwd": "/p/cold", "name": "cold",
                                            "hotkey": "Ctrl+F12"}])
    assert len(out) == 1, out
    assert out[0] == {"path": "/p/cold", "name": "cold", "mark": False,
                      "n": 0, "live": 0, "mtime": 0.0, "hotkey": "Ctrl+F12"}, out


def test_rows_without_a_hotkey_keep_their_shape():
    # Строка без хоткея не должна обзавестись пустым полем: читатель отличает
    # «нет клавиши» от «клавиша пустая» только отсутствием ключа.
    rows = CC["project_rows"]([], set(), {"/p/empty": "empty"})
    out = CC["merge_project_hotkeys"](rows, [])
    assert "hotkey" not in out[0], out


def test_synthetic_hotkey_rows_sort_alongside_others_not_at_the_tail():
    # Синтетическая строка — mtime 0.0, как у мёртвой закладки без сессий; она
    # обязана встать по имени среди таких же, а не хвостом после сортировки
    # project_rows — иначе список дёргается: строки с хоткеем всегда внизу,
    # даже если по алфавиту им место наверху.
    rows = CC["project_rows"]([], set(), {"/p/zzz": "zzz"})
    out = CC["merge_project_hotkeys"](rows, [{"cwd": "/p/aaa", "name": "aaa",
                                              "hotkey": "Ctrl+F11"}])
    assert [r["path"] for r in out] == ["/p/aaa", "/p/zzz"], out


def test_a_hotkey_project_does_not_displace_the_marked_name():
    # Имя закладки человек написал сам; имя из менеджера — служебное, и
    # перебивать им закладку нельзя.
    rows = CC["project_rows"]([], set(), {"/p/one": "МОЙ проект"})
    out = CC["merge_project_hotkeys"](rows, [{"cwd": "/p/one", "name": "one",
                                              "hotkey": "Ctrl+F11"}])
    assert out[0]["name"] == "МОЙ проект", out



def test_project_age_comes_from_content_not_mtime():
    # Наверх всплывали проекты с открытыми окнами, где разговора не было
    # часами: mtime транскрипта двигают служебные записи — last-prompt,
    # custom-title, pr-link, — и Claude Code переписывает их спустя дни после
    # последней реплики. Про это в самом агрегаторе написано дважды, у
    # last_message_at и у fresh_ids; строка проекта была последним местом,
    # которое всё ещё верило mtime.
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/a.jsonl", 9000.0)]}]
    rows = CC["project_rows"](dirs, set(), {}, age_of=lambda p: 1000.0)
    assert rows[0]["mtime"] == 1000.0, rows


def test_project_age_stops_at_the_first_file_that_cannot_be_beaten():
    # Возраст содержимого не может быть позже записи в файл, а files уже
    # отсортирован по mtime убыванием: как только накопленный ответ достиг
    # mtime следующего файла, ни один из оставшихся его не обгонит. Без
    # остановки это чтение хвоста по 256 КБ у каждого транскрипта проекта — на
    # живой машине их под сотню в одном каталоге.
    seen = []

    def age_of(path):
        seen.append(path)
        return 8000.0

    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/new.jsonl", 9000.0),
                       ("/d/-p-one/old.jsonl", 5000.0),
                       ("/d/-p-one/older.jsonl", 4000.0)]}]
    rows = CC["project_rows"](dirs, set(), {}, age_of=age_of)
    assert rows[0]["mtime"] == 8000.0, rows
    assert seen == ["/d/-p-one/new.jsonl"], seen


def test_a_newer_conversation_in_an_older_file_still_wins():
    # Обратный случай: у новейшего по mtime файла хвост переписан служебной
    # записью, а разговор в нём давний — тогда свежайшим оказывается соседний
    # транскрипт, и остановка не должна срабатывать раньше него.
    ages = {"/d/-p-one/new.jsonl": 1000.0, "/d/-p-one/old.jsonl": 4500.0}
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/new.jsonl", 9000.0),
                       ("/d/-p-one/old.jsonl", 5000.0)]}]
    rows = CC["project_rows"](dirs, set(), {}, age_of=ages.get)
    assert rows[0]["mtime"] == 4500.0, rows


def test_unknown_content_age_falls_back_to_mtime():
    # Ноль у last_message_at значит «в хвосте нет ни одной записи со
    # временем», то есть возраст неизвестен, а не древний. Отдав его как есть,
    # строка проекта уехала бы в 1970 год — а формат `ago` по нулю именно его
    # и рисует.
    dirs = [{"dir": "/d/-p-one", "cwd": "/p/one",
             "files": [("/d/-p-one/a.jsonl", 9000.0)]}]
    rows = CC["project_rows"](dirs, set(), {}, age_of=lambda p: 0.0)
    assert rows[0]["mtime"] == 9000.0, rows


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
