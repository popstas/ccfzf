"""Признак разорванной сессии: застрявшая очередь отправки ssh-сокета.

Строки /proc/net/tcp{,6} — по форме настоящих (сверено с живой машиной),
адреса и очереди подставлены: документационные 192.0.2.0/24 (RFC 5737), —
репозиторий публичный. Настоящая строка застрявшего сокета ещё не снята.

Запуск: python3 tests/test_sendq.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

HEADER = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when "
          "retrnsmt   uid  timeout inode")
# 192.0.2.14:22 ← 192.0.2.15:63374, очередь 948 (0x3B4) — разорванная.
TCP_STUCK = ("   3: 0E0200C0:0016 0F0200C0:F78E 01 000003B4:00000000 01:00000020 "
             "00000005  1000        0 23697 4 0000000000000000 27 4 30 10 48")
# Тот же сервер, другой клиент, очередь пуста.
TCP_IDLE = ("   4: 0E0200C0:0016 0F0200C0:EBD4 01 00000000:00000000 02:000008A3 "
            "00000000  1000        0 23698 2 0000000000000000 27 4 30 10 48")
# Слушающий сокет: в ответ не попадает.
TCP_LISTEN = ("   0: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 "
              "00000000     0        0 1234 1 0000000000000000 100 0 0 10 0")
# IPv4-mapped в tcp6: ::ffff:192.0.2.14:22 ← ::ffff:192.0.2.15:63374.
TCP6_MAPPED = ("  22: 0000000000000000FFFF00000E0200C0:0016 "
               "0000000000000000FFFF00000F0200C0:F78E 01 00000064:00000000 "
               "02:000008A3 00000000  1000        0 23699 2 0000000000000000 27 4 30 10 48")


def env(*pairs):
    return "\0".join(pairs).encode() + b"\0"


def test_ssh_peer_reads_four_fields():
    got = CC["ssh_peer"](env("HOME=/h", "SSH_CONNECTION=192.0.2.15 63374 192.0.2.14 22"))
    assert got == ("192.0.2.15", 63374, "192.0.2.14", 22), got


def test_ssh_peer_absent():
    assert CC["ssh_peer"](env("HOME=/h", "TERM=xterm")) is None
    assert CC["ssh_peer"](b"") is None


def test_ssh_peer_garbage():
    # Не четыре поля, нечисловой порт — не догадка, а отказ.
    assert CC["ssh_peer"](env("SSH_CONNECTION=192.0.2.15 63374")) is None
    assert CC["ssh_peer"](env("SSH_CONNECTION=192.0.2.15 x 192.0.2.14 22")) is None


def test_ssh_peer_normalizes_mapped():
    got = CC["ssh_peer"](env("SSH_CONNECTION=::ffff:192.0.2.15 1 ::ffff:192.0.2.14 22"))
    assert got == ("192.0.2.15", 1, "192.0.2.14", 22), got


def test_tcp_queues_ipv4():
    got = CC["tcp_queues"]("\n".join([HEADER, TCP_STUCK, TCP_IDLE]))
    assert got[("192.0.2.14", 22, "192.0.2.15", 63374)] == 948, got
    assert got[("192.0.2.14", 22, "192.0.2.15", 60372)] == 0, got


def test_tcp_queues_ipv6_mapped():
    got = CC["tcp_queues"]("\n".join([HEADER, TCP6_MAPPED]))
    assert got == {("192.0.2.14", 22, "192.0.2.15", 63374): 100}, got


def test_tcp_queues_ipv6_native():
    # 2001:db8::1 — четыре 32-битных слова, каждое байтами задом наперёд.
    line = ("   1: B80D0120000000000000000001000000:0016 "
            "B80D0120000000000000000002000000:1F90 01 00000010:00000000 "
            "00:00000000 00000000  1000        0 1 1 0 27 4 30 10 48")
    got = CC["tcp_queues"](line)
    assert got == {("2001:db8::1", 22, "2001:db8::2", 8080): 16}, got


def test_tcp_queues_skips_listen_and_garbage():
    got = CC["tcp_queues"]("\n".join([HEADER, TCP_LISTEN, "мусор", ""]))
    assert got == {}, got


# ---- вердикт по двум опросам ----------------------------------------------

K = "100:1700000000:192.0.2.15:63374:192.0.2.14:22"


def poll(seq):
    """Прогнать опросы [(now, q)] и вернуть [(вердикт, состояние)] по каждому."""
    prev, out = {}, []
    for now, q in seq:
        disc, prev = CC["sendq_verdicts"]({K: q}, prev, now)
        out.append((K in disc, prev))
    return out


def test_constants():
    assert CC["SENDQ_STUCK_SECS"] == 8
    assert CC["SENDQ_MAX_GAP"] == 60


def test_draining_queue_is_not_stuck():
    res = poll([(0, 0), (1, 108), (2, 0)])
    assert [r[0] for r in res] == [False, False, False]
    assert res[-1][1] == {}, res[-1][1]


def test_equal_queue_over_stuck_secs_is_disconnected():
    res = poll([(0, 948), (9, 948)])
    assert [r[0] for r in res] == [False, True]


def test_two_polls_within_stuck_secs_are_not_enough():
    # Два пикера опросили подряд: второй замер ничего не доказывает.
    res = poll([(0, 948), (0.3, 948)])
    assert [r[0] for r in res] == [False, False]


def test_growing_queue_counts_as_stuck():
    res = poll([(0, 748), (5, 848), (10, 948)])
    assert [r[0] for r in res] == [False, False, True]


def test_decrease_resets():
    res = poll([(0, 948), (9, 500)])
    assert res[-1][0] is False
    assert res[-1][1][K]["since"] == 9, res[-1][1]


def test_gap_over_max_resets():
    # Бэкофф скрытого пикера: два всплеска с разницей в восемь минут — не улика.
    res = poll([(0, 948), (500, 948)])
    assert [r[0] for r in res] == [False, False]
    assert res[-1][1][K]["since"] == 500


def test_any_drain_between_samples_resets():
    # Очередь дважды рассосалась, хоть ни разу и не упала ниже первого замера:
    # это пишущая и здоровая сессия, а не застрявшая.
    res = poll([(0, 36), (3, 500), (6, 100), (9, 400)])
    assert [r[0] for r in res] == [False, False, False, False]
    assert res[-1][1][K]["since"] == 6, res[-1][1]


def test_verdict_is_stable_while_stuck():
    res = poll([(0, 948), (9, 948), (10, 960), (11, 960), (12, 1000)])
    assert [r[0] for r in res] == [False, True, True, True, True]


def test_vanished_key_is_dropped():
    _, prev = CC["sendq_verdicts"]({K: 948}, {}, 0)
    disc, prev = CC["sendq_verdicts"]({}, prev, 9)
    assert disc == set() and prev == {}, (disc, prev)


# ---- проба в --state: фальшивый /proc --------------------------------------

import json
import tempfile

SID = "aaaaaaaa-1111-2222-3333-444444444444"


def fake_proc(root, procs, tcp):
    """procs: {pid: (argv, environ-пары)}; tcp — текст /proc/net/tcp."""
    os.makedirs(os.path.join(root, "net"), exist_ok=True)
    with open(os.path.join(root, "net", "tcp"), "w") as fh:
        fh.write(tcp)
    for pid, (argv, envp) in procs.items():
        d = os.path.join(root, str(pid))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "cmdline"), "wb") as fh:
            fh.write("\0".join(argv).encode() + b"\0")
        with open(os.path.join(d, "environ"), "wb") as fh:
            fh.write(env(*envp))
        with open(os.path.join(d, "stat"), "w") as fh:
            # 22-е поле — starttime; comm с пробелом, как бывает в жизни.
            fh.write("%d (claude x) S 1 %s 4242 0\n" % (pid, " ".join(["0"] * 17)))


STUCK_ENV = ("SSH_CONNECTION=192.0.2.15 63374 192.0.2.14 22",)
IDLE_ENV = ("SSH_CONNECTION=192.0.2.15 60372 192.0.2.14 22",)


def probe_twice(procs_rec, proc_tree, tcp):
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "proc")
        fake_proc(root, proc_tree, tcp)
        state = os.path.join(tmp, "cache", "sendq.json")
        first = CC["disconnected_ids"](procs_rec, root, state, 0)
        second = CC["disconnected_ids"](procs_rec, root, state, 9)
        return first, second, os.path.exists(state)


def test_disconnected_ids_marks_stuck_socket():
    first, second, _ = probe_twice(
        {SID: {"pid": 100, "tmux": None, "zellij": None}},
        {100: (["claude", "-n", "api"], STUCK_ENV)},
        "\n".join([HEADER, TCP_STUCK, TCP_IDLE]))
    assert first == set() and second == {SID}, (first, second)


def test_disconnected_ids_idle_socket():
    _, second, _ = probe_twice(
        {SID: {"pid": 100, "tmux": None, "zellij": None}},
        {100: (["claude"], IDLE_ENV)},
        "\n".join([HEADER, TCP_STUCK, TCP_IDLE]))
    assert second == set(), second


def test_disconnected_ids_skips_multiplexer():
    for mux in ({"tmux": "%3", "zellij": None}, {"tmux": None, "zellij": "home"}):
        _, second, _ = probe_twice(
            {SID: dict(pid=100, **mux)},
            {100: (["claude"], STUCK_ENV)},
            "\n".join([HEADER, TCP_STUCK]))
        assert second == set(), (mux, second)


def test_disconnected_ids_follows_reptyr():
    # Сессию перенёс `reptyr -T`: у агента старый SSH_CONNECTION с застрявшим
    # сокетом, а держит её reptyr под новым ssh, у которого очередь пуста.
    _, second, _ = probe_twice(
        {SID: {"pid": 100, "tmux": None, "zellij": None}},
        {100: (["claude"], STUCK_ENV),
         200: (["reptyr", "-T", "100"], IDLE_ENV)},
        "\n".join([HEADER, TCP_STUCK, TCP_IDLE]))
    assert second == set(), second


def test_disconnected_ids_follows_reptyr_chain():
    # Второй перенос целится в первый reptyr; держатель — последнее звено.
    _, second, _ = probe_twice(
        {SID: {"pid": 100, "tmux": None, "zellij": None}},
        {100: (["claude"], IDLE_ENV),
         200: (["/usr/bin/reptyr", "-T", "100"], IDLE_ENV),
         300: (["reptyr", "200"], STUCK_ENV)},
        "\n".join([HEADER, TCP_STUCK, TCP_IDLE]))
    assert second == {SID}, second


def test_disconnected_ids_without_socket_or_peer():
    # Местная сессия (SSH_CONNECTION нет) и сессия без своего сокета — не улика.
    _, second, _ = probe_twice(
        {SID: {"pid": 100, "tmux": None, "zellij": None},
         "b": {"pid": 101, "tmux": None, "zellij": None}},
        {100: (["claude"], ("HOME=/h",)),
         101: (["claude"], ("SSH_CONNECTION=192.0.2.99 1 192.0.2.14 22",))},
        "\n".join([HEADER, TCP_STUCK]))
    assert second == set(), second


def test_disconnected_ids_without_proc_root():
    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, "sendq.json")
        got = CC["disconnected_ids"]({SID: {"pid": 100}}, os.path.join(tmp, "nope"), state, 0)
        assert got == set() and not os.path.exists(state), got


def test_disconnected_ids_survives_broken_state_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "proc")
        fake_proc(root, {100: (["claude"], STUCK_ENV)}, "\n".join([HEADER, TCP_STUCK]))
        state = os.path.join(tmp, "sendq.json")
        with open(state, "w") as fh:
            fh.write("{не json")
        rec = {SID: {"pid": 100, "tmux": None, "zellij": None}}
        assert CC["disconnected_ids"](rec, root, state, 0) == set()
        assert CC["disconnected_ids"](rec, root, state, 9) == {SID}
        with open(state) as fh:
            json.load(fh)


def test_disconnected_ids_empty_path_disables():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "proc")
        fake_proc(root, {100: (["claude"], STUCK_ENV)}, "\n".join([HEADER, TCP_STUCK]))
        rec = {SID: {"pid": 100, "tmux": None, "zellij": None}}
        assert CC["disconnected_ids"](rec, root, "", 0) == set()
        assert CC["disconnected_ids"](rec, root, "", 9) == set()


def test_state_branch_emits_field():
    # Проводку ветки state сквозным прогоном не поймать: настоящий /proc в
    # тесте не подделать. Сторожится форма — вызов пробы и поле записи.
    src = harness.block()
    state = src.split('elif mode == "state"', 1)[1].split("\nelif mode", 1)[0]
    assert "disconnected_ids(procs)" in state
    assert '"disconnected": sid in disconnected' in state


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
