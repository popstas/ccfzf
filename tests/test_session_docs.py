"""Спека и план сессии в ответе --state. Запуск: python3 tests/test_session_docs.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

# Шестое значение tail_facts — состояние агента из хвоста. Подставным хвостам
# этих тестов оно безразлично: своё правило у него своё, в test_agent_state.py.
NO_STATE = {"state": "", "question": ""}



def write(d, name, lines):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o) + "\n")
    return path


def msg(text):
    return {"type": "assistant", "timestamp": "2026-08-18T10:00:00Z",
            "message": {"content": [{"type": "text", "text": text}]}}


def test_spec_and_plan_are_found_in_the_tail():
    # Хука для этого нет: state.json пишет claude-wt, и поля про спеки там не
    # заводили — а завести нечем, репозиторий чужой. Зато путь называет сам
    # разговор, и хвост его транскрипта уже читается ради заголовка.
    with tempfile.TemporaryDirectory() as d:
        p = write(d, "a.jsonl", [
            msg("написал docs/superpowers/specs/2026-08-18-x-design.md"),
            msg("и план docs/superpowers/plans/2026-08-18-x.md"),
        ])
        assert CC["tail_facts"](p)[3] == {
            "spec": "docs/superpowers/specs/2026-08-18-x-design.md",
            "plan": "docs/superpowers/plans/2026-08-18-x.md",
        }


def test_the_last_mentioned_path_wins():
    # Сессия за день трогает и прошлый план, и новый. Спрошено «над чем она
    # сейчас», и последнее упоминание отвечает на это вернее первого.
    with tempfile.TemporaryDirectory() as d:
        p = write(d, "a.jsonl", [
            msg("docs/superpowers/plans/2026-08-01-old.md"),
            msg("docs/superpowers/plans/2026-08-18-new.md"),
        ])
        assert CC["tail_facts"](p)[3]["plan"] == "docs/superpowers/plans/2026-08-18-new.md"


def test_a_transcript_without_documents_says_so():
    with tempfile.TemporaryDirectory() as d:
        p = write(d, "a.jsonl", [msg("обычный разговор без бумаг")])
        assert CC["tail_facts"](p)[3] == {}


def test_a_spec_outside_superpowers_counts_too():
    # Каталог спек в проектах бывает и без `superpowers/`: у windows11-manager
    # рядом лежат оба, и новейшая спека — как раз в коротком. Поймано на живой
    # сессии 9974, у которой путь назван в хвосте двадцать семь раз, а колонка
    # бумаги была пуста.
    with tempfile.TemporaryDirectory() as d:
        p = write(d, "a.jsonl", [msg("см. docs/specs/2026-08-18-claude-place-layouts-design.md")])
        assert CC["tail_facts"](p)[3] == {
            "spec": "docs/specs/2026-08-18-claude-place-layouts-design.md",
        }


def test_only_superpowers_paths_count():
    # `docs/plans/` — это ralphex, и его планы живут по другому правилу и
    # открываются иначе. Ловить их этой же регуляркой значило бы обещать
    # человеку пункт меню, ведущий не туда, куда написано.
    with tempfile.TemporaryDirectory() as d:
        p = write(d, "a.jsonl", [msg("docs/plans/2026-08-18-x.md и docs/superpowers/notes/y.md")])
        assert CC["tail_facts"](p)[3] == {}


def test_a_named_but_missing_file_is_not_a_document():
    # Транскрипт называет пути, которых нет: предложенное имя, чужой репозиторий,
    # сокращённый в письме путь. Пункт меню по такому ведёт в никуда — а узнать
    # об этом человеку неоткуда, кроме как нажав. Живой пример 2026-08-18: у
    # сессии 9120 спекой числился `docs/specs/...md`, у 9974 планом —
    # `feature-plan.md` из чужого репозитория; ни того, ни другого на диске нет.
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "repo")
        os.makedirs(os.path.join(root, "docs", "specs"))
        real = os.path.join(root, "docs", "specs", "2026-08-18-real-design.md")
        open(real, "w").close()
        p = write(d, "a.jsonl", [
            msg("сперва docs/specs/2026-08-18-real-design.md"),
            msg("потом docs/specs/2026-08-18-nikogda-ne-pisali.md"),
        ])
        # Позже упомянутого файла нет, и побеждает последний **существующий**,
        # а не пустота: правило «свежее главнее» отбором не отменяется.
        assert CC["tail_facts"](p, root)[3] == {
            "spec": "docs/specs/2026-08-18-real-design.md",
        }


def test_without_a_directory_the_check_is_skipped():
    # Каталог знают не все зовущие: интерактивный список зовёт tail_facts ради
    # одного заголовка. Проверять там нечем, и требовать каталог значило бы
    # ронять тех, кому бумаги не нужны вовсе.
    with tempfile.TemporaryDirectory() as d:
        p = write(d, "a.jsonl", [msg("docs/specs/2026-08-18-x-design.md")])
        assert CC["tail_facts"](p)[3] == {"spec": "docs/specs/2026-08-18-x-design.md"}


def test_a_known_document_survives_a_tail_that_no_longer_mentions_it():
    # Путь, названный однажды и уехавший за TAIL, иначе пропал бы — а сессия
    # над тем же планом и работает. Приём тот же, что у `gist`: найденное
    # переносится через изменения файла.
    cache = {"/p/a.jsonl": {"mtime": 1.0, "title": "t", "doing": "d", "turnAt": 0,
                            "gist": "g", "gistDone": True, "size": 10,
                            "plan": "docs/superpowers/plans/2026-08-18-x.md"}}
    got = CC["facts_for"]("/p/a.jsonl", 2.0, cache,
                          tail=lambda p: ("t", "d", 0, {}, "cli", NO_STATE),
                          head=lambda p: "g", size_of=lambda p: 20)
    assert got["plan"] == "docs/superpowers/plans/2026-08-18-x.md", got


def test_a_freshly_named_document_replaces_the_remembered_one():
    cache = {"/p/a.jsonl": {"mtime": 1.0, "title": "t", "doing": "d", "turnAt": 0,
                            "gist": "g", "gistDone": True, "size": 10,
                            "plan": "docs/superpowers/plans/old.md"}}
    got = CC["facts_for"]("/p/a.jsonl", 2.0, cache,
                          tail=lambda p: ("t", "d", 0, {"plan": "docs/superpowers/plans/new.md"},
                                          "cli", NO_STATE),
                          head=lambda p: "g", size_of=lambda p: 20)
    assert got["plan"] == "docs/superpowers/plans/new.md", got


def test_a_truncated_file_forgets_its_documents():
    # Уменьшение размера — единственная наблюдаемая подпись подмены файла: id
    # отдали другой сессии, восстановили из бэкапа, сжали историю. Память о
    # чужом плане пережила бы подмену и врала бы про новую сессию. То же
    # правило и по той же причине действует у `gist`.
    cache = {"/p/a.jsonl": {"mtime": 1.0, "title": "t", "doing": "d", "turnAt": 0,
                            "gist": "g", "gistDone": True, "size": 100,
                            "plan": "docs/superpowers/plans/old.md"}}
    got = CC["facts_for"]("/p/a.jsonl", 2.0, cache,
                          tail=lambda p: ("t", "d", 0, {}, "cli", NO_STATE),
                          head=lambda p: "g", size_of=lambda p: 10)
    assert "plan" not in got, got


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
