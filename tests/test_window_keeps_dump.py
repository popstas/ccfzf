"""Окно трекера держит сессию в дампе за пределом среза. Запуск: python3 tests/test_window_keeps_dump.py

Сессия с мёртвым процессом и открытым терминалом (`kitty --hold`) за пределом
`--limit` живёт в ответе `--state` и в дампе только потому, что трекер держит
её окно: `live |= set(windows)`, а `pick_files` добавляет к срезу всех живых.
Дамп — индекс, по которому трекер привязывает окна. Выпади сессия из него, и
окно её больше не привяжется никогда: привязки нет — нет и записи окна, нет
записи — нет строки в дампе. Кольцо снято 2026-11-22 (разбор — пункт «Окно на
экране есть, а привязки к сессии нет» в ccfzf-picker/docs/TODO.md); второй его
конец чинится в трекерах откатом на слоты, а здесь сторожится этот: связка
«запись окна → строка дампа» стоит на двух строках режима `state`, и юнит
`test_pick_files.py` ни одну из них не видит.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

OLD = "aaaaaaaa-1111-2222-3333-444444444444"
NEW_A = "bbbbbbbb-1111-2222-3333-444444444444"
NEW_B = "cccccccc-1111-2222-3333-444444444444"
CWD = "/w/ExpertizeMe"


def _transcript(projects, sid, title, mtime):
    """Транскрипт с одной репликой и именем сессии, датированный `mtime`."""
    path = os.path.join(projects, sid + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "cwd": CWD, "sessionId": sid,
                             "timestamp": "2026-08-22T00:00:00Z",
                             "message": {"role": "user", "content": "hi"}}) + "\n")
        fh.write(json.dumps({"type": "custom-title", "customTitle": title,
                             "sessionId": sid}) + "\n")
    os.utime(path, (mtime, mtime))


def _world(home, with_window):
    """Три сессии одного каталога; старейшая — за пределом `--limit 2`.

    Окно, если есть, у старейшей: её процесса нет, и живой она бывает только
    по записи трекера.
    """
    now = time.time()
    projects = os.path.join(home, ".claude", "projects", "-w-ExpertizeMe")
    os.makedirs(projects)
    _transcript(projects, OLD, "ExpertizeMe-2", now - 36000)
    _transcript(projects, NEW_A, "other-a", now - 600)
    _transcript(projects, NEW_B, "other-b", now - 60)
    wdir = os.path.join(home, ".ccfzf", "windows")
    os.makedirs(wdir)
    windows = {OLD: {"title": "ExpertizeMe-2", "lastSeen": now}} if with_window else {}
    with open(os.path.join(wdir, "mac.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": now, "host": "mac", "pid": 1, "windows": windows}, fh)
    return wdir


def _run_state(home, wdir):
    """Режим `state` с явными путями: ни памятки фактов, ни чужого окружения."""
    dump = os.path.join(home, "sessions.json")
    saved = {k: os.environ.get(k) for k in ("HOME", "CCFZF_FACTS_FILE",
                                             "CCFZF_STATE_DUMP_MAX_AGE")}
    os.environ.update({"HOME": home, "CCFZF_FACTS_FILE": "",
                       "CCFZF_STATE_DUMP_MAX_AGE": "0"})
    try:
        out, _ = harness.run(["state", os.path.join(home, "marks"), "", dump, "2",
                              wdir, "", "", "", ""])
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    with open(dump, encoding="utf-8") as fh:
        return json.loads(out), json.load(fh)


def _row(sessions, sid):
    return next((s for s in sessions if s["id"] == sid), None)


def test_a_window_keeps_a_session_past_the_limit_in_the_answer_and_the_dump():
    with tempfile.TemporaryDirectory() as home:
        state, dump = _run_state(home, _world(home, with_window=True))
        for where, sessions in (("--state", state["sessions"]), ("dump", dump["sessions"])):
            row = _row(sessions, OLD)
            assert row is not None, "%s потерял сессию с открытым окном" % where
            assert row["live"] is True, "%s: живой её делает окно" % where
            assert row["title"] == "ExpertizeMe-2", row
        assert not _row(state["sessions"], OLD).get("pid"), "процесса у неё нет"


def test_without_a_window_the_session_past_the_limit_is_gone_from_both():
    # Вторая половина кольца, ради которой трекеры откатываются на слоты:
    # без записи окна строки нет ни в ответе, ни в дампе, и индекс трекера
    # её не знает. Сломается этот тест — значит, срез стал держать и мёртвых
    # без окна, и откат в трекерах можно пересмотреть.
    with tempfile.TemporaryDirectory() as home:
        state, dump = _run_state(home, _world(home, with_window=False))
        assert _row(state["sessions"], OLD) is None, state["sessions"]
        assert _row(dump["sessions"], OLD) is None, dump["sessions"]
        assert {s["id"] for s in dump["sessions"]} == {NEW_A, NEW_B}


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("ok  ", t.__name__)
        except Exception as e:  # noqa: BLE001 — отчёт о любом падении
            failed += 1
            print("FAIL", t.__name__, repr(e))
    print("%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)
