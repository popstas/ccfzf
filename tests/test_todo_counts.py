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


def test_the_same_directory_is_read_once_per_answer():
    """Счёт нужен и строкам сессий, а их сто на четыре десятка каталогов.

    Читать файл на каждую строку значило бы сто чтений вместо сорока пяти — и
    это на горячем пути, который зовут раз в секунду по ssh.
    """
    seen = []

    def counted(cwd):
        seen.append(cwd)
        return [{"label": "next", "done": 0, "todo": 1}]

    memo = CC["todo_memo"](counted)
    assert memo("/p/one") == [{"label": "next", "done": 0, "todo": 1}]
    assert memo("/p/one") == [{"label": "next", "done": 0, "todo": 1}]
    assert memo("/p/two") is not None
    assert seen == ["/p/one", "/p/two"], seen


def test_a_directory_without_a_todo_is_remembered_too():
    # Иначе пустой ответ переспрашивался бы у каждой строки: каталогов без
    # docs/TODO.md почти половина, и именно они дали бы больше всего лишних
    # чтений.
    seen = []

    def counted(cwd):
        seen.append(cwd)
        return []

    memo = CC["todo_memo"](counted)
    assert memo("/p/none") == []
    assert memo("/p/none") == []
    assert seen == ["/p/none"], seen


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def settings(d, todo, local=False):
    name = "settings.local.json" if local else "settings.json"
    write(os.path.join(d, ".claude", name),
          '{"env": {"STATUSLINE_TODO": "%s"}}' % todo)


def test_settings_name_the_todo_file():
    """Файл задач называет `env.STATUSLINE_TODO`, а `docs/TODO.md` — умолчание.

    По этому ключу живёт статус-строка Claude Code, то есть названный там файл
    и есть тот, который человек видит перед собой. У вольта Obsidian это
    `tasks.md` в корне, и счёт по `docs/TODO.md` был бы счётом файла, который
    в этом каталоге никто не открывает.
    """
    with tempfile.TemporaryDirectory() as d:
        settings(d, "tasks.md")
        write(os.path.join(d, "tasks.md"), "# week\n\n- [x] a\n- [ ] b\n")
        write(os.path.join(d, "docs", "TODO.md"), "# next\n\n- [ ] c\n")
        assert CC["project_todo"](d) == [{"label": "week", "done": 1, "todo": 1}]


def test_the_named_file_may_lie_outside_the_project():
    # Относительный путь считается от каталога проекта, абсолютный берётся как
    # есть — те же два правила, что у statusline-block.sh. Абсолютный тут не
    # редкость: у соседних рабочих каталогов список задач лежит в чужом вольте.
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as far:
        outside = os.path.join(far, "tasks.md")
        write(outside, "# week\n\n- [ ] a\n")
        settings(d, outside)
        assert CC["project_todo"](d) == [{"label": "week", "done": 0, "todo": 1}]


def test_local_settings_win_over_the_shared_ones():
    # Тот же порядок, каким слои настроек кладёт друг на друга сам Claude Code.
    with tempfile.TemporaryDirectory() as d:
        settings(d, "shared.md")
        settings(d, "mine.md", local=True)
        write(os.path.join(d, "shared.md"), "# shared\n\n- [ ] a\n")
        write(os.path.join(d, "mine.md"), "# mine\n\n- [ ] b\n")
        assert CC["project_todo"](d) == [{"label": "mine", "done": 0, "todo": 1}]


def test_settings_without_the_key_leave_the_default_alone():
    # Ключа нет у большинства проектов, и это обычный случай, а не поломка:
    # у самого ccfzf-picker задачи и лежат в docs/TODO.md.
    with tempfile.TemporaryDirectory() as d:
        write(os.path.join(d, ".claude", "settings.json"), '{"env": {}}')
        write(os.path.join(d, "docs", "TODO.md"), "# next\n\n- [ ] a\n")
        assert CC["project_todo"](d) == [{"label": "next", "done": 0, "todo": 1}]


def test_broken_settings_cost_the_default_and_not_the_answer():
    # Счёт задач украшает строку. Уронив на нём разбор, мы потеряли бы весь
    # ответ --state — то есть список целиком из-за запятой в чужом файле.
    with tempfile.TemporaryDirectory() as d:
        write(os.path.join(d, ".claude", "settings.json"), "{не json")
        write(os.path.join(d, "docs", "TODO.md"), "# next\n\n- [ ] a\n")
        assert CC["project_todo"](d) == [{"label": "next", "done": 0, "todo": 1}]


def test_a_named_file_that_is_missing_is_not_the_default_either():
    # Ключ назвали — значит `docs/TODO.md` в этом каталоге не список задач, а
    # посторонний файл. Молча подставив его, счёт врал бы ровно там, где
    # человек и просил считать другое.
    with tempfile.TemporaryDirectory() as d:
        settings(d, "tasks.md")
        write(os.path.join(d, "docs", "TODO.md"), "# next\n\n- [ ] a\n")
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
