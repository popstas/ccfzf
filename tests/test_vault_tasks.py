"""Задача вольта у строки сессии: разбор vaults-config.md и tasks.md, поле `task`.

Связь пишет скилл sess2task: подпункт `- Сессия <имя>` в блок задачи. Имена
сессий и задачи здесь выдуманные — репозиторий публичный.

Запуск: python3 tests/test_vault_tasks.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def config_text(*vaults):
    """Конфиг в том виде, в каком его держит человек: секция на скилл."""
    out = ["Конфиг вольтов.\n"]
    for name, vault in vaults:
        out.append("## %s\n\n- `vault`: `%s`\n- `title`: что-то\n- `tasks`: `tasks.md`\n"
                   % (name, vault))
    return "\n".join(out)


def parse(text, label="demo"):
    return CC["parse_vault_tasks"](text, label)


# --- Task 1: разбор ---------------------------------------------------------

def test_sections_without_tasks_are_skipped():
    # `sync-conflicts` — секция без `tasks`: вольт там есть, задач нет.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vaults-config.md")
        write(p, config_text(("one-connect", "/v/one"), ("two-connect", "/v/two"))
              + "\n## sync-conflicts\n\nПапки.\n\n- `vault`: `/v/shared`\n")
        got = CC["read_vaults_config"](p)
        assert got == [{"vault": "/v/one", "tasks": "tasks.md"},
                       {"vault": "/v/two", "tasks": "tasks.md"}], got


def test_a_missing_config_reads_empty():
    with tempfile.TemporaryDirectory() as d:
        assert CC["read_vaults_config"](os.path.join(d, "нет.md")) == []
        assert CC["read_vaults_config"]("") == []
        assert CC["vault_task_index"](os.path.join(d, "нет.md")) == {}
        assert CC["vault_task_index"]("") == {}


def test_the_name_is_the_first_word_after_the_label():
    # После имени sess2task пишет что угодно: проект в скобках, номера PR.
    got = parse("- [ ] Покрасить забор ➕ 2026-01-02\n"
                "\t- Сессия alpha-head (demo-repo); #12 #13\n")
    assert list(got) == ["alpha-head"], got
    assert got["alpha-head"][0]["text"] == "Покрасить забор", got


def test_leading_junk_before_the_name_is_dropped():
    # Мусорный префикс бывает: копия из дерева сессий несёт `└`.
    got = parse("- [ ] Задача\n\t- Сессия └beta-prepare\n")
    assert list(got) == ["beta-prepare"], got


def test_a_closed_task_is_done():
    got = parse("- [x] Сделано ✅ 2026-01-03\n\t- Сессия gamma\n")
    assert got["gamma"][0]["done"] is True, got
    got = parse("- [ ] Не сделано\n\t- Сессия gamma\n")
    assert got["gamma"][0]["done"] is False, got


def test_two_sessions_under_one_task():
    got = parse("- [ ] Общая задача\n\t- Сессия one-a\n\t- Сессия one-b\n")
    assert set(got) == {"one-a", "one-b"}, got
    assert got["one-a"][0]["text"] == got["one-b"][0]["text"] == "Общая задача"


def test_a_session_under_a_nested_task_belongs_to_it():
    got = parse("- [ ] Родитель\n"
                "\t- [ ] Вложенная\n"
                "\t\t- Сессия nested-s\n"
                "\t- Сессия parent-s\n")
    assert got["nested-s"][0]["text"] == "Вложенная", got
    # Подпункт на уровне вложенной задачи — её сосед, а не ребёнок: он
    # относится к родителю.
    assert got["parent-s"][0]["text"] == "Родитель", got


def test_the_session_line_need_not_be_first_in_the_block():
    # Старый формат: подпункт ниже заметок.
    got = parse("- [ ] Задача\n\t- заметка\n\t- [[Ссылка]]\n\t- Сессия late-s\n")
    assert got["late-s"][0]["text"] == "Задача", got


def test_a_session_line_outside_any_task_is_ignored():
    got = parse("## Раздел\n\n- Сессия orphan\n- [ ] Задача\n\n## Другой\n\t- Сессия lost\n")
    assert got == {}, got


def test_the_text_is_cleaned_of_tasks_markers_and_links():
    got = parse("- [ ] Сделать [[Note|ящик]] для [[Почта]] и [сайта](https://example.org) "
                "⚡ ➕ 2026-11-21 📅 2026-11-25\n\t- Сессия clean-s\n")
    e = got["clean-s"][0]
    assert e["text"] == "Сделать ящик для Почта и сайта", e
    assert e["added"] == "2026-11-21", e
    got = parse("- [x] Готово ⏳ 2026-01-01 🛫 2026-01-01 ✅ 2026-01-02\n\t- Сессия d\n")
    assert got["d"][0]["text"] == "Готово", got
    assert got["d"][0]["added"] == "", got


def test_a_long_task_is_cut_to_120():
    got = parse("- [ ] " + "я" * 200 + "\n\t- Сессия long-s\n")
    text = got["long-s"][0]["text"]
    assert len(text) == 120 and text.endswith("…"), (len(text), text[-3:])


def test_the_vault_label_is_carried():
    got = parse("- [ ] Задача\n\t- Сессия s\n", "work")
    assert got["s"][0]["vault"] == "work", got


def test_the_index_joins_vaults_by_name():
    # Одно и то же имя бывает в двух вольтах — задачи складываются.
    with tempfile.TemporaryDirectory() as d:
        one, two = os.path.join(d, "one"), os.path.join(d, "two")
        write(os.path.join(one, "tasks.md"), "- [ ] Первая\n\t- Сессия same\n")
        write(os.path.join(two, "tasks.md"), "- [ ] Вторая\n\t- Сессия same\n")
        p = os.path.join(d, "vaults-config.md")
        write(p, config_text(("a", one), ("b", two), ("c", os.path.join(d, "нет"))))
        got = CC["vault_task_index"](p)
        assert [(e["vault"], e["text"]) for e in got["same"]] == [
            ("one", "Первая"), ("two", "Вторая")], got


if __name__ == "__main__":
    fails = 0
    names = [n for n in globals() if n.startswith("test_")]
    for name in sorted(names):
        try:
            globals()[name]()
            print("ok   " + name)
        except Exception as e:  # noqa: BLE001 — падение любого рода и есть провал
            fails += 1
            print("FAIL " + name + ": " + repr(e))
    print("%d/%d passed" % (len(names) - fails, len(names)))
    sys.exit(1 if fails else 0)
