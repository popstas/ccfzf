"""Процессный слой на маке: разбор `ps` и ветки функций /proc.

На macOS нет /proc, и весь разбор процессов идёт через один вызов `ps`.
Проверить это на Linux можно только так: настоящего маковского `ps` здесь не
завести, поэтому разбор отделён от вызова, а ветки проверяются с подставной
таблицей.

Запуск: python3 tests/test_darwin_procs.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

# Снято с живого мака: `ps -axwwo pid=,ppid=,tty=,lstart=,command=`.
# Здесь четыре строки нарочно разные: сессия без аргументов и с терминалом,
# запуск через версионный лаунчер, процесс без управляющего терминала (`??`)
# и день месяца, выровненный пробелом (`Aug  1`).
PS = """\
99228     1 ttys007 Tue Aug 18 16:18:25 2026 claude
71308 71300 ttys003 Sat Aug  1 04:30:17 2026 /Users/u/.local/share/claude/versions/2.1.233/claude --resume 2f03f490-c090-4c97-99e2-eecedbf009fa
84235     1 ??      Mon Aug 17 00:29:35 2026 /Applications/Claude.app/Contents/MacOS/Claude
"""


class table:
    """Подставная таблица процессов на время одного теста."""

    def __init__(self, rows, darwin=True):
        self.rows, self.darwin = rows, darwin

    def __enter__(self):
        self.saved = (CC["DARWIN"], CC["_PS_TABLE"])
        CC["DARWIN"], CC["_PS_TABLE"] = self.darwin, self.rows
        return self

    def __exit__(self, *a):
        CC["DARWIN"], CC["_PS_TABLE"] = self.saved


def test_ps_rows_reads_pid_ppid_and_tty():
    rows = CC["ps_rows"](PS)
    assert sorted(rows) == ["71308", "84235", "99228"], sorted(rows)
    assert rows["71308"]["ppid"] == "71300", rows["71308"]
    assert rows["99228"]["tty"] == "ttys007", rows["99228"]
    assert rows["84235"]["tty"] == "??", rows["84235"]


def test_ps_rows_splits_the_command_back_into_argv():
    # Ради этого разбор и нужен: argv кормит is_claude и arg_value, а `ps`
    # отдаёт его одной строкой.
    rows = CC["ps_rows"](PS)
    assert rows["99228"]["args"] == ["claude"], rows["99228"]
    assert CC["is_claude"](rows["99228"]["args"])
    args = rows["71308"]["args"]
    assert CC["is_claude"](args), args
    assert CC["arg_value"](args, "--resume") == "2f03f490-c090-4c97-99e2-eecedbf009fa", args


def test_ps_rows_reads_lstart_whatever_the_timezone():
    # Сверка обратным преобразованием, а не числом: `mktime` считает в местном
    # поясе, и число зависело бы от машины, на которой гоняют тесты.
    rows = CC["ps_rows"](PS)
    for pid, want in (("99228", "Tue Aug 18 16:18:25 2026"),
                      ("71308", "Sat Aug  1 04:30:17 2026")):
        got = time.strftime(CC["LSTART_FMT"], time.localtime(rows[pid]["started"]))

        # `%d` печатает день с ведущим нулём, а `ps` выравнивает пробелом:
        # сравниваются значения, а не то, как их записали.
        def fields(s):
            f = s.split()
            f[2] = str(int(f[2]))
            return f

        assert fields(got) == fields(want), (pid, got, want)


def test_ps_rows_skips_what_is_not_a_process_line():
    assert CC["ps_rows"]("") == {}
    assert CC["ps_rows"]("PID PPID TTY STARTED COMMAND\n") == {}
    # Строка без команды — не процесс, а обрезок.
    assert CC["ps_rows"]("99228 1 ttys007 Tue Aug 18 16:18:25 2026\n") == {}


def test_a_bad_date_costs_the_date_and_nothing_else():
    rows = CC["ps_rows"]("99228 1 ttys007 no such date at all claude\n")
    assert rows["99228"]["started"] == 0.0, rows
    assert rows["99228"]["args"] == ["claude"], rows


def test_the_tty_gets_its_directory_back():
    # `ps` печатает `ttys007`, а читателю нужен путь: по нему открывают
    # терминал сессии, и `/dev/` там обязателен.
    with table(CC["ps_rows"](PS)):
        assert CC["proc_tty"]("99228") == "/dev/ttys007"
        # `??` — это «управляющего терминала нет», а не имя устройства.
        assert CC["proc_tty"]("84235") == ""
        assert CC["proc_tty"]("404") == ""


def test_process_fields_come_from_the_table():
    with table(CC["ps_rows"](PS)):
        assert CC["proc_args"]("99228") == ["claude"]
        assert CC["parent_pid"]("71308") == "71300"
        assert CC["proc_args"]("404") == []
        assert CC["parent_pid"]("404") == ""
        assert CC["proc_started"]("99228") == int(CC["ps_table"]()["99228"]["started"])
        assert CC["proc_created"]("99228") == CC["proc_started"]("99228")
        assert sorted(CC["all_pids"]()) == ["71308", "84235", "99228"]


def test_the_linux_road_is_untouched():
    # Ветка добавлена, а не подменена: на Linux всё по-прежнему читается из
    # /proc, и подставная таблица на это не влияет.
    with table({"99228": {"args": ["claude"], "ppid": "1", "tty": "ttys007",
                          "started": 1.0}}, darwin=False):
        mine = CC["proc_args"](os.getpid())
        assert os.path.basename(mine[0]).startswith("python"), mine
        assert CC["proc_tty"]("99228") == "", "с Linux-ветки таблица не читается"
        assert CC["proc_cwd"](os.getpid()) == os.getcwd()


def test_lsof_answers_with_its_last_path_field():
    out = "p99228\nfcwd\nn/private/tmp\n"
    assert CC["lsof_cwd"](out) == "/private/tmp"
    # Заголовок процесса тоже строка-поле, и путь в ней не лежит.
    assert CC["lsof_cwd"]("p99228\n") == ""
    assert CC["lsof_cwd"]("") == ""


def test_boot_id_on_the_mac_is_the_boot_second():
    saved = CC["darwin_sysctl"]
    CC["DARWIN"], CC["darwin_sysctl"] = True, lambda name: (
        "{ sec = 1786113356, usec = 421885 } Sun Aug 10 03:15:56 2026\n")
    try:
        assert CC["boot_id"]() == "1786113356"
        CC["darwin_sysctl"] = lambda name: ""
        assert CC["boot_id"]() == "", "не прочиталось — пустая строка, а не падение"
    finally:
        CC["DARWIN"], CC["darwin_sysctl"] = False, saved


def test_the_environment_is_scanned_by_prefix():
    # На маке окружение приезжает хвостом к команде и от argv не отделено —
    # поэтому читатели ищут переменную по префиксу, а не по месту.
    tail = ["claude", "PATH=/usr/bin", "ZELLIJ_SESSION_NAME=work", "TMUX_PANE=%3"]
    assert CC["zellij_env_name"](tail) == "work"
    assert CC["zellij_env_name"](["claude", "ZELLIJ_SESSION_NAME_X=no"]) == ""


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
