"""Флаг «автокомпакт выключен» у сессии и то, что нужно таймеру пикера в --state.

Таймер автокомпакта живёт в пикере на nb (решение Стаса 27.11, 1a), а флаг —
здесь, на машине агрегатора, по образцу комментария: пикеры всех машин читают
его из `--state` и ставят по ssh (`ccfzf --auto-compact <id> on|off`).

Запуск: python3 tests/test_autocompact.py
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccfzf")
SID = "aaaaaaaa-1111-2222-3333-444444444444"
OTHER = "bbbbbbbb-1111-2222-3333-444444444444"
T_CACHE = 1785958060


# ── хранилище ──────────────────────────────────────────────────────────────

def test_off_is_written_and_read_back():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ac.json")
        assert CC["set_autocompact"](p, SID, False, 100.0, "nb") is True
        assert CC["read_autocompact"](p) == {SID}
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
        assert raw == {SID: {"off": True, "at": 100.0, "host": "nb"}}, raw


def test_on_removes_the_entry():
    # Включено — умолчание: записи нет вовсе, как у пустого комментария.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ac.json")
        CC["set_autocompact"](p, SID, False, 100.0, "nb")
        CC["set_autocompact"](p, SID, True, 200.0, "nb")
        assert CC["read_autocompact"](p) == set()


def test_writing_one_keeps_the_others():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ac.json")
        CC["set_autocompact"](p, SID, False, 100.0, "nb")
        CC["set_autocompact"](p, OTHER, False, 101.0, "mac")
        CC["set_autocompact"](p, SID, True, 102.0, "nb")
        assert CC["read_autocompact"](p) == {OTHER}


def test_only_a_session_id_is_accepted():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ac.json")
        assert CC["set_autocompact"](p, "../etc/passwd", False, 1.0, "nb") is False
        assert CC["read_autocompact"](p) == set()


def test_missing_broken_or_odd_entries_read_as_on():
    # Файл пишет чужая версия ccfzf: незнакомое теряется молча, а не роняет
    # ответ --state.
    with tempfile.TemporaryDirectory() as d:
        assert CC["read_autocompact"](os.path.join(d, "нет.json")) == set()
        assert CC["read_autocompact"]("") == set()
        p = os.path.join(d, "bad.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{не json")
        assert CC["read_autocompact"](p) == set()
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({SID: {"off": True}, OTHER: {"off": "yes"}, "не-id": {"off": True}}, fh)
        assert CC["read_autocompact"](p) == {SID}


# ── командная строка ───────────────────────────────────────────────────────

def _cli(args, p, path=None):
    env = dict(os.environ, CCFZF_AUTOCOMPACT_FILE=p)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(["bash", SRC, "--auto-compact", *args],
                          capture_output=True, text=True, env=env)


def test_cli_off_then_on():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ac.json")
        r = _cli([SID, "off", "nb"], p)
        assert r.returncode == 0, (r.returncode, r.stderr)
        assert CC["read_autocompact"](p) == {SID}
        r = _cli([SID, "on"], p)
        assert r.returncode == 0, (r.returncode, r.stderr)
        assert CC["read_autocompact"](p) == set()


def test_cli_refuses_a_bad_value_or_id():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ac.json")
        r = _cli([SID, "maybe"], p)
        assert r.returncode == 2, (r.returncode, r.stderr)
        assert "on|off" in r.stderr, r.stderr
        r = _cli([SID], p)
        assert r.returncode == 2, (r.returncode, r.stderr)
        r = _cli(["not-an-id", "off"], p)
        assert r.returncode == 2, (r.returncode, r.stderr)
        assert not os.path.exists(p)


def test_cli_does_not_need_fzf():
    # Как --comment: пикер зовёт по ssh и на машине, где fzf нет.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ac.json")
        keep = [os.path.dirname(shutil.which("python3")), "/usr/bin", "/bin"]
        path = os.pathsep.join(keep)
        assert shutil.which("fzf", path=path) is None, path
        r = _cli([SID, "off"], p, path=path)
        assert r.returncode == 0, (r.returncode, r.stderr)
        assert CC["read_autocompact"](p) == {SID}


# ── --state ────────────────────────────────────────────────────────────────

def _stamp(at):
    return datetime.datetime.fromtimestamp(
        at, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def build_home(tmp, sids):
    cwd = os.path.join(tmp, "proj")
    os.makedirs(cwd, exist_ok=True)
    d = os.path.join(tmp, ".claude", "projects", re.sub(r"[^a-zA-Z0-9]", "-", cwd))
    os.makedirs(d, exist_ok=True)
    for i, sid in enumerate(sids):
        path = os.path.join(d, sid + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"cwd": cwd, "type": "user", "timestamp": _stamp(T_CACHE - 60),
                                 "message": {"role": "user", "content": "hello"}}) + "\n")
            fh.write(json.dumps({"type": "assistant", "timestamp": _stamp(T_CACHE),
                                 "message": {"role": "assistant", "stop_reason": "end_turn",
                                             "content": [{"type": "text", "text": "готово"}],
                                             "usage": {"input_tokens": 3, "output_tokens": 10,
                                                       "cache_read_input_tokens": 100,
                                                       "cache_creation_input_tokens": 0}}}) + "\n")
            fh.write(json.dumps({"type": "custom-title", "customTitle": "t%d" % i}) + "\n")
        os.utime(path, (2000 + i, 2000 + i))


def run_state(tmp, ac_path, *extra):
    env = dict(os.environ)
    env.update({
        "HOME": tmp,
        "FZF_MARKS_FILE": os.path.join(tmp, "no-marks"),
        "CCFZF_SESSIONS_FILE": os.path.join(tmp, "dump.json"),
        "CCFZF_PROJECTS_FILE": "",
        "CCFZF_WINDOWS_FILE": "",
        "CCFZF_FACTS_FILE": os.path.join(tmp, "facts.json"),
        "XDG_CACHE_HOME": os.path.join(tmp, "cache"),
        "CCFZF_AUTOCOMPACT_FILE": ac_path,
    })
    r = subprocess.run(["bash", SRC, "--state", *extra], capture_output=True, text=True, env=env)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return json.loads(r.stdout)


def test_state_marks_only_the_off_session():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [SID, OTHER])
        p = os.path.join(tmp, "ac.json")
        CC["set_autocompact"](p, SID, False, 100.0, "nb")
        by_id = {s["id"]: s for s in run_state(tmp, p)["sessions"]}
        # Ложь доезжает: state_record выбрасывает пустое, но не этот ключ.
        assert by_id[SID].get("autoCompact") is False, by_id[SID]
        assert "autoCompact" not in by_id[OTHER], by_id[OTHER]


def test_toggling_changes_the_fingerprint():
    # Иначе --if-changed ответил бы `unchanged`, и пикер не увидел бы флаг.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [SID])
        p = os.path.join(tmp, "ac.json")
        before = run_state(tmp, p)["fingerprint"]
        CC["set_autocompact"](p, SID, False, 100.0, "nb")
        after = run_state(tmp, p, "--if-changed", before)
        assert after.get("unchanged") is not True, after
        assert after["fingerprint"] != before


def test_off_file_disabled_reads_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [SID])
        out = run_state(tmp, "")
        assert "autoCompact" not in out["sessions"][0], out["sessions"][0]


def test_cache_at_reaches_the_state_answer():
    # Часы автокомпакта пикера — agent.cacheAt (последний ответ с кешем), а не
    # updated: idle-уведомление и fail двигают updated без запроса к API.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [SID])
        row = run_state(tmp, os.path.join(tmp, "ac.json"))["sessions"][0]
        assert row["agent"].get("cacheAt") == T_CACHE, row


def test_state_record_keeps_false_auto_compact_only():
    rec = CC["state_record"]({"id": SID, "cwd": "/x", "title": "t", "mtime": 1,
                              "live": False, "kind": "interactive", "autoCompact": False,
                              "comment": ""})
    assert rec["autoCompact"] is False, rec
    assert "comment" not in rec, rec


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
