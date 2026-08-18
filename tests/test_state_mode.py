"""Сквозной прогон режима --state поверх подставного HOME.

Единственный тест, который проверяет саму проводку веток режимов: harness
исполняет python-блок с argv из одного элемента, и ни одна ветка там не
срабатывает — значит соединение функций между собой ловится только так.

Запуск: python3 tests/test_state_mode.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ccfzf")

A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"


def build_home(tmp, sids):
    """~/.claude/projects/<mangled>/<sid>.jsonl, по строке на сессию.

    cwd берётся из первых строк файла (dir_cwd), заголовок — из хвоста
    (tail_facts), поэтому обе записи кладутся сразу.
    """
    cwd = os.path.join(tmp, "proj")
    os.makedirs(cwd, exist_ok=True)
    d = os.path.join(tmp, ".claude", "projects", re.sub(r"[^a-zA-Z0-9]", "-", cwd))
    os.makedirs(d, exist_ok=True)
    for i, sid in enumerate(sids):
        path = os.path.join(d, sid + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"cwd": cwd, "type": "user",
                                 "message": {"role": "user", "content": "hello %d" % i}}) + "\n")
            fh.write(json.dumps({"type": "custom-title", "customTitle": "t%d" % i}) + "\n")
        os.utime(path, (2000 + i, 2000 + i))
    return cwd


def _facts_env(tmp, dump_path):
    return {
        "HOME": tmp,
        "FZF_MARKS_FILE": os.path.join(tmp, "no-marks"),
        "CCFZF_SESSIONS_FILE": dump_path,
        "CCFZF_PROJECTS_FILE": "",
        "CCFZF_WINDOWS_FILE": "",
        "CCFZF_FACTS_FILE": os.path.join(tmp, "facts.json"),
        "XDG_CACHE_HOME": os.path.join(tmp, "cache"),
    }


def run_state(tmp, dump_path, *extra, env_extra=None):
    env = dict(os.environ)
    env.update(_facts_env(tmp, dump_path))
    env.update(env_extra or {})
    r = subprocess.run(["bash", SRC, "--state", *extra],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return json.loads(r.stdout)


def run_dump(tmp, dump_path):
    # Тот же общий facts.json (CCFZF_FACTS_FILE), что и у run_state — оба
    # режима пишут одну памятку, и находки второго круга ревью ровно про то,
    # как записи одного писателя читает другой.
    env = dict(os.environ)
    env.update(_facts_env(tmp, dump_path))
    r = subprocess.run(["bash", SRC, "--dump"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, (r.returncode, r.stderr)


def build_reply_session(tmp, sid, first_prompt, later_reply, mtime=2000):
    """Транскрипт с различимыми gist (первый промпт) и doing (более поздний
    ответ) — нужен, чтобы в тесте отличить, какое из двух значений вернул
    --state после утечки памятки."""
    cwd = os.path.join(tmp, "proj")
    os.makedirs(cwd, exist_ok=True)
    d = os.path.join(tmp, ".claude", "projects", re.sub(r"[^a-zA-Z0-9]", "-", cwd))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, sid + ".jsonl")
    _write_reply_session(path, cwd, first_prompt, later_reply)
    os.utime(path, (mtime, mtime))
    return path, cwd


def _write_reply_session(path, cwd, first_prompt, later_reply):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"cwd": cwd, "type": "user",
                             "message": {"role": "user", "content": first_prompt}}) + "\n")
        fh.write(json.dumps({"type": "assistant",
                             "message": {"role": "assistant", "content": later_reply}}) + "\n")


def test_state_lists_the_fixture_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        assert sorted(s["id"] for s in out["sessions"]) == sorted([A, B]), out["sessions"]


def test_limit_cuts_the_list():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        out = run_state(tmp, os.path.join(tmp, "dump.json"), "--limit", "1")
        assert len(out["sessions"]) == 1, out["sessions"]


def test_activity_at_comes_from_the_hook_file():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        hooks = os.path.join(tmp, ".claude", "claude-wt")
        os.makedirs(hooks)
        state_file = os.path.join(hooks, A + ".state.json")
        with open(state_file, "w", encoding="utf-8") as fh:
            fh.write("{}")
        # Дробная часть — нарочно: mtime файловой системы дробный, а
        # activityAt обязан быть int и floor от него. `1234567890 ==
        # 1234567890.0` в Python истинно, так что сравнение одним `==` не
        # поймало бы регрессию, потерявшую int(...) в ccfzf — json.loads
        # тихо вернул бы float, и assert прошёл бы как ни в чём не бывало.
        os.utime(state_file, (1234567890.7, 1234567890.7))
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        by_id = {s["id"]: s for s in out["sessions"]}
        assert by_id[A]["activityAt"] == 1234567890, by_id[A]
        assert isinstance(by_id[A]["activityAt"], int), by_id[A]
        # Хук про неё не писал — ноль, ровно то же, что сегодня возвращает
        # сетевой вызов у читателя при отсутствии файла.
        assert by_id[B]["activityAt"] == 0, by_id[B]


def test_the_dump_written_on_the_way_has_only_the_eight_fields():
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        dump_path = os.path.join(tmp, "dump.json")
        run_state(tmp, dump_path)
        with open(dump_path, encoding="utf-8") as fh:
            dump = json.load(fh)
        assert dump["sessions"], dump
        for s in dump["sessions"]:
            assert set(s) == {"id", "title", "cwd", "live", "mtime",
                              "kind", "parent", "activityAt"}, s


def test_the_state_answer_keeps_its_rich_shape():
    # Обрезается только файл. Пикер читает stdout, и поля gist/doing/agent
    # рисуются у него в строке — забрать их значило бы опустошить список.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        s = out["sessions"][0]
        for key in ("file", "projects", "gist", "doing", "frozen", "agent"):
            assert key in s, (key, sorted(s))


def test_the_state_answer_carries_the_zellij_list():
    # Список зависит от того, что запущено на машине прямо сейчас, поэтому
    # проверяется форма, а не содержимое: тест, требующий пустоты, падал бы у
    # того, у кого zellij открыт, а требующий непустоты — у всех остальных.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        assert isinstance(out.get("zellij"), list), sorted(out)
        for row in out["zellij"]:
            assert sorted(row) == ["agents", "created", "name", "pid"], sorted(row)
            assert isinstance(row["name"], str) and row["name"], row
            assert isinstance(row["created"], int), row
            assert isinstance(row["agents"], int), row


def test_every_session_says_which_zellij_holds_it():
    # Поле обязано быть у каждой записи, даже когда zellij не при делах:
    # у отрисовщика не должно быть третьего случая «поля нет вовсе» — то же
    # правило, что у `window` и `tmux`.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A])
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        s = out["sessions"][0]
        assert "zellij" in s, sorted(s)
        assert s["zellij"] is None or isinstance(s["zellij"], str), s["zellij"]


def _sorted_sessions(out):
    # `age` завязан на «сейчас» и отличается на каждом опросе по построению
    # (см. комментарий про fingerprint в ccfzf) — сравнивать тёплый и холодный
    # прогон нужно без него, иначе тест не сторожил бы ничего, кроме часов.
    return sorted(
        ({k: v for k, v in s.items() if k != "age"} for s in out["sessions"]),
        key=lambda s: s["id"])


def test_a_warm_run_answers_the_same_as_a_cold_one():
    # Весь смысл дисковой памятки — что второй опрос за тот же файл памятки
    # попадает в кэш по mtime (float из os.stat -> JSON -> сравнение) и
    # ничего не пересчитывает, но список сессий обязан остаться тем же
    # самым. Восемь юнит-тестов рядом гоняют facts_for с фальшивыми
    # tail/head — ни один из них не проверяет ни настоящий ключ по mtime,
    # ни это свойство целиком.
    with tempfile.TemporaryDirectory() as tmp:
        build_home(tmp, [A, B])
        dump_path = os.path.join(tmp, "dump.json")
        cold = run_state(tmp, dump_path)
        warm = run_state(tmp, dump_path)
        assert _sorted_sessions(cold) == _sorted_sessions(warm), \
            (cold["sessions"], warm["sessions"])


def test_a_removed_fixture_drops_out_of_the_memo():
    # Памятка не накапливает мусор: файл, выпавший из среза (здесь — удалён
    # совсем), не должен оставаться в facts.json вечной записью.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = build_home(tmp, [A, B])
        dump_path = os.path.join(tmp, "dump.json")
        run_state(tmp, dump_path)
        facts_path = os.path.join(tmp, "facts.json")
        with open(facts_path, encoding="utf-8") as fh:
            before = json.load(fh)
        assert any(p.endswith(A + ".jsonl") for p in before["files"]), before

        d = os.path.join(tmp, ".claude", "projects", re.sub(r"[^a-zA-Z0-9]", "-", cwd))
        os.unlink(os.path.join(d, A + ".jsonl"))
        run_state(tmp, dump_path)
        with open(facts_path, encoding="utf-8") as fh:
            after = json.load(fh)
        assert not any(p.endswith(A + ".jsonl") for p in after["files"]), after


def test_state_after_a_cold_dump_still_answers_the_first_prompt_not_the_latest_reply():
    # Сценарий B из второго круга ревью. Порядок важен: dump должен увидеть
    # сессию первым, на холодной памятке — тогда его старая запись несла
    # gist="", gistDone=False с уже настоящим mtime. Следующий --state ловил
    # её как полное попадание (mtime совпал), f["gist"] был пуст, и сборка
    # ответа (`f["gist"] or f["doing"]`) молча подставляла последний ответ
    # агента вместо первого промпта — и так на каждом следующем опросе, пока
    # у простаивающей сессии не сдвинется mtime, то есть никогда.
    with tempfile.TemporaryDirectory() as tmp:
        build_reply_session(tmp, A, "FIRST PROMPT", "LATER REPLY")
        dump_path = os.path.join(tmp, "dump.json")

        run_dump(tmp, dump_path)  # тот самый писатель, что раньше отравлял памятку

        out = run_state(tmp, dump_path)
        assert out["sessions"][0]["gist"] == "FIRST PROMPT", out["sessions"]


def test_truncation_guard_survives_a_dump_in_the_middle():
    # Сценарий D из второго круга ревью. dump раньше сам обновлял size на
    # укороченный размер, не тронув gist, — и тем самым стирал подпись
    # усечения (size меньше сохранённого) для следующего --state. Починка не
    # опирается только на size: dump-запись без ключа gist читается как
    # «не искали», и --state пересчитывает gist сам вне зависимости от того,
    # что лежит в size.
    with tempfile.TemporaryDirectory() as tmp:
        path, cwd = build_reply_session(
            tmp, A, "OLD PROMPT " * 5, "OLD REPLY " * 5, mtime=2000)
        dump_path = os.path.join(tmp, "dump.json")
        run_state(tmp, dump_path)

        # Файл под тем же путём переписан заново, короче прежнего — ровно та
        # подмена, ради которой сторож и заведён.
        _write_reply_session(path, cwd, "NEW", "NEW REPLY")
        os.utime(path, (3000, 3000))

        run_dump(tmp, dump_path)

        out = run_state(tmp, dump_path)
        assert out["sessions"][0]["gist"] == "NEW", out["sessions"]


def test_state_reports_every_window_and_names_the_first_one():
    # Сессия открыта на двух машинах. Список отдаётся целиком, а `window`
    # остаётся и равно первому: его читает пикер прошлой версии, и он обязан
    # продолжать работать.
    with tempfile.TemporaryDirectory() as tmp:
        sid = "aaaaaaaa-1111-2222-3333-444444444444"
        build_home(tmp, [sid])
        wdir = os.path.join(tmp, "windows")
        os.makedirs(wdir)
        now = int(time.time())
        for name, host, focused in (("a.json", "windows-box", 0),
                                    ("b.json", "mac-host", now - 30)):
            with open(os.path.join(wdir, name), "w", encoding="utf-8") as fh:
                json.dump({"generated": now, "host": host, "pid": 42, "windows": {
                    sid: {"title": "ccfzf", "desktop": None,
                          "lastSeen": now - 1, "focusedAt": focused}}}, fh)
        out = run_state(tmp, os.path.join(tmp, "dump.json"),
                        env_extra={"CCFZF_WINDOWS_DIR": wdir, "CCFZF_WINDOWS_FILE": ""})
        row = [s for s in out["sessions"] if s["id"] == sid][0]
        assert [w["host"] for w in row["windows"]] == ["mac-host", "windows-box"], row["windows"]
        assert row["window"] == row["windows"][0], row["window"]


def test_the_python_block_is_not_passed_as_an_argument():
    """Потолок ядра, о который уже споткнулись: MAX_ARG_STRLEN — 32 страницы,
    то есть 128 КБ на ОДИН аргумент, сколько бы места ни было под argv целиком.
    Блок дорос до 131 880 байт, `python3 -c "$PY"` перестал запускаться вовсе,
    и отказ был непроходимый и без подсказки: `Argument list too long`, код
    126, ни одного ответа --state.

    Сторож текстовый, и поведением его не заменить: на машине с другим ядром
    или страницей потолок иной, а вернуть `-c` можно одной правкой — и она
    сломала бы агрегатор ровно тогда, когда файл в следующий раз подрастёт.
    """
    with open(SRC, encoding="utf-8") as fh:
        src = fh.read()
    assert 'python3 -c "$PY"' not in src, "блок снова уходит аргументом — потолок 128 КБ вернётся"
    assert 'py() { printf ' in src, "исчезла обёртка py(), кормящая блок через stdin"


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
