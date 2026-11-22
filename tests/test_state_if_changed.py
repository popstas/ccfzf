"""Условный ответ `--state --if-changed <fp>`.

Пикер зовёт `--state` по ssh раз в секунду, пока окно показано, и почти
каждый раз получает тот же ответ, что секунду назад, — сотни килобайт. Здесь
проверяется короткий ответ «без изменений»: отпечаток в полном ответе,
совпадение и промах, что в отпечаток не входит, и что дамп для трекера
пишется по-прежнему.

Запуск: python3 tests/test_state_if_changed.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from test_state_mode import A, B, SRC, _facts_env, build_home, run_state

NS = harness.load()
state_fingerprint = NS["state_fingerprint"]


def run_raw(tmp, dump_path, *extra, env_extra=None):
    """Обёртка целиком: код возврата, stdout и stderr — без разбора."""
    env = dict(os.environ)
    env.update(_facts_env(tmp, dump_path))
    env.update(env_extra or {})
    return subprocess.run(["bash", SRC, *extra], capture_output=True, text=True, env=env)


def run_block(tmp, dump_path, *argv):
    """Python-блок отдельным процессом — так его зовёт пикер на Windows."""
    py = os.path.join(tmp, "ccfzf.py")
    with open(py, "w", encoding="utf-8") as fh:
        fh.write(harness.block())
    env = dict(os.environ)
    env.update(_facts_env(tmp, dump_path))
    r = subprocess.run([sys.executable, py, *argv], capture_output=True, text=True, env=env)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return json.loads(r.stdout)


def write_window(tmp, sid, **win):
    """Файл трекера с одним окном; возвращает env для run_state."""
    wdir = os.path.join(tmp, "windows")
    os.makedirs(wdir, exist_ok=True)
    now = int(time.time())
    rec = {"title": "t0", "desktop": 1, "lastSeen": now, "focusedAt": 0}
    rec.update(win)
    with open(os.path.join(wdir, "box.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": now, "host": "box", "pid": 42, "windows": {sid: rec}}, fh)
    return {"CCFZF_WINDOWS_DIR": wdir, "CCFZF_WINDOWS_FILE": ""}


def test_the_full_answer_carries_its_fingerprint():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        fp = out.get("fingerprint")
        assert isinstance(fp, str) and re.fullmatch(r"[0-9a-f]{16}", fp), out.get("fingerprint")
        # Полный ответ остался полным: отпечаток — добавка, а не замена.
        assert [s["id"] for s in out["sessions"]] == [A], out


def test_a_matching_fingerprint_gets_the_short_answer():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        dump = os.path.join(tmp, "dump.json")
        fp = run_state(tmp, dump)["fingerprint"]
        r = run_raw(tmp, dump, "--state", "--if-changed", fp)
        assert r.returncode == 0, r.stderr
        short = json.loads(r.stdout)
        assert short.get("unchanged") is True, short
        assert short.get("fingerprint") == fp, short
        assert isinstance(short.get("generated"), (int, float)), short
        # Короткий — значит без списков вовсе: ради этого всё и делается.
        assert "sessions" not in short and "projects" not in short, short
        assert len(r.stdout) < 120, len(r.stdout)


def test_a_stale_fingerprint_gets_the_full_answer():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        dump = os.path.join(tmp, "dump.json")
        out = run_state(tmp, dump, "--if-changed", "0123456789abcdef")
        assert "unchanged" not in out, out
        assert [s["id"] for s in out["sessions"]] == [A], out
        assert out["fingerprint"] != "0123456789abcdef"


def test_a_changed_session_changes_the_fingerprint():
    # Сдвинутый mtime транскрипта — это и есть активность: возраст в строке
    # и порядок списка считаются от него.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        dump = os.path.join(tmp, "dump.json")
        fp = run_state(tmp, dump)["fingerprint"]
        d = os.path.join(tmp, ".claude", "projects")
        path = [os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs if f.endswith(".jsonl")][0]
        os.utime(path, (3000, 3000))
        out = run_state(tmp, dump, "--if-changed", fp)
        assert "unchanged" not in out and out["fingerprint"] != fp, out


def test_window_last_seen_is_outside_the_fingerprint():
    # Трекер переписывает `lastSeen` каждые несколько секунд, а пикер его не
    # читает. Войди он в отпечаток — в тихой системе, где не меняется больше
    # ничего, короткого ответа не было бы почти никогда.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        dump = os.path.join(tmp, "dump.json")
        env = write_window(tmp, A, lastSeen=int(time.time()) - 5)
        fp = run_state(tmp, dump, env_extra=env)["fingerprint"]
        env = write_window(tmp, A, lastSeen=int(time.time()))
        short = json.loads(run_raw(tmp, dump, "--state", "--if-changed", fp, env_extra=env).stdout)
        assert short.get("unchanged") is True, short


def test_what_the_picker_reads_from_a_window_is_inside_the_fingerprint():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        dump = os.path.join(tmp, "dump.json")
        fp = run_state(tmp, dump, env_extra=write_window(tmp, A))["fingerprint"]
        for change in ({"focusedAt": 123}, {"unreadAt": 456}, {"title": "other"}, {"minimized": True}):
            out = run_state(tmp, dump, "--if-changed", fp, env_extra=write_window(tmp, A, **change))
            assert "unchanged" not in out, (change, out.get("unchanged"))


def test_the_dump_is_written_even_on_the_short_answer():
    # Дамп читает windows11-manager, им живут Home Assistant и плата openHASP.
    # Короткий ответ касается только stdout.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        dump = os.path.join(tmp, "dump.json")
        fp = run_state(tmp, dump)["fingerprint"]
        os.remove(dump)
        r = run_raw(tmp, dump, "--state", "--if-changed", fp,
                    env_extra={"CCFZF_STATE_DUMP_MAX_AGE": "0"})
        assert json.loads(r.stdout).get("unchanged") is True, r.stdout
        with open(dump, encoding="utf-8") as fh:
            assert [s["id"] for s in json.load(fh)["sessions"]] == [A]


def test_the_fingerprint_does_not_depend_on_the_hash_seed():
    # Отпечаток считает новый процесс на каждый опрос: зависни он от порядка
    # множеств или словарей, совпадения не было бы никогда.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        dump = os.path.join(tmp, "dump.json")
        fps = {run_state(tmp, dump, env_extra={"PYTHONHASHSEED": seed})["fingerprint"]
               for seed in ("1", "2", "3")}
        assert len(fps) == 1, fps


def test_the_fingerprint_ignores_generated_last_seen_and_key_order():
    a = {"generated": 1, "sessions": [{"id": "x", "mtime": 5,
                                       "window": {"title": "t", "lastSeen": 1},
                                       "windows": [{"title": "t", "lastSeen": 1}]}]}
    b = {"sessions": [{"windows": [{"lastSeen": 9, "title": "t"}],
                       "window": {"lastSeen": 9, "title": "t"},
                       "mtime": 5, "id": "x"}], "generated": 2}
    assert state_fingerprint(a) == state_fingerprint(b)
    c = json.loads(json.dumps(a))
    c["sessions"][0]["mtime"] = 6
    assert state_fingerprint(a) != state_fingerprint(c)
    # Исключения — поимённые: поле, которого здесь никто не называл
    # (следующая задача добавит своё), входит в отпечаток само.
    d = json.loads(json.dumps(a))
    d["sessions"][0]["somethingNew"] = True
    assert state_fingerprint(a) != state_fingerprint(d)
    # Счёт не трогает сам ответ: тот уходит в stdout следом.
    assert a["generated"] == 1 and a["sessions"][0]["window"]["lastSeen"] == 1


def test_the_alias_takes_the_key_in_any_order():
    # Дорога Windows: пикер зовёт вырезанный блок напрямую, без обёртки.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        dump = os.path.join(tmp, "dump.json")
        fp_all = run_block(tmp, dump, "--state")["fingerprint"]
        assert run_block(tmp, dump, "--state", "--if-changed", fp_all).get("unchanged") is True
        one = run_block(tmp, dump, "--state", "--limit", "1")
        assert len(one["sessions"]) == 1, one
        fp_one = one["fingerprint"]
        assert fp_one != fp_all, "другой срез — другой ответ"
        for argv in (("--state", "--limit", "1", "--if-changed", fp_one),
                     ("--state", "--if-changed", fp_one, "--limit", "1")):
            assert run_block(tmp, dump, *argv).get("unchanged") is True, argv


def test_the_wrapper_rejects_the_key_without_a_value_or_without_state():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        dump = os.path.join(tmp, "dump.json")
        r = run_raw(tmp, dump, "--state", "--if-changed")
        assert r.returncode == 2 and "--if-changed" in r.stderr, (r.returncode, r.stderr)
        r = run_raw(tmp, dump, "--dump", "--if-changed", "abc")
        assert r.returncode == 2 and "--if-changed" in r.stderr, (r.returncode, r.stderr)


def test_the_key_order_does_not_matter_in_the_wrapper():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        dump = os.path.join(tmp, "dump.json")
        fp = run_state(tmp, dump, "--limit", "1")["fingerprint"]
        for argv in (("--if-changed", fp, "--state", "--limit", "1"),
                     ("--state", "--if-changed", fp, "--limit", "1")):
            r = run_raw(tmp, dump, *argv)
            assert r.returncode == 0, r.stderr
            assert json.loads(r.stdout).get("unchanged") is True, argv


def test_help_shows_the_key_and_the_whole_header():
    # `usage` печатал строки 2-35 по номерам, и шапка, доросшая до сорока,
    # теряла хвост: последней переменной окружения в --help не было вовсе.
    r = subprocess.run(["bash", SRC, "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "--if-changed" in r.stdout, r.stdout
    assert "CCFZF_STATE_DUMP_MAX_AGE" in r.stdout, r.stdout
    assert "set -euo" not in r.stdout and "MARKS=" not in r.stdout, r.stdout


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
