"""Тесты записи агента. Запуск: python3 tests/test_agent_of.py"""
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


def _agent_of(d, sid):
    """agent_of читает каталог из глобального STATUS_DIR, его и подменяем.

    Память meta_all ключуется каталогом, поэтому временный каталог каждого
    теста свой и в чужой ответ не попадает.
    """
    CC["STATUS_DIR"] = d
    return CC["agent_of"](sid)


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
