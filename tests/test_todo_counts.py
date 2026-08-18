"""Счётчики docs/TODO.md у строки проекта. Запуск: python3 tests/test_todo_counts.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()


def sections(text):
    return CC["todo_sections"](text.splitlines())


def test_checkboxes_split_by_top_level_headers():
    # Разбор — порт statusline-block.sh из skill-do, и делит он по `# `, то
    # есть по заголовку первого уровня. Метка приводится к нижнему регистру и
    # теряет двоеточие: она встаёт в строку списка рядом с числом, а не
    # цитируется дословно.
    got = sections("# TODO\n\n# Next:\n\n- [x] a\n- [ ] b\n\n# Backlog\n\n- [ ] c\n")
    assert got == [{"label": "next", "done": 1, "todo": 1},
                   {"label": "backlog", "done": 0, "todo": 1}], got


def test_a_section_without_checkboxes_is_dropped():
    # Заголовок файла (`# TODO`) галочек не несёт почти никогда, и, оставшись,
    # он занял бы ведущее место — то самое, чей счёт человек и читает.
    got = sections("# TODO\n\n# next\n\n- [ ] a\n")
    assert got == [{"label": "next", "done": 0, "todo": 1}], got


def test_only_top_level_checkboxes_count():
    # Подпункты — это шаги одной задачи, а не задачи. Считая их, счёт скакал бы
    # от того, насколько подробно расписан пункт, а не от объёма работы.
    got = sections("# next\n\n- [ ] a\n  - [ ] a1\n  - [x] a2\n")
    assert got == [{"label": "next", "done": 0, "todo": 1}], got


def test_checkboxes_before_any_header_get_a_nameless_section():
    # Файл без заголовков — обычное дело у мелкого проекта, и счёт у него
    # обязан быть: пустая метка значит «называть нечем», а не «секции нет».
    got = sections("- [x] a\n- [ ] b\n")
    assert got == [{"label": "", "done": 1, "todo": 1}], got


def test_asterisk_bullets_count_too():
    got = sections("# next\n\n* [ ] a\n* [X] b\n")
    assert got == [{"label": "next", "done": 1, "todo": 1}], got


def test_a_file_without_checkboxes_has_no_sections():
    # Пустой список — это «счёта нет», и читатель обязан не рисовать колонку
    # вовсе, а не показывать 0/0.
    assert sections("# next\n\nпросто текст\n") == []


def test_project_todo_reads_docs_todo_md():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "docs"))
        with open(os.path.join(d, "docs", "TODO.md"), "w", encoding="utf-8") as fh:
            fh.write("# next\n\n- [ ] a\n- [x] b\n")
        assert CC["project_todo"](d) == [{"label": "next", "done": 1, "todo": 1}]


def test_project_without_a_todo_file_gets_nothing():
    # Файла нет у двадцати проектов из сорока пяти на живой машине. Ни ошибки,
    # ни пустой секции: поля в ответе просто не будет.
    with tempfile.TemporaryDirectory() as d:
        assert CC["project_todo"](d) == []


def test_unreadable_todo_is_not_an_error():
    # Каталог вместо файла, битая кодировка, отобранные права — всё это
    # обязано стоить пустого счёта, а не падения всего ответа --state.
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "docs", "TODO.md"))
        assert CC["project_todo"](d) == []


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
