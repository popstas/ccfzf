"""Ключ --limit. Запуск: python3 tests/test_limit.py"""
import os
import subprocess
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccfzf")


def run(*args):
    return subprocess.run(["bash", SRC, *args], capture_output=True, text=True)


def test_limit_rejects_a_non_number():
    # Проверка стоит до всякой работы: разбор аргументов идёт раньше поиска
    # python3 и fzf, поэтому тест ничего не сканирует и ничего не пишет.
    r = run("--limit", "abc", "--state")
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "--limit" in r.stderr, r.stderr


def test_limit_rejects_zero_and_negative():
    for bad in ("0", "-5"):
        r = run("--limit", bad, "--state")
        assert r.returncode == 2, (bad, r.returncode, r.stderr)


def test_limit_requires_a_value():
    r = run("--state", "--limit")
    assert r.returncode == 2, (r.returncode, r.stderr)


def test_both_spellings_are_accepted():
    # Значение верное — значит разбор до конца дошёл и код 2 не возвращён.
    # Дальше режим отработает по-настоящему, поэтому сравниваем именно с 2.
    for args in (("--limit", "7", "--state"), ("--limit=7", "--state")):
        r = run(*args)
        assert r.returncode != 2, (args, r.returncode, r.stderr)


def test_help_documents_the_key():
    r = run("--help")
    assert "--limit" in r.stdout, r.stdout


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
