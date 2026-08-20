"""Тесты живости сессий. Запуск: python3 tests/test_liveness.py"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "bbbbbbbb-1111-2222-3333-444444444444"


def test_arg_value_reads_the_equals_form():
    """Claude Desktop зовёт агента `--resume=<id>` — одним токеном.

    Пробельную форму пишет терминальный клиент, форму с равенством —
    приложение. Не понимай её агрегатор, id сессии из argv не доставался бы
    вовсе: строка оставалась бы без pid, а живость ей доставалась бы обходным
    путём — по каталогу живого процесса, то есть в каталоге с двумя сессиями
    доставалась бы не той.
    """
    args = ["/x/claude", "--resume=" + UUID_A, "--effort", "high"]
    assert CC["arg_value"](args, "--resume") == UUID_A, args


def test_arg_value_still_reads_the_spaced_form():
    args = ["/x/claude", "--resume", UUID_A]
    assert CC["arg_value"](args, "--resume") == UUID_A, args


def test_arg_value_does_not_take_a_longer_flag_for_its_prefix():
    """`--session-id` не должен вычитываться из `--session-id-foo=…`.

    Форма с равенством — это поиск по началу строки, и без явного `=` он
    поймал бы любой флаг, начинающийся тем же словом.
    """
    args = ["/x/claude", "--session-id-foo=" + UUID_A]
    assert CC["arg_value"](args, "--session-id") == "", args


def test_arg_value_reads_an_empty_equals_form_as_nothing():
    args = ["/x/claude", "--resume="]
    assert CC["arg_value"](args, "--resume") == "", args


def test_hook_stamps_reads_mtime_of_state_files():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, UUID_A + ".state.json")
        with open(path, "w") as fh:
            fh.write("{}")
        os.utime(path, (1000, 1000))
        assert CC["hook_stamps"](d) == {UUID_A: 1000}


def test_hook_stamps_ignores_everything_but_state_files():
    with tempfile.TemporaryDirectory() as d:
        for name in (UUID_A + ".status.json", UUID_A + ".meta.json",
                     "not-a-uuid.state.json", "README"):
            with open(os.path.join(d, name), "w") as fh:
                fh.write("{}")
        assert CC["hook_stamps"](d) == {}


def test_hook_stamps_survives_a_missing_directory():
    assert CC["hook_stamps"]("/nonexistent-dir-for-tests") == {}


def _proc(pid, cwd="/p"):
    return {"pid": pid, "tty": "/dev/pts/1", "tmux": None, "cwd": cwd}


def test_reattribute_moves_the_process_to_the_id_being_written():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_B}, live
    assert UUID_A not in procs, procs
    assert procs[UUID_B]["pid"] == 42, procs


def test_reattribute_leaves_a_candidate_owned_by_another_process():
    now = time.time()
    live, procs, agents = {UUID_A, UUID_B}, {UUID_A: _proc(42), UUID_B: _proc(43)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_A, UUID_B}, live
    assert procs[UUID_A]["pid"] == 42, procs


def test_reattribute_ignores_a_candidate_whose_hook_went_quiet():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 3600}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_A}, live
    assert procs[UUID_A]["pid"] == 42, procs


def test_reattribute_carries_the_background_mark_along():
    now = time.time()
    live, procs = {UUID_A}, {UUID_A: _proc(42)}
    agents = {UUID_A: {"kind": "background", "parent": "p"}}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert agents == {UUID_B: {"kind": "background", "parent": "p"}}, agents


def test_reattribute_does_nothing_without_a_cwd():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42, cwd="")}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B])
    assert live == {UUID_A}, live


def test_live_by_hook_adds_a_working_session_no_process_names():
    now = time.time()
    live = set()
    CC["live_by_hook"](live, {UUID_A: now - 10}, now)
    assert live == {UUID_A}, live


def test_live_by_hook_keeps_a_running_session_whose_hook_is_silent():
    now = time.time()
    live = {UUID_B}
    CC["live_by_hook"](live, {UUID_B: now - 86400}, now)
    assert live == {UUID_B}, live


def test_live_by_hook_does_not_resurrect_a_session_that_went_quiet():
    now = time.time()
    live = set()
    CC["live_by_hook"](live, {UUID_A: now - 3600}, now)
    assert live == set(), live


def test_live_by_hook_does_not_resurrect_an_id_reattribute_just_vacated():
    # Ротация A->B тридцать секунд назад: без skip live_by_hook добавил бы
    # A обратно по его ещё не остывшей отметке — ровно та дублирующая
    # строка, ради ухода от которой существует reattribute().
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 30, UUID_B: now - 5}
    moved = CC["reattribute"](live, procs, agents, stamps, now,
                              ids_in=lambda cwd: [UUID_A, UUID_B])
    CC["live_by_hook"](live, stamps, now, skip=moved)
    assert live == {UUID_B}, live


def test_reattribute_does_not_let_a_second_process_reclaim_a_vacated_id():
    # UUID_A переезжает на UUID_B (его хук свежее) и освобождает UUID_A.
    # UUID_IDLE — второй, простаивающий процесс в том же каталоге: его
    # собственная отметка старая, а у освобождённого UUID_A она ещё не
    # остыла, так что без защиты он выглядел бы для UUID_IDLE лучшим
    # кандидатом — хотя в этот транскрипт больше никто не пишет.
    UUID_IDLE = "cccccccc-1111-2222-3333-444444444444"
    now = time.time()
    live = {UUID_A, UUID_IDLE}
    procs = {UUID_A: _proc(42), UUID_IDLE: _proc(43)}
    agents = {}
    stamps = {UUID_A: now - 25, UUID_B: now - 5, UUID_IDLE: now - 3600}

    def ids_in(cwd):
        return [UUID_A, UUID_B, UUID_IDLE]

    CC["reattribute"](live, procs, agents, stamps, now, ids_in=ids_in)
    assert procs.get(UUID_A) is None, procs
    assert procs[UUID_IDLE]["pid"] == 43, procs
    assert UUID_A not in live, live


def test_reattribute_returns_the_ids_it_vacated():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    moved = CC["reattribute"](live, procs, agents, stamps, now,
                              ids_in=lambda cwd: [UUID_A, UUID_B])
    assert moved == {UUID_A}, moved


def test_reattribute_returns_an_empty_set_when_nothing_moves():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 3600}
    moved = CC["reattribute"](live, procs, agents, stamps, now,
                              ids_in=lambda cwd: [UUID_A, UUID_B])
    assert moved == set(), moved


def test_hook_stamps_reads_both_of_two_state_files():
    with tempfile.TemporaryDirectory() as d:
        path_a = os.path.join(d, UUID_A + ".state.json")
        path_b = os.path.join(d, UUID_B + ".state.json")
        with open(path_a, "w") as fh:
            fh.write("{}")
        with open(path_b, "w") as fh:
            fh.write("{}")
        os.utime(path_a, (1000, 1000))
        os.utime(path_b, (2000, 2000))
        assert CC["hook_stamps"](d) == {UUID_A: 1000, UUID_B: 2000}


BOOT = "00000000-aaaa-bbbb-cccc-000000000000"


def _meta(d, sid, pid, started, pid_started=777, boot=BOOT):
    body = {"sessionId": sid, "pid": pid, "pidStarted": pid_started,
            "started": started, "boot": boot}
    with open(os.path.join(d, sid + ".meta.json"), "w") as fh:
        json.dump(body, fh)


def test_pid_owners_reads_the_pid_the_hook_wrote():
    with tempfile.TemporaryDirectory() as d:
        _meta(d, UUID_A, 42, 1000)
        assert CC["pid_owners"](d, boot=BOOT) == {42: (UUID_A, 777)}


def test_pid_owners_keeps_the_latest_id_of_one_process():
    with tempfile.TemporaryDirectory() as d:
        _meta(d, UUID_A, 42, 1000)
        _meta(d, UUID_B, 42, 2000)
        assert CC["pid_owners"](d, boot=BOOT) == {42: (UUID_B, 777)}


def test_pid_owners_drops_records_from_another_boot():
    with tempfile.TemporaryDirectory() as d:
        _meta(d, UUID_A, 42, 1000, boot="ffffffff-dead-dead-dead-ffffffffffff")
        assert CC["pid_owners"](d, boot=BOOT) == {}


def test_pid_owners_ignores_files_the_old_hook_wrote():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, UUID_A + ".meta.json"), "w") as fh:
            json.dump({"sessionId": UUID_A, "cwd": "/p", "started": 1000}, fh)
        assert CC["pid_owners"](d, boot=BOOT) == {}


def test_pid_owners_survives_junk_and_a_missing_directory():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, UUID_A + ".meta.json"), "w") as fh:
            fh.write("{not json")
        _meta(d, UUID_B, 42, 1000)
        assert CC["pid_owners"](d, boot=BOOT) == {42: (UUID_B, 777)}
    assert CC["pid_owners"]("/nonexistent-dir-for-tests", boot=BOOT) == {}


def test_reattribute_by_pid_moves_the_process_to_the_id_the_hook_named():
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    moved, resolved = CC["reattribute_by_pid"](
        live, procs, agents, {42: (UUID_B, 777)}, started_of=lambda pid: 777)
    assert live == {UUID_B}, live
    assert procs[UUID_B]["pid"] == 42, procs
    assert moved == {UUID_A} and resolved == {UUID_B}, (moved, resolved)


def test_reattribute_by_pid_leaves_a_process_already_on_its_own_id():
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    moved, resolved = CC["reattribute_by_pid"](
        live, procs, agents, {42: (UUID_A, 777)}, started_of=lambda pid: 777)
    assert live == {UUID_A} and moved == set(), (live, moved)
    assert resolved == {UUID_A}, resolved


def test_reattribute_by_pid_refuses_a_recycled_pid():
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    moved, resolved = CC["reattribute_by_pid"](
        live, procs, agents, {42: (UUID_B, 777)}, started_of=lambda pid: 999)
    assert live == {UUID_A}, live
    assert procs[UUID_A]["pid"] == 42 and moved == set(), (procs, moved)


def test_reattribute_by_pid_carries_the_background_mark_along():
    live, procs = {UUID_A}, {UUID_A: _proc(42)}
    agents = {UUID_A: {"kind": "background", "parent": "p"}}
    CC["reattribute_by_pid"](live, procs, agents, {42: (UUID_B, 777)},
                             started_of=lambda pid: 777)
    assert agents == {UUID_B: {"kind": "background", "parent": "p"}}, agents


def test_reattribute_leaves_alone_what_the_pid_pass_settled():
    now = time.time()
    live, procs, agents = {UUID_A}, {UUID_A: _proc(42)}, {}
    stamps = {UUID_A: now - 86400, UUID_B: now - 30}
    CC["reattribute"](live, procs, agents, stamps, now,
                      ids_in=lambda cwd: [UUID_A, UUID_B],
                      skip_procs={UUID_A})
    assert live == {UUID_A}, live
    assert procs[UUID_A]["pid"] == 42, procs


def _jsonl(d, name, records):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return path


def test_last_message_at_reads_the_newest_stamped_record():
    with tempfile.TemporaryDirectory() as d:
        path = _jsonl(d, "a.jsonl", [
            {"type": "user", "timestamp": "2026-08-05T19:00:00.000Z"},
            {"type": "assistant", "timestamp": "2026-08-05T19:51:00.000Z"},
        ])
        assert CC["last_message_at"](path) == 1785959460.0, CC["last_message_at"](path)


def test_last_message_at_ignores_service_records_without_a_stamp():
    # Ровно тот случай, ради которого функция и появилась: в хвосте живого
    # файла лежат last-prompt / custom-title / mode, у них времени нет, а
    # mtime Claude Code им обновляет спустя дни после разговора.
    with tempfile.TemporaryDirectory() as d:
        path = _jsonl(d, "a.jsonl", [
            {"type": "assistant", "timestamp": "2026-08-01T20:11:00.000Z"},
            {"type": "last-prompt", "lastPrompt": "..."},
            {"type": "custom-title", "customTitle": "obsidian"},
            {"type": "mode", "mode": "default"},
        ])
        assert CC["last_message_at"](path) == 1785615060.0, CC["last_message_at"](path)


def test_last_message_at_gives_zero_when_nothing_is_stamped():
    with tempfile.TemporaryDirectory() as d:
        path = _jsonl(d, "a.jsonl", [{"type": "mode", "mode": "default"}])
        assert CC["last_message_at"](path) == 0.0


def test_last_message_at_survives_junk_and_a_missing_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "a.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
            fh.write(json.dumps({"type": "user", "timestamp": "не время"}) + "\n")
            fh.write(json.dumps({"type": "user", "timestamp": 123}) + "\n")
        assert CC["last_message_at"](path) == 0.0
    assert CC["last_message_at"]("/nonexistent-file-for-tests.jsonl") == 0.0


def _fat(record, size):
    """Та же запись, но длиннее `size` байт: одна вставленная картинка."""
    return dict(record, pad="x" * size)


def test_last_message_at_reads_a_record_wider_than_the_tail():
    # Единственная запись, и она шире хвоста: в первый срез не попадает ни
    # одной целой строки. Без второго захода работающая сессия отдала бы 0 и
    # выпала бы из живых.
    with tempfile.TemporaryDirectory() as d:
        path = _jsonl(d, "a.jsonl", [
            _fat({"type": "assistant", "timestamp": "2026-08-05T19:51:00.000Z"},
                 CC["TAIL"]),
        ])
        assert os.path.getsize(path) > CC["TAIL"]
        assert CC["last_message_at"](path) == 1785959460.0, CC["last_message_at"](path)


def test_last_message_at_reads_a_wide_record_behind_service_ones():
    # Тот же случай в живом виде: широкая запись, а за ней хвост служебных без
    # времени. Целые строки в первом срезе есть, времени в них нет.
    with tempfile.TemporaryDirectory() as d:
        path = _jsonl(d, "a.jsonl", [
            _fat({"type": "assistant", "timestamp": "2026-08-01T20:11:00.000Z"},
                 CC["TAIL"]),
            {"type": "last-prompt", "lastPrompt": "..."},
            {"type": "custom-title", "customTitle": "obsidian"},
            {"type": "mode", "mode": "default"},
        ])
        assert CC["last_message_at"](path) == 1785615060.0, CC["last_message_at"](path)


def test_last_message_at_gives_zero_after_a_fruitless_second_pass():
    # Файл больше хвоста, времени нет нигде: повтор отработал и честно вернул
    # «возраст неизвестен».
    with tempfile.TemporaryDirectory() as d:
        path = _jsonl(d, "a.jsonl", [
            _fat({"type": "mode", "mode": "default"}, CC["TAIL"]),
            {"type": "last-prompt", "lastPrompt": "..."},
        ])
        assert os.path.getsize(path) > CC["TAIL"]
        assert CC["last_message_at"](path) == 0.0


def test_fresh_ids_takes_the_newest_transcript_by_content():
    # Файл со свежим mtime, но старым содержимым, проигрывает файлу, чьё
    # содержимое новее. Сортировка идёт по содержимому, mtime не спрашивается.
    now = time.time()
    live = set()
    ages = {"/p/" + UUID_A + ".jsonl": now - 60, "/p/" + UUID_B + ".jsonl": now - 600}
    CC["fresh_ids"](["/p"], live, now,
                    files_in=lambda cwd: sorted(ages), age_of=ages.get)
    assert live == {UUID_A}, live


def test_fresh_ids_gives_each_process_its_own_file():
    now = time.time()
    live = set()
    ages = {"/p/" + UUID_A + ".jsonl": now - 60, "/p/" + UUID_B + ".jsonl": now - 600}
    CC["fresh_ids"](["/p", "/p"], live, now,
                    files_in=lambda cwd: sorted(ages), age_of=ages.get)
    assert live == {UUID_A, UUID_B}, live


def test_fresh_ids_drops_a_candidate_whose_content_is_stale():
    # Тот самый случай 2026-08-08: mtime 26 минут, последнее сообщение неделю
    # назад. По mtime сессия считалась живой, по содержимому — нет.
    now = time.time()
    live = set()
    ages = {"/p/" + UUID_A + ".jsonl": now - 7 * 86400}
    CC["fresh_ids"](["/p"], live, now,
                    files_in=lambda cwd: sorted(ages), age_of=ages.get)
    assert live == set(), live


def test_fresh_ids_drops_a_file_with_no_stamped_record_at_all():
    # last_message_at отдаёт 0 — «возраст неизвестен». Ноль старше любой
    # отсечки, и такой файл живым не назначается.
    now = time.time()
    live = set()
    CC["fresh_ids"](["/p"], live, now,
                    files_in=lambda cwd: ["/p/" + UUID_A + ".jsonl"],
                    age_of=lambda path: 0.0)
    assert live == set(), live


def test_fresh_ids_does_not_take_a_file_someone_already_owns():
    now = time.time()
    live = {UUID_A}
    ages = {"/p/" + UUID_A + ".jsonl": now - 60, "/p/" + UUID_B + ".jsonl": now - 120}
    CC["fresh_ids"](["/p"], live, now,
                    files_in=lambda cwd: sorted(ages), age_of=ages.get)
    assert live == {UUID_A, UUID_B}, live


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("ok   %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (t.__name__, e))
    print("%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)
