"""Тесты разбора zellij. Запуск: python3 tests/test_zellij.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

SERVER = ["/snap/zellij/65/bin/zellij", "--server",
          "/run/user/1000/zellij/contract_version_1/obsidian-agent-base"]


def test_server_argv_gives_the_session_name():
    assert CC["zellij_server_name"](SERVER) == "obsidian-agent-base"


def test_a_client_is_not_a_server():
    # `zellij attach foo` — тот же бинарь, сессии не держит.
    assert CC["zellij_server_name"](["zellij", "attach", "foo"]) == ""
    assert CC["zellij_server_name"](["zellij"]) == ""


def test_someone_elses_server_flag_is_not_zellij():
    # `--server` встречается у кого угодно; решает имя бинаря.
    assert CC["zellij_server_name"](["node", "--server", "/tmp/sock"]) == ""


def test_a_server_without_a_socket_path_gives_nothing():
    assert CC["zellij_server_name"](["zellij", "--server"]) == ""


def test_trailing_slash_does_not_eat_the_name():
    assert CC["zellij_server_name"](
        ["zellij", "--server", "/run/user/1000/zellij/v1/home/"]) == "home"


def test_env_gives_the_session_name():
    env = ["ZELLIJ=0", "ZELLIJ_PANE_ID=0", "ZELLIJ_SESSION_NAME=cup-dashboard", ""]
    assert CC["zellij_env_name"](env) == "cup-dashboard"


def test_env_without_zellij_gives_nothing():
    assert CC["zellij_env_name"](["PATH=/usr/bin", "TMUX_PANE=%3"]) == ""


def test_a_similar_variable_is_not_the_name():
    # Префиксное сравнение без `=` поймало бы ZELLIJ_SESSION_NAME_EXTRA.
    assert CC["zellij_env_name"](["ZELLIJ_SESSION_NAMES=a,b"]) == ""


def test_proc_zellij_answers_none_for_a_pid_that_is_gone():
    assert CC["proc_zellij"]("999999999") is None


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
