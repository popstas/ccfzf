"""Переменная CCFZF_STATE_DUMP_MAX_AGE. Запуск: python3 tests/test_state_dump_age.py"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccfzf")


def test_zero_means_rewrite_always():
    """Ноль значит «переписывать всегда»."""
    with tempfile.NamedTemporaryFile(suffix=".json") as f:
        now = time.time()
        assert not CC["stale_dump"](f.name, now, 30), "по обычному сроку файл свеж"
        assert CC["stale_dump"](f.name, now, 0), "ноль значит переписывать всегда"


def test_negative_is_the_same_as_zero():
    """Отрицательный срок — тот же ноль."""
    with tempfile.NamedTemporaryFile(suffix=".json") as f:
        assert CC["stale_dump"](f.name, time.time(), -1)


def test_empty_path_never_goes_stale():
    """Дамп выключен — писать нечего, и ноль этого не меняет."""
    assert not CC["stale_dump"]("", time.time(), 0)


def test_env_overrides_the_default():
    """Переменная перебивает умолчание."""
    os.environ["CCFZF_STATE_DUMP_MAX_AGE"] = "0"
    try:
        assert CC["env_int"]("CCFZF_STATE_DUMP_MAX_AGE", 30) == 0
    finally:
        del os.environ["CCFZF_STATE_DUMP_MAX_AGE"]


def test_garbage_env_falls_back_to_the_default():
    """Опечатка в переменной не должна ронять ответ, ради которого запуск."""
    os.environ["CCFZF_STATE_DUMP_MAX_AGE"] = "быстро"
    try:
        assert CC["env_int"]("CCFZF_STATE_DUMP_MAX_AGE", 30) == 30
    finally:
        del os.environ["CCFZF_STATE_DUMP_MAX_AGE"]


def test_missing_env_gives_the_default():
    """Нет переменной — прежние тридцать секунд."""
    os.environ.pop("CCFZF_STATE_DUMP_MAX_AGE", None)
    assert CC["env_int"]("CCFZF_STATE_DUMP_MAX_AGE", 30) == 30


def test_state_mode_reads_the_variable():
    """Вызов stale_dump обязан спрашивать переменную, иначе всплеск пикера уйдёт впустую."""
    src = open(SRC, encoding="utf-8").read()
    assert 'env_int("CCFZF_STATE_DUMP_MAX_AGE", STATE_DUMP_MAX_AGE)' in src


def test_the_header_documents_the_variable():
    """Переменная описана в шапке рядом с остальными."""
    src = open(SRC, encoding="utf-8").read()
    assert "CCFZF_STATE_DUMP_MAX_AGE" in src.split("PYEOF")[0]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
