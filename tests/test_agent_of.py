"""Тесты записи агента. Запуск: python3 tests/test_agent_of.py"""
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
NOW, TURN, START = 1785958293, 1785958000, 1785950000


def _write(d, sid, suffix, obj):
    with open(os.path.join(d, sid + suffix), "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def _transcript(d, at):
    """Транскрипт, чья последняя запись со временем — `at`.

    Хвост дописан служебными записями без `timestamp`: Claude Code кладёт их
    спустя дни после разговора, и именно из-за них mtime тут не годится.
    """
    path = os.path.join(d, UUID_A + ".jsonl")
    stamp = datetime.datetime.fromtimestamp(
        at, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "timestamp": stamp}) + "\n")
        fh.write(json.dumps({"type": "last-prompt", "lastPrompt": "/do"}) + "\n")
    return path


def _agent_of(d, sid, transcript=""):
    """agent_of читает каталог из глобального STATUS_DIR, его и подменяем.

    Память meta_all ключуется каталогом, поэтому временный каталог каждого
    теста свой и в чужой ответ не попадает.
    """
    CC["STATUS_DIR"] = d
    return CC["agent_of"](sid, transcript)


def test_agent_of_passes_the_four_fields_from_their_own_files():
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".state.json", {
            "state": "question", "updated": NOW, "turnAt": TURN,
            "question": "Какой вариант?",
            "message": "Claude needs your permission to use Bash",
        })
        _write(d, UUID_A, ".meta.json", {"started": START})
        got = _agent_of(d, UUID_A)
        assert got["turnAt"] == TURN, got["turnAt"]
        assert got["started"] == START, got["started"]
        assert got["question"] == "Какой вариант?", got["question"]
        assert got["message"] == "Claude needs your permission to use Bash", got["message"]


def test_agent_of_defaults_the_four_fields_when_the_hook_is_older():
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".state.json", {"state": "idle", "updated": NOW})
        got = _agent_of(d, UUID_A)
        assert got["turnAt"] == 0, got["turnAt"]
        assert got["started"] == 0, got["started"]
        assert got["question"] == "", got["question"]
        assert got["message"] == "", got["message"]


def test_agent_of_zeroes_a_spoiled_turn_stamp():
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".state.json",
               {"state": "active", "updated": NOW, "turnAt": "90"})
        assert _agent_of(d, UUID_A)["turnAt"] == 0
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".state.json",
               {"state": "active", "updated": NOW, "turnAt": -1})
        assert _agent_of(d, UUID_A)["turnAt"] == 0


def test_agent_of_does_not_let_meta_alone_create_a_record():
    # «Запись агента есть» значит «хук хоть раз сработал». Одна отметка старта
    # — это не она: читатель по наличию записи решает, есть ли что сказать.
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".meta.json", {"started": START})
        assert _agent_of(d, UUID_A) is None


def test_meta_all_reads_a_directory_once_and_skips_junk():
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".meta.json", {"started": START})
        with open(os.path.join(d, "not-a-uuid.meta.json"), "w") as fh:
            fh.write('{"started": 1}')
        with open(os.path.join(d, UUID_A + ".state.json"), "w") as fh:
            fh.write("{}")
        # Не-словарь и битый JSON — тоже junk, и оба под настоящими id: имя тут
        # не при чём, дело в содержимом. isinstance(meta, dict) в meta_all —
        # единственная строка, которая держит краш всего ответа --state: до неё
        # pid_owners звала meta.get("pid") над чем угодно, и список вместо
        # словаря в одном файле ронял бы ответ целиком.
        _write(d, "cccccccc-1111-2222-3333-444444444444", ".meta.json", [1, 2])
        with open(os.path.join(d, "dddddddd-1111-2222-3333-444444444444.meta.json"), "w") as fh:
            fh.write("{not json")
        got = CC["meta_all"](d)
        assert list(got) == [UUID_A], list(got)
        assert got[UUID_A]["started"] == START
        # Второй вызов отдаёт то же, не перечитывая: дописанный файл не виден.
        _write(d, "bbbbbbbb-1111-2222-3333-444444444444", ".meta.json", {"started": 2})
        assert list(CC["meta_all"](d)) == [UUID_A]
    assert CC["meta_all"]("/nonexistent-dir-for-tests") == {}


def test_meta_all_keeps_directories_apart():
    # Память общая на процесс, ключ — каталог. Без ключа ответ первого теста
    # достался бы второму, и все проверки выше стали бы проверять кэш.
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        _write(a, UUID_A, ".meta.json", {"started": 111})
        assert CC["meta_all"](a)[UUID_A]["started"] == 111
        assert CC["meta_all"](b) == {}


def test_agent_of_does_not_let_the_statusline_move_last_activity():
    # Сессия спит шесть часов, но её терминал открыт, и статуслайн по таймеру
    # переписывает status.json каждые несколько секунд. `updated` обязан
    # остаться тем, что в state.json: через max() у любой живой сессии
    # «последняя активность» вечно оказывалась секундной давности.
    idle = NOW - 6 * 3600
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".state.json", {"state": "idle", "updated": idle})
        _write(d, UUID_A, ".status.json",
               {"costUsd": 3, "contextPct": 40, "updated": NOW})
        got = _agent_of(d, UUID_A)
        assert got["updated"] == idle, got["updated"]
        # Деньги и проценты, наоборот, у статуслайна: он пишется чаще.
        assert got["costUsd"] == 3, got["costUsd"]
        assert got["contextPct"] == 40, got["contextPct"]


def test_agent_of_dates_a_stateless_session_by_its_last_message():
    # Сессия открыта двенадцатый день и всё это время молчит. state.json у неё
    # съела чистка (prune_state роняет файл, которого неделю не касались), а
    # status.json жив: статуслайн переписывает его по таймеру, пока открыт
    # терминал. Отката на этот пульс быть не должно — сессия всплывала бы
    # наверх сортировки `recent` вечно, отвечая «активность секунду назад» про
    # разговор двенадцатидневной давности.
    quiet = NOW - 12 * 24 * 3600
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".status.json", {"costUsd": 1, "updated": NOW})
        got = _agent_of(d, UUID_A, _transcript(d, quiet))
        assert got["updated"] == quiet, got["updated"]
        # Деньги статуслайн по-прежнему знает лучше всех: обнулять их незачем.
        assert got["costUsd"] == 1, got["costUsd"]


def test_agent_of_leaves_last_activity_unknown_without_a_transcript():
    # Транскрипта нет (сессию стёрли, а файлы состояния остались) — честный
    # ответ «не знаем», ноль. Читатель топит такие строки вниз сам.
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".status.json", {"costUsd": 1, "updated": NOW})
        assert _agent_of(d, UUID_A)["updated"] == 0


def test_agent_of_dates_a_spoiled_stamp_by_the_transcript_too():
    quiet = NOW - 3 * 24 * 3600
    with tempfile.TemporaryDirectory() as d:
        _write(d, UUID_A, ".state.json", {"state": "idle", "updated": "nope"})
        _write(d, UUID_A, ".status.json", {"updated": NOW})
        assert _agent_of(d, UUID_A, _transcript(d, quiet))["updated"] == quiet


def test_agent_of_returns_nothing_when_the_hook_never_ran():
    with tempfile.TemporaryDirectory() as d:
        assert _agent_of(d, UUID_A) is None


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
