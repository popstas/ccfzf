# Потоки данных сессий — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** убрать 455 мс сетевых `stat` из перечитывания индекса сессий на Windows и 280 мс пересчёта неизменных фактов из каждого вызова `ccfzf --state` на pc-virt.

**Architecture:** число, ради которого читатель ходит по сети (mtime файла хука), считается писателем локально и едет полем `activityAt` в дампе; сам дамп признаётся каналом к своим двум читателям и режется до восьми полей и `--limit` записей; неизменные факты о транскриптах (первый промпт, заголовок) запоминаются в дисковой памятке, потому что `--state` запускается новым процессом на каждый опрос.

**Tech Stack:** ccfzf — bash с python3-блоком внутри heredoc, тесты pytest поверх `tests/harness.py`. windows11-manager — ESM Node, тесты vitest.

Спека: [`docs/superpowers/specs/2026-08-10-session-data-flow-design.md`](../specs/2026-08-10-session-data-flow-design.md).

## Global Constraints

- **Язык.** Комментарии, докстринги, названия тестов и сообщения в `assert` — по-русски, они объясняют «почему». Всё, что видит человек (`usage()`, сообщения об ошибках CLI, README), — по-английски.
- **Два репозитория.** `ccfzf` — `/home/popstas/projects/shell/ccfzf` (задачи 1–7). `windows11-manager` — `/home/popstas/projects/js/windows11-manager` (задачи 8–10).
- **ccfzf правится только в файле `ccfzf`.** Python живёт heredoc-ом между `<<'PYEOF'` (строка 118) и `PYEOF` (строка 1468). Отдельного `.py` не существует, и создавать его нельзя — `tests/harness.py` вырезает блок по этим меткам.
- **Тесты ccfzf запускаются двумя способами** и должны работать обоими: `python3 -m pytest tests/ -q` и `python3 tests/test_<имя>.py` (у каждого файла свой `__main__`-раннер, см. хвост `tests/test_state_projects.py`).
- **Тесты windows11-manager:** `npm test` (vitest), из корня репозитория.
- **`--limit` по умолчанию 100.** Ровно это число, ровно это имя ключа.
- **Поля дампа — ровно эти восемь, в этом порядке:** `id, title, cwd, live, mtime, kind, parent, activityAt`.
- **`mtime` и `activityAt` — epoch-секунды.** `mtime` — float от `os.path.getmtime`, `activityAt` — int, `floor` от mtime файла хука. Читатель на JS сравнивает их между собой, разъезд единиц молча сломал бы разрешение тёзок.
- **Не ломать контракт `--state` для пикера.** Из ответа `--state` в stdout не убирается ни одно поле: `file`, `gist`, `doing`, `projects`, `frozen`, `agent`, `window` там остаются. Режется только файл дампа.
- **Коммиты частые, по задаче.** Сообщения — conventional commits, по-русски в теле.

---

### Task 1: `--limit` в CLI ccfzf

Ключ заменяет константу `DUMP_SESSIONS = 200` и управляет всем сразу — и `--state`, и `--dump`.

**Files:**
- Modify: `ccfzf` (строки 11–13 — шапка help; 21–24 и 45–47 — комментарии; 49 — `usage()`; 74–92 — разбор аргументов; 136 — константа; 1474, 1480, 1516 — вызовы python; ветки `dump` и `state`)
- Test: `tests/test_limit.py` (создать)

**Interfaces:**
- Produces: bash-переменная `limit` (строка, проверенная как целое положительное); python получает её последним argv — `state`: `sys.argv[5]`, `dump`: `sys.argv[6]`; в обеих ветках разворачивается в локальную переменную `limit` (int).

- [x] **Step 1: Написать падающий тест**

Создать `tests/test_limit.py`:

```python
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
```

- [x] **Step 2: Убедиться, что тест падает**

Run: `cd /home/popstas/projects/shell/ccfzf && python3 -m pytest tests/test_limit.py -q`
Expected: FAIL — сейчас `--limit` попадает в ветку `*)` разбора и трактуется как имя проекта, кода 2 нет.

- [x] **Step 3: Разбор ключа в bash**

В `ccfzf`, после строки `session_id=""` (строка ~79) добавить:

```bash
# Сколько новейших сессий ccfzf вообще рассматривает. Прежние 200 были
# рассчитаны на список для человека; читателю дампа столько не нужно никогда,
# а платит за них и он (разбор), и pc-virt (двести хвостов на каждый опрос).
limit=100
```

В `while (($#))`, сразу после ветки `--session=*`:

```bash
    --limit) limit="${2-}"; [[ -n $limit ]] || { echo "ccfzf: --limit requires a positive integer" >&2; exit 2; }; shift 2 ;;
    --limit=*) limit="${1#*=}"; shift ;;
```

После цикла, перед проверкой `kiosk && print_mode`:

```bash
[[ $limit =~ ^[1-9][0-9]*$ ]] || { echo "ccfzf: --limit requires a positive integer" >&2; exit 2; }
```

- [x] **Step 4: Шапка help и `usage()`**

Строку 13 (`#                               picker on another machine; no picker, no fzf`) оставить, после неё вставить:

```
#   ccfzf --limit <n>           how many newest sessions to look at at all
#                               (default 100; applies to --state and --dump)
```

`usage()` печатает `sed -n '2,30p'` — диапазон уже обрезал описание `CCFZF_WINDOWS_FILE` на полуслове, а две новые строки сдвинут всё ещё на две. Заменить на `sed -n '2,34p'`.

- [x] **Step 5: Прокинуть в python**

Строка 136: заменить

```python
DUMP_SESSIONS = 200       # newest sessions written to the sessions dump
```

на

```python
DUMP_SESSIONS = 100       # умолчание для --limit: сколько новейших сессий смотрим
```

Три вызова python дополнить аргументом (строки 1474, 1480, 1516):

```bash
python3 -c "$PY" dump "$MARKS" "$SESSIONS_FILE" "$PROJECTS_FILE" "$WINDOWS_FILE" "$limit"
```

```bash
python3 -c "$PY" state "$MARKS" "$WINDOWS_FILE" "$SESSIONS_FILE" "$limit"
```

(строка 1516 — та же форма, что 1474.)

В ветке `elif mode == "dump":` после `windows_path = sys.argv[5] if len(sys.argv) > 5 else ""` добавить:

```python
    limit = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else DUMP_SESSIONS
```

В ветке `elif mode == "state":` после `sessions_path = sys.argv[4] if len(sys.argv) > 4 else ""` добавить:

```python
    limit = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else DUMP_SESSIONS
```

В обеих ветках заменить `files[:DUMP_SESSIONS]` на `files[:limit]` (строки ~1306 и ~1382).

- [x] **Step 6: Обновить комментарии про 200**

Строки 21–24 шапки:

```
#   CCFZF_SESSIONS_FILE              json dump for the window tracker: the
#                                    newest sessions (see --limit), all projects
#                                    (default ~/.ccfzf.sessions.json, empty — off);
#                                    --dump always rewrites it, --state only when
#                                    it is older than STATE_DUMP_MAX_AGE
```

Строки 45–47:

```bash
# What ccfzf sees is also dumped as json for the window tracker on the other
# machine: every project, and the newest --limit sessions across all of them.
# Set either to an empty string to turn that dump off.
```

- [x] **Step 7: Прогнать тесты**

Run: `cd /home/popstas/projects/shell/ccfzf && python3 -m pytest tests/ -q`
Expected: PASS, включая прежние файлы тестов.

- [x] **Step 8: Коммит**

```bash
cd /home/popstas/projects/shell/ccfzf
git add ccfzf tests/test_limit.py
git commit -m "feat(cli): ключ --limit, умолчание 100

Прежние 200 сессий были рассчитаны на список для человека. Читателю дампа
столько не нужно никогда, а платят за них оба: он — разбором, pc-virt —
двумя сотнями хвостов на каждый опрос --state.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: срез `pick_files` — `--limit` ∪ живые ∪ с окном

Обрезка по времени одна отрезала бы сессию, чьё окно открыто, а транскрипт не трогали дольше среза. Объединение это чинит и, в отличие от фильтра по `live`, соврать не может — оно только добавляет.

**Files:**
- Modify: `ccfzf` (добавить `sid_of` и `pick_files` рядом с `dir_cwd`; ветки `dump` и `state`)
- Test: `tests/test_pick_files.py` (создать)

**Interfaces:**
- Consumes: `limit` из Task 1.
- Produces: `sid_of(path) -> str`; `pick_files(files, limit, keep_ids) -> list`, где `files` — `[(path, mtime, cwd)]`, отсортированный по убыванию `mtime`, `keep_ids` — `set` строк.

- [x] **Step 1: Написать падающий тест**

Создать `tests/test_pick_files.py`:

```python
"""Срез сессий для дампа. Запуск: python3 tests/test_pick_files.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"
C = "cccccccc-1111-2222-3333-444444444444"


def files(*ids):
    # mtime убывает по порядку, как их отдаёт сам ccfzf после сортировки.
    return [("/d/%s.jsonl" % sid, 1000.0 - i, "/p") for i, sid in enumerate(ids)]


def test_sid_of_strips_the_jsonl_suffix():
    assert CC["sid_of"]("/d/-p/%s.jsonl" % A) == A


def test_within_the_limit_nothing_is_added():
    got = CC["pick_files"](files(A, B), 5, {B})
    assert [f[0] for f in got] == ["/d/%s.jsonl" % A, "/d/%s.jsonl" % B], got


def test_beyond_the_limit_the_tail_is_cut():
    got = CC["pick_files"](files(A, B, C), 1, set())
    assert [CC["sid_of"](f[0]) for f in got] == [A], got


def test_a_session_worth_keeping_survives_the_cut():
    # Ради этого случая объединение и существует: окно открыто, а транскрипт
    # не трогали дольше среза. Без неё читателю дампа нечем понять, чьё окно.
    got = CC["pick_files"](files(A, B, C), 1, {C})
    assert [CC["sid_of"](f[0]) for f in got] == [A, C], got


def test_order_stays_by_falling_mtime():
    # Добавка всегда старше головы, поэтому сортировать заново незачем —
    # но если срез когда-нибудь начнут делать не по отсортированному списку,
    # порядок разъедется молча.
    got = CC["pick_files"](files(A, B, C), 2, {C})
    assert [f[1] for f in got] == [1000.0, 999.0, 998.0], got


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
```

- [x] **Step 2: Убедиться, что тест падает**

Run: `python3 -m pytest tests/test_pick_files.py -q`
Expected: FAIL — `KeyError: 'sid_of'`.

- [x] **Step 3: Реализовать**

В `ccfzf`, сразу после функции `dir_cwd` (перед `def head_gist`):

```python
def sid_of(path):
    """Id сессии по имени её транскрипта."""
    return os.path.basename(path)[:-6]


def pick_files(files, limit, keep_ids):
    """Первые `limit` по свежести плюс те, кого терять нельзя.

    `files` отсортирован по убыванию mtime, поэтому добавка всегда старше
    головы и порядок сохраняется сам — пересортировывать нечего.

    Объединение — не перестраховка. Один срез по времени отрезал бы сессию,
    чей транскрипт не трогали дольше среза, а окно её открыто до сих пор: у
    читателя дампа она единственный способ понять, чьё это окно. Фильтровать
    вместо этого по `live` нельзя — флаг уже врал (2026-08-01, работающая
    сессия с `live: false`), а объединение только добавляет и потому соврать
    не может.
    """
    head = files[:limit]
    if len(files) <= limit or not keep_ids:
        return head
    return head + [f for f in files[limit:] if sid_of(f[0]) in keep_ids]
```

- [x] **Step 4: Подключить в обеих ветках**

В ветке `state`, заменить

```python
    sessions = []
    for path, mtime, cwd in files[:limit]:
```

на

```python
    # `live` здесь уже вобрал сессии с открытым окном (`live |= set(windows)`
    # выше), так что второго множества не нужно.
    picked = pick_files(files, limit, live)

    sessions = []
    for path, mtime, cwd in picked:
```

В ветке `dump` — то же самое, там `live` тоже уже объединён с `windows`.

В записи ответа заменить `"shown": len(sessions)` оставить как есть (оно и так считает записанное), а `"total": len(files)` — как есть.

- [x] **Step 5: Прогнать тесты**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [x] **Step 6: Коммит**

```bash
git add ccfzf tests/test_pick_files.py
git commit -m "feat(dump): срез --limit объединяется с живыми и оконными

Окно, открытое на сессии, чей транскрипт не трогали дольше среза, иначе
выпало бы из дампа, и читателю нечем было бы понять, чьё это окно.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `activityAt` в записи сессии

Файлы `<id>.state.json`, ради mtime которых читатель ходит по сети, у ccfzf локальные, и он их уже обходит.

**Files:**
- Modify: `ccfzf` (ветки `dump` и `state`)
- Test: `tests/test_state_mode.py` (создать — сквозной запуск режима `state` поверх подставного `HOME`)

**Interfaces:**
- Consumes: `hook_stamps()` (ccfzf:696) — `{sid: mtime}` из `~/.claude/claude-wt`.
- Produces: поле `activityAt` (int, epoch-секунды, 0 — хук про сессию не писал) в каждой записи `sessions` и в `--state`, и в дампе.

- [x] **Step 1: Написать падающий тест**

Создать `tests/test_state_mode.py`:

```python
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


def run_state(tmp, dump_path, *extra):
    env = dict(os.environ)
    env.update({
        "HOME": tmp,
        "FZF_MARKS_FILE": os.path.join(tmp, "no-marks"),
        "CCFZF_SESSIONS_FILE": dump_path,
        "CCFZF_PROJECTS_FILE": "",
        "CCFZF_WINDOWS_FILE": "",
        "CCFZF_FACTS_FILE": os.path.join(tmp, "facts.json"),
        "XDG_CACHE_HOME": os.path.join(tmp, "cache"),
    })
    r = subprocess.run(["bash", SRC, "--state", *extra],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return json.loads(r.stdout)


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
        os.utime(state_file, (1234567890, 1234567890))
        out = run_state(tmp, os.path.join(tmp, "dump.json"))
        by_id = {s["id"]: s for s in out["sessions"]}
        assert by_id[A]["activityAt"] == 1234567890, by_id[A]
        # Хук про неё не писал — ноль, ровно то же, что сегодня возвращает
        # сетевой вызов у читателя при отсутствии файла.
        assert by_id[B]["activityAt"] == 0, by_id[B]


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
```

- [x] **Step 2: Убедиться, что тест падает**

Run: `python3 -m pytest tests/test_state_mode.py -q`
Expected: первые два теста проходят, `test_activity_at_comes_from_the_hook_file` падает с `KeyError: 'activityAt'`.

- [x] **Step 3: Реализовать**

В ветке `state`, после `live, agents, procs = running_sessions()` добавить:

```python
    # Отметки хуков — те самые, за mtime которых читатель дампа сегодня ходит
    # по сети на каждого кандидата с общим заголовком. Здесь файлы локальные и
    # обход один: scandir по каталогу, доли миллисекунды. Считать одно и то же
    # с двух сторон незачем — число уезжает полем.
    stamps = hook_stamps()
```

В ветке `dump` — после `live, agents, _ = running_sessions()` та же строка.

В обеих ветках, в собираемую запись сессии добавить (рядом с `"live"`):

```python
            "activityAt": int(stamps.get(sid, 0)),
```

- [x] **Step 4: Прогнать тесты**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [x] **Step 5: Коммит**

```bash
git add ccfzf tests/test_state_mode.py
git commit -m "feat(state): отметка хука едет полем activityAt

Читатель дампа на Windows брал её сетевым stat по каждому кандидату с общим
заголовком — 354 вызова на 200 сессий, 455 мс. Файлы у ccfzf локальные, и
hook_stamps() уже обходит их одним scandir.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: дамп — восемь полей, одна форма у обоих писателей

**Files:**
- Modify: `ccfzf` (константа и функция рядом с `write_json`; ветки `dump` и `state`)
- Test: `tests/test_dump_shape.py` (создать), `tests/test_state_mode.py` (дополнить)

**Interfaces:**
- Consumes: записи сессий из Task 3 (с `activityAt`).
- Produces: `DUMP_KEEP` (tuple из восьми имён), `dump_record(s) -> dict`.

- [x] **Step 1: Написать падающий тест**

Создать `tests/test_dump_shape.py`:

```python
"""Форма дампа для оконного трекера. Запуск: python3 tests/test_dump_shape.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

FULL = {
    "id": "a1", "cwd": "/p", "file": "/d/a1.jsonl", "projects": ["p"],
    "title": "t", "gist": "g", "doing": "d", "mtime": 100.0, "age": "1m",
    "live": True, "frozen": False, "kind": "interactive", "parent": "",
    "activityAt": 99, "pid": 7, "tty": "pts/0", "tmux": None, "agent": {},
    "window": None,
}


def test_dump_keeps_exactly_what_the_reader_uses():
    # Читателей у файла два, оба в windows11-manager/src/claude-wt/sessions.js.
    # Список сверен по ним; лишнее поле здесь — это байты, которые оба процесса
    # разбирают четырежды в минуту и выбрасывают.
    assert CC["DUMP_KEEP"] == (
        "id", "title", "cwd", "live", "mtime", "kind", "parent", "activityAt",
    ), CC["DUMP_KEEP"]


def test_dump_record_drops_everything_else():
    got = CC["dump_record"](FULL)
    assert set(got) == set(CC["DUMP_KEEP"]), got
    assert got["id"] == "a1" and got["activityAt"] == 99, got


def test_dump_record_shouts_when_a_field_is_missing():
    # Проекция — единственное место, где сходятся два писателя одного файла.
    # Молча отдать читателю запись без title значило бы стереть ему индекс.
    try:
        CC["dump_record"]({"id": "a1"})
    except KeyError:
        return
    raise AssertionError("ожидался KeyError на неполной записи")


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
```

Дописать в `tests/test_state_mode.py` (перед блоком `if __name__`):

```python
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
```

- [x] **Step 2: Убедиться, что тесты падают**

Run: `python3 -m pytest tests/test_dump_shape.py tests/test_state_mode.py -q`
Expected: FAIL — `KeyError: 'DUMP_KEEP'`, и дамп пока несёт тринадцать полей.

- [x] **Step 3: Реализовать проекцию**

В `ccfzf`, сразу перед `def write_json`:

```python
# Что уезжает в дамп. Читателей у файла два, оба в
# windows11-manager/src/claude-wt/sessions.js (loadSessionIndex,
# loadBackgroundAgents), и это ровно те поля, которые они читают. Остальное —
# gist, doing, file, projects, age, frozen — не читает никто: пикер сюда не
# ходит вовсе, он берёт --state по ssh. Комментарий над режимом dump обещал
# «for whatever else wants to know it»; желающих не нашлось, а платят за
# обещание оба читателя, разбирая и выбрасывая эти байты четырежды в минуту.
DUMP_KEEP = ("id", "title", "cwd", "live", "mtime", "kind", "parent", "activityAt")


def dump_record(s):
    """Запись сессии для дампа.

    Единственное место, где сходятся два писателя одного файла: режимы `dump`
    и `state` пишут его оба, и до этой проекции содержимое зависело от того,
    кто записал последним. Отсутствующее поле роняет KeyError намеренно —
    молча отданный читателю индекс без title стирается целиком.
    """
    return {k: s[k] for k in DUMP_KEEP}
```

- [x] **Step 4: Подключить в ветке `state`**

Заменить блок записи дампа:

```python
    if stale_dump(sessions_path, now, STATE_DUMP_MAX_AGE):
        keep = ("id", "cwd", "file", "projects", "title", "gist", "doing",
                "mtime", "age", "live", "frozen", "kind", "parent")
        write_json(sessions_path, {
            "generated": now, "total": len(files), "shown": len(sessions),
            "sessions": [{k: s[k] for k in keep} for s in sessions],
        })
```

на:

```python
    if stale_dump(sessions_path, now, STATE_DUMP_MAX_AGE):
        write_json(sessions_path, {
            "generated": now, "total": len(files), "shown": len(sessions),
            "sessions": [dump_record(s) for s in sessions],
        })
```

- [x] **Step 5: Подключить в ветке `dump`**

Запись сессии там собирается своя, богаче нужного. Заменить тело цикла на:

```python
        sessions = []
        for path, mtime, cwd in picked:
            sid = sid_of(path)
            title, _doing = tail_facts(path)
            agent = agents.get(sid) or {}
            # head_gist здесь больше не зовётся: `gist` в дамп не уезжает, а
            # стоил он 165 мс из 320 на двухстах сессиях.
            sessions.append(dump_record({
                "id": sid, "cwd": cwd, "title": clean(title),
                "mtime": mtime, "live": sid in live,
                "kind": agent.get("kind", "interactive"),
                "parent": agent.get("parent", ""),
                "activityAt": int(stamps.get(sid, 0)),
            }))
```

Переменные `frozen` и `gist` в ветке `dump` становятся ненужными — убрать строку `frozen = frozen_ids()` и всё, что её использует, если больше ничего не осталось.

- [x] **Step 6: Прогнать тесты**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [x] **Step 7: Убедиться руками, что дамп похудел**

Run:
```bash
cd /home/popstas/projects/shell/ccfzf && ./ccfzf --dump && ls -la ~/.ccfzf.sessions.json
```
Expected: было ~184 КБ, стало ~25 КБ.

- [x] **Step 8: Коммит**

```bash
git add ccfzf tests/test_dump_shape.py tests/test_state_mode.py
git commit -m "feat(dump): восемь полей вместо тринадцати, одна форма у обоих писателей

Читателей у файла два, оба смотрят в семь полей. Пикер сюда не ходит вовсе —
он берёт --state по ssh, и его ответ не тронут. 184 КБ -> ~25 КБ.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: памятка фактов о транскриптах

280 из 320 мс каждого `--state` — пересчёт того, что не менялось. Процесс на каждый опрос новый, поэтому памятка на диске.

**Files:**
- Modify: `ccfzf` (константы рядом со `STATUS_DIR`; функции рядом с `write_json`; ветки `dump` и `state`)
- Test: `tests/test_facts_cache.py` (создать)

**Interfaces:**
- Consumes: `tail_facts(path) -> (title, doing)`, `head_gist(path) -> str`, `clean(s) -> str`, `HEAD_LIMIT`, `write_json`.
- Produces: `FACTS_FILE` (str), `FACTS_VERSION` (int), `load_facts(path) -> dict`, `save_facts(path, facts) -> None`, `facts_for(path, mtime, cache, tail=None, head=None, size_of=os.path.getsize) -> dict` с ключами `mtime, title, doing, gist, gistDone`.

- [x] **Step 1: Написать падающий тест**

Создать `tests/test_facts_cache.py`:

```python
"""Памятка фактов о транскриптах. Запуск: python3 tests/test_facts_cache.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

P = "/d/a1.jsonl"


def counting(title="T", doing="D", gist="G"):
    calls = {"tail": 0, "head": 0}

    def tail(path):
        calls["tail"] += 1
        return title, doing

    def head(path):
        calls["head"] += 1
        return gist

    return calls, tail, head


def test_a_hit_recomputes_nothing():
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "T", "doing": "D",
                 "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 100.0, cache, tail=tail, head=head)
    assert got == cache[P], got
    assert calls == {"tail": 0, "head": 0}, calls


def test_a_changed_file_recomputes_the_tail():
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "old", "doing": "old",
                 "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 200.0, cache, tail=tail, head=head)
    assert got["title"] == "T" and got["doing"] == "D", got
    assert calls["tail"] == 1, calls


def test_a_known_gist_survives_any_change_to_the_file():
    # Первый промпт сессии неизменен — ключевать его по mtime незачем. Это
    # 165 мс из 320 на двухстах сессиях, и уходят они даже у тех сессий,
    # которые пишутся прямо сейчас.
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "old", "doing": "old",
                 "gist": "первый промпт", "gistDone": True}}
    got = CC["facts_for"](P, 999.0, cache, tail=tail, head=head)
    assert got["gist"] == "первый промпт", got
    assert calls["head"] == 0, calls


def test_an_empty_gist_is_retried_while_the_file_is_small():
    calls, tail, head = counting(gist="")
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head,
                          size_of=lambda p: 10)
    assert calls["head"] == 1, calls
    assert got["gist"] == "" and got["gistDone"] is False, got


def test_an_empty_gist_stops_being_retried_past_the_head_limit():
    # head_gist дальше HEAD_LIMIT и не смотрит, значит ответ измениться уже
    # не может — спрашивать бессмысленно до конца жизни файла.
    calls, tail, head = counting(gist="")
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head,
                          size_of=lambda p: CC["HEAD_LIMIT"] + 1)
    assert got["gistDone"] is True, got
    calls2, tail2, head2 = counting(gist="")
    again = CC["facts_for"](P, 200.0, {P: got}, tail=tail2, head=head2,
                            size_of=lambda p: CC["HEAD_LIMIT"] + 1)
    assert calls2["head"] == 0, calls2
    assert again["gistDone"] is True, again


def test_the_title_is_stored_cleaned():
    calls, tail, head = counting(title="  t\tt  ")
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head)
    assert got["title"] == CC["clean"]("  t\tt  "), got


def test_a_broken_memo_reads_as_empty():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "facts.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{ не json")
        assert CC["load_facts"](p) == {}, "рваный файл"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"v": 999, "files": {P: {"mtime": 1}}}, fh)
        assert CC["load_facts"](p) == {}, "чужая версия"
        assert CC["load_facts"]("") == {}, "выключенная памятка"
        assert CC["load_facts"](os.path.join(tmp, "нет.json")) == {}, "нет файла"


def test_save_then_load_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "sub", "facts.json")
        facts = {P: {"mtime": 100.0, "title": "T", "doing": "D",
                     "gist": "G", "gistDone": True}}
        CC["save_facts"](p, facts)
        assert CC["load_facts"](p) == facts, CC["load_facts"](p)


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
```

- [x] **Step 2: Убедиться, что тест падает**

Run: `python3 -m pytest tests/test_facts_cache.py -q`
Expected: FAIL — `KeyError: 'facts_for'`.

- [x] **Step 3: Константы**

В `ccfzf`, после `HOOK_LIVE_TTL` (строка ~160) добавить:

```python
# Памятка фактов о транскриптах. Нужна оттого, что `--state` запускается новым
# процессом на каждый опрос пикера — раз в секунду, через ssh, — и кэшу в
# памяти взяться неоткуда. Из 320 мс вызова 280 уходили на пересчёт того, что
# не менялось: 165 мс head_gist и 117 мс tail_facts на двухстах сессиях.
#
# Ключ — mtime файла. Про врущий mtime здесь говорить нечего: каталог
# локальный, ext4; тот шрам — про чтение V: с Windows, где атрибуты отдаёт
# кэш SMB долгоживущему процессу. Пустая строка выключает памятку.
FACTS_VERSION = 1
FACTS_FILE = os.environ.get("CCFZF_FACTS_FILE")
if FACTS_FILE is None:
    FACTS_FILE = os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
        "ccfzf", "facts.json")
```

- [x] **Step 4: Дать `write_json` необязательный отступ**

Памятка — файл для машины, и отступ в ней только байты. Идёт первым: `save_facts` ниже зовёт `write_json` уже с этим параметром. Заменить сигнатуру и вызов:

```python
def write_json(path, obj, indent=1):
```

```python
            json.dump(obj, fh, ensure_ascii=False, indent=indent)
```

- [x] **Step 5: Функции**

Сразу после `dump_record` добавить:

```python
def load_facts(path):
    """Памятка с диска, или пустая — по любой причине.

    Пустая всегда безопасна: памятка — чистая функция от содержимого файлов,
    и промах стоит ровно того, что стоил вызов до её появления.
    """
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            o = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(o, dict) or o.get("v") != FACTS_VERSION:
        return {}
    files = o.get("files")
    return files if isinstance(files, dict) else {}


def save_facts(path, facts):
    """Записать памятку. Гонку двух ccfzf решает последний писатель, и это
    верно: у двух памяток об одних и тех же файлах расходиться нечему."""
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        return
    write_json(path, {"v": FACTS_VERSION, "files": facts}, indent=None)


def facts_for(path, mtime, cache, tail=None, head=None, size_of=os.path.getsize):
    """Заголовок, последняя реплика и первый промпт — считаются при промахе.

    `gist` живёт по своему правилу: первый промпт сессии неизменен, и
    найденный непустой переносится через любые изменения файла — head_gist для
    неё больше не зовётся никогда. Пустой пересчитывается, пока файл не
    перерос HEAD_LIMIT: дальше head_gist и сам не смотрит, ответ измениться
    уже не может, и тогда ставится gistDone.

    Заголовок кладётся уже причёсанным (`clean`): его так читают оба режима, а
    сам `clean` — регулярка, и на двухстах сессиях считается заметно.
    """
    tail = tail or tail_facts
    head = head or head_gist
    old = cache.get(path) or {}
    if old.get("mtime") == mtime:
        return old
    title, doing = tail(path)
    gist = old.get("gist") or ""
    done = bool(gist) or bool(old.get("gistDone"))
    if not done:
        gist = head(path)
        if gist:
            done = True
        else:
            try:
                done = size_of(path) > HEAD_LIMIT
            except OSError:
                done = False
    return {"mtime": mtime, "title": clean(title), "doing": doing,
            "gist": gist, "gistDone": done}
```

- [x] **Step 6: Подключить в ветке `state`**

Заменить цикл сборки сессий:

```python
    cache = load_facts(FACTS_FILE)
    facts = {}
    sessions = []
    for path, mtime, cwd in picked:
        sid = sid_of(path)
        f = facts_for(path, mtime, cache)
        facts[path] = f
        agent = agents.get(sid) or {}
        sessions.append({
            "id": sid, "cwd": cwd, "file": path,
            "projects": sorted(owners_of(cwd, marks)),
            "title": f["title"], "gist": (f["gist"] or f["doing"])[:200],
            "doing": f["doing"],
            "mtime": mtime, "age": ago(mtime, now),
            "live": sid in live, "frozen": sid in frozen,
            "activityAt": int(stamps.get(sid, 0)),
            "kind": agent.get("kind", "interactive"),
            "parent": agent.get("parent", ""),
            "pid": (procs.get(sid) or {}).get("pid", 0),
            "tty": (procs.get(sid) or {}).get("tty", ""),
            "tmux": (procs.get(sid) or {}).get("tmux"),
            "agent": agent_of(sid),
            # Отсутствует, а не null: «окна нет» и «про окна ничего не
            # известно» у читателя рисуются одинаково, и заводить между ними
            # разницу некому — она не видна ни в одной строке списка.
            "window": windows.get(sid),
        })

    # Записи файлов, выпавших из среза, в памятку не попали — чистка выходит
    # сама. Пишем только при отличии: иначе каждый опрос пикера стоил бы
    # записи всей памятки на диск.
    if facts != cache:
        save_facts(FACTS_FILE, facts)
```

- [x] **Step 7: Подключить в ветке `dump`**

Тот же приём, но без `gist`: в дамп он не уезжает.

```python
        cache = load_facts(FACTS_FILE)
        facts = {}
        sessions = []
        for path, mtime, cwd in picked:
            sid = sid_of(path)
            f = facts_for(path, mtime, cache)
            facts[path] = f
            agent = agents.get(sid) or {}
            sessions.append(dump_record({
                "id": sid, "cwd": cwd, "title": f["title"],
                "mtime": mtime, "live": sid in live,
                "kind": agent.get("kind", "interactive"),
                "parent": agent.get("parent", ""),
                "activityAt": int(stamps.get(sid, 0)),
            }))
        if facts != cache:
            save_facts(FACTS_FILE, facts)
```

- [x] **Step 8: Прогнать тесты**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [x] **Step 9: Померить**

Run:
```bash
rm -f ~/.cache/ccfzf/facts.json
cd /home/popstas/projects/shell/ccfzf
time ./ccfzf --state > /dev/null   # холодная памятка
time ./ccfzf --state > /dev/null   # тёплая
```
Expected: первый прогон — как раньше (~0.3 с), второй — заметно быстрее (~0.05 с). Если второй не быстрее — памятка не пишется или ключ не совпадает; смотреть `~/.cache/ccfzf/facts.json`.

- [x] **Step 10: Коммит**

```bash
git add ccfzf tests/test_facts_cache.py
git commit -m "perf(state): дисковая памятка фактов о транскриптах

--state запускается новым процессом на каждый опрос, кэшу в памяти взяться
неоткуда. 280 из 320 мс уходило на пересчёт неизменного; главная часть —
первый промпт сессии, который не меняется никогда.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: документация ccfzf

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: поведение из задач 1–5.

- [x] **Step 1: Ключ в блоке использования**

В блок с перечнем режимов (README.md:82-88), после строки `ccfzf --session <id>        go straight into a session by id, no picker`, добавить:

```
ccfzf --limit <n>           how many newest sessions to look at at all (100)
```

- [x] **Step 2: Таблица переменных**

Строку 130 заменить и добавить следующую за ней:

```
| `CCFZF_SESSIONS_FILE` | `~/.ccfzf.sessions.json` | dump for a window tracker on another machine, `--limit` newest sessions; empty turns it off |
| `CCFZF_FACTS_FILE` | `$XDG_CACHE_HOME/ccfzf/facts.json` | memo of per-transcript facts, so a fresh `--state` process does not recompute them; empty turns it off |
```

- [x] **Step 3: Раздел «The dumps»**

Абзац README.md:143 заменить на:

```markdown
`CCFZF_SESSIONS_FILE` — the newest sessions across **all** projects (`--limit`, 100 by default), newest first, plus every live session and every session with a window open, so the file always holds whoever a window on screen might belong to. The reader is a window tracker on another machine, and the fields are the ones it needs — nothing else:
```

Пример JSON (README.md:145-167) заменить на:

```json
{
 "generated": 1785460168.138,
 "total": 860,
 "shown": 104,
 "sessions": [
  {
   "id": "c5bf2507-7381-4aa9-979d-b66242f39d7f",
   "title": "Add a session picker",
   "cwd": "/home/you/projects/js/webapp",
   "live": true,
   "mtime": 1785460166.26,
   "kind": "interactive",
   "parent": "",
   "activityAt": 1785460166
  }
 ]
}
```

Абзац README.md:168 заменить на:

```markdown
`total` is how many sessions exist, `shown` how many made it into the file. `activityAt` is when this session's hook last wrote, in epoch seconds, or 0 if it never did — the reader ranks same-titled candidates by it, and computing it here saves it a network `stat` per candidate. `kind` is `interactive` or `background`, and `parent` names the session a background agent was forked from.

`ccfzf --state` is the other output and a richer one: it prints everything above plus `file`, `projects`, `gist`, `doing`, `age`, `frozen`, `pid`, `tty`, `tmux`, `agent` and `window` on stdout, for a picker on another machine. The dump is not a subset by accident — the two have different readers.
```

- [x] **Step 4: Коммит**

```bash
git add README.md
git commit -m "docs: --limit, форма дампа и памятка фактов в README

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: перепроверить контракт живьём

Дамп меняет форму, а читатель на Windows ещё старый. Убедиться, что он это переживает, **до** правок в нём.

**Files:** нет правок, только проверка.

- [x] **Step 1: Собрать свежий дамп и сверить поля**

Run:
```bash
cd /home/popstas/projects/shell/ccfzf && ./ccfzf --dump
python3 -c "
import json
d=json.load(open('/home/popstas/.ccfzf.sessions.json'))
s=d['sessions']
print('shown',d['shown'],'total',d['total'])
print('поля:',sorted(s[0]))
need={'id','title','cwd','live','mtime','kind','parent'}
assert all(need <= set(x) for x in s), 'старому читателю не хватит полей'
print('живых:',sum(1 for x in s if x['live']))
print('размер полей ок')
"
```
Expected: восемь полей, `shown` около 100 (плюс добавка объединения), все семь полей, которые читает сегодняшний `sessions.js`, на месте.

- [x] **Step 2: Записать результат**

Если `shown` заметно больше 100 — значит объединение тянет много живых/оконных; это нормально, но стоит посмотреть, не протух ли файл трекера.

---

### Task 8: читатель предпочитает `s.activityAt`

**Files:**
- Modify: `/home/popstas/projects/js/windows11-manager/src/claude-wt/sessions-helpers.js:16-21,42-75`
- Test: `/home/popstas/projects/js/windows11-manager/src/claude-wt/sessions-helpers.test.js`

**Interfaces:**
- Consumes: поле `activityAt` (число, epoch-секунды) в записях дампа.
- Produces: `stampOf(session, probe) -> number`; `byActivityThen(probe)` теперь берёт отметку из сессии, когда та её несёт; сигнатура `indexSessions(dump, activityAt)` не меняется.

- [ ] **Step 1: Написать падающий тест**

Дописать в `src/claude-wt/sessions-helpers.test.js`, внутрь `describe('indexSessions', ...)`:

```js
  it('берёт отметку активности из дампа и не ходит по сети', () => {
    const probe = vi.fn(() => 0);
    const index = indexSessions({ sessions: [
      { id: 'stale', title: 'ccfzf', cwd: '/p', mtime: 900, live: true, activityAt: 100 },
      { id: 'fresh', title: 'ccfzf', cwd: '/p', mtime: 100, live: false, activityAt: 900 },
    ] }, probe);
    expect(index.ccfzf.id).toBe('fresh');
    expect(probe).not.toHaveBeenCalled();
  });

  it('ранжирует по отметке из дампа и без сетевой функции вовсе', () => {
    // Читатель может быть позван без progressDir — раньше это значило
    // «сравнивать только по live и mtime», и работающая сессия с live: false
    // проигрывала мёртвой тёзке. Поле в дампе снимает и этот случай.
    const index = indexSessions({ sessions: [
      { id: 'stale', title: 'ccfzf', cwd: '/p', mtime: 900, live: true, activityAt: 100 },
      { id: 'fresh', title: 'ccfzf', cwd: '/p', mtime: 100, live: false, activityAt: 900 },
    ] });
    expect(index.ccfzf.id).toBe('fresh');
  });

  it('считает отсутствующую отметку нулём, а не поводом идти в сеть', () => {
    // Смешанный дамп бывает между поколениями писателя. Ноль — то же, что
    // возвращает сетевой вызов, когда файла хука нет.
    const probe = vi.fn(() => 5000);
    const index = indexSessions({ sessions: [
      { id: 'has', title: 'ccfzf', cwd: '/p', mtime: 100, live: false, activityAt: 900 },
      { id: 'none', title: 'ccfzf', cwd: '/p', mtime: 900, live: true },
    ] }, probe);
    expect(index.ccfzf.id).toBe('has');
    expect(probe).not.toHaveBeenCalled();
  });
```

В шапке файла заменить импорт на `import { describe, it, expect, vi } from 'vitest';`.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd /home/popstas/projects/js/windows11-manager && npx vitest run src/claude-wt/sessions-helpers.test.js`
Expected: FAIL — сейчас `activityAt` из записи не читается, побеждает `stale`.

- [ ] **Step 3: Реализовать**

В `src/claude-wt/sessions-helpers.js` заменить `byActivityThen` на:

```js
/**
 * Отметка активности сессии: своя, из дампа, либо добытая у читателя.
 *
 * Поле `activityAt` кладёт ccfzf: файлы `<id>.state.json` у него локальные, а
 * здесь они на сетевом диске, и мерить одно и то же с двух сторон незачем —
 * 354 сетевых stat на 200 сессий, 455 мс на перечитывание индекса. Ноль
 * значит «хук про эту сессию не писал», ровно то же, что возвращает сетевой
 * вызов при отсутствии файла.
 */
function stampOf(s, probe) {
  if (Number.isFinite(s?.activityAt)) return s.activityAt;
  return probe ? (probe(s?.id) ?? 0) : 0;
}

/**
 * Сравнение с учётом того, что говорят хуки самих агентов.
 *
 * Флаг `live` в дампе ccfzf бывает неверен: замерено 2026-08-01, когда две
 * сессии делили заголовок `shared` — работала та, у которой стояло
 * `live=false`, а `live=true` висело на старой. Хук же срабатывает на каждый
 * вызов инструмента реально работающего агента, поэтому свежая отметка от
 * него — довод сильнее любого флага в дампе.
 *
 * Если хук не установлен, обе отметки нулевые и всё сводится к прежнему
 * правилу.
 */
function byActivityThen(probe) {
  return (a, b) => {
    const diff = stampOf(b, probe) - stampOf(a, probe);
    return diff !== 0 ? diff : compareSessions(a, b);
  };
}
```

В `indexSessions` заменить выбор компаратора:

```js
    // Спрашивать про активность есть смысл только когда кандидатов больше
    // одного: у единственного всё равно нет соперника. Отметка из дампа
    // бесплатна, поэтому её достаточно и без сетевой функции.
    const hasStamps = list.some(s => Number.isFinite(s?.activityAt));
    const compare = list.length > 1 && (hasStamps || activityAt)
      ? byActivityThen(hasStamps ? null : activityAt)
      : compareSessions;
```

Добавить `stampOf` в экспорт: `export { compareSessions, byActivityThen, stampOf, indexSessions, indexBackgroundAgents };`

- [ ] **Step 4: Прогнать тесты**

Run: `npm test`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
cd /home/popstas/projects/js/windows11-manager
git add src/claude-wt/sessions-helpers.js src/claude-wt/sessions-helpers.test.js
git commit -m "perf(claude-wt): отметка активности берётся из дампа

354 сетевых stat на сборку индекса (455 мс) были платой за число, которое
ccfzf считает у себя локально и теперь кладёт полем activityAt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: fallback — памятка на сборку и предфильтр по `mtime`

Дамп без поля бывает: старый ccfzf, откат, окно рассинхрона между двумя деплоями. Сетевой путь остаётся, но перестаёт быть штормом.

**Files:**
- Modify: `/home/popstas/projects/js/windows11-manager/src/claude-wt/sessions-helpers.js`
- Test: `/home/popstas/projects/js/windows11-manager/src/claude-wt/sessions-helpers.test.js`

**Interfaces:**
- Consumes: `stampOf`, `compareSessions`, `byActivityThen` из Task 8.
- Produces: `HOOK_SKEW_SEC` (число, 300); `comparatorFor(list, activityAt) -> (a, b) => number`.

- [ ] **Step 1: Написать падающий тест**

Дописать в `sessions-helpers.test.js` новый блок:

```js
describe('indexSessions без activityAt в дампе', () => {
  const twin = (id, mtime, over = {}) => ({
    id, title: 'ExpertizeMe', cwd: '/p', mtime, live: false, ...over,
  });

  it('спрашивает про каждый id не больше одного раза', () => {
    // Сортировка зовёт компаратор многократно, и раньше каждый его вызов был
    // сетевым stat: 354 обращения на 200 сессий.
    const probe = vi.fn(() => 0);
    indexSessions({ sessions: [twin('a', 100), twin('b', 100), twin('c', 100)] }, probe);
    expect(new Set(probe.mock.calls.map(c => c[0])).size).toBe(probe.mock.calls.length);
  });

  it('не спрашивает про кандидата, отставшего по mtime', () => {
    // Транскрипт пишет только работающая сессия, а хук стучит на тот же вызов
    // инструмента. Отставший на неделю отстал и по хуку — сеть тут трата.
    const probe = vi.fn(() => 0);
    indexSessions({ sessions: [twin('now', 1_000_000), twin('week', 1_000_000 - 7 * 86400)] }, probe);
    expect(probe.mock.calls.map(c => c[0])).not.toContain('week');
  });

  it('не идёт в сеть, когда после отсева остался один кандидат', () => {
    const probe = vi.fn(() => 0);
    const index = indexSessions({ sessions: [twin('now', 1_000_000), twin('old', 1)] }, probe);
    expect(probe).not.toHaveBeenCalled();
    expect(index.ExpertizeMe.id).toBe('now');
  });

  it('спрашивает про соседей в пределах запаса и слушает ответ', () => {
    const probe = vi.fn(id => (id === 'quiet' ? 9000 : 1));
    const index = indexSessions({ sessions: [
      twin('loud', 1_000_000),
      twin('quiet', 1_000_000 - 60),
    ] }, probe);
    expect(probe).toHaveBeenCalled();
    expect(index.ExpertizeMe.id).toBe('quiet');
  });
});
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `npx vitest run src/claude-wt/sessions-helpers.test.js`
Expected: FAIL на трёх из четырёх — сейчас статится каждый кандидат и по нескольку раз.

- [ ] **Step 3: Реализовать**

В `sessions-helpers.js`, перед `indexSessions`:

```js
/**
 * Насколько кандидат может отстать по `mtime` и всё ещё иметь шанс выиграть
 * по отметке хука.
 *
 * Транскрипт пишет только работающая сессия, а хук стучит на тот же вызов
 * инструмента: отметки расходятся меньше чем на секунду (замерено 2026-08-06,
 * докстринг `hook_stamps` в ccfzf: 0.3 с и 0.7 с). Значит кандидат, отставший
 * от самого свежего в группе больше чем на этот запас, отстал и по хуку, и
 * сетевой stat про него — чистая трата. Сам запас — на длинный вызов, внутри
 * которого хук уже отметился, а транскрипт ещё нет.
 *
 * Опорой берётся самый свежий `mtime` в группе, а не «сейчас»: обе величины
 * из одного дампа, часы двух машин сравнивать не приходится вовсе.
 */
const HOOK_SKEW_SEC = 5 * 60;

/**
 * Компаратор для группы тёзок.
 *
 * Отметка из дампа бесплатна — тогда сравниваем по ней и всё. Её нет —
 * остаётся сетевой путь, и у него два сторожа: спрашиваем только тех, кто
 * ещё может выиграть, и каждого не больше одного раза. Сортировка зовёт
 * компаратор многократно, и без памятки один и тот же id статился по
 * нескольку раз за одну сборку.
 */
function comparatorFor(list, activityAt) {
  if (list.length < 2) return compareSessions;
  if (list.some(s => Number.isFinite(s?.activityAt))) return byActivityThen(null);
  if (!activityAt) return compareSessions;

  const best = Math.max(...list.map(s => s?.mtime ?? 0));
  const asked = new Set(
    list.filter(s => (s?.mtime ?? 0) >= best - HOOK_SKEW_SEC).map(s => s?.id),
  );
  // Один кандидат после отсева — спорить не с кем, сеть не трогаем совсем.
  if (asked.size < 2) return compareSessions;

  const memo = new Map();
  return byActivityThen(id => {
    if (!asked.has(id)) return 0;
    if (!memo.has(id)) memo.set(id, activityAt(id) ?? 0);
    return memo.get(id);
  });
}
```

В `indexSessions` заменить блок выбора компаратора (введённый в Task 8) на:

```js
    const compare = comparatorFor(list, activityAt);
```

Дополнить экспорт: `export { compareSessions, byActivityThen, stampOf, comparatorFor, HOOK_SKEW_SEC, indexSessions, indexBackgroundAgents };`

- [ ] **Step 4: Прогнать тесты**

Run: `npm test`
Expected: PASS, включая тесты Task 8 и прежние.

- [ ] **Step 5: Коммит**

```bash
git add src/claude-wt/sessions-helpers.js src/claude-wt/sessions-helpers.test.js
git commit -m "perf(claude-wt): у сетевого пути два сторожа

Дамп без activityAt бывает — старый ccfzf или откат. Тогда спрашиваем только
тех, кто ещё может выиграть (предфильтр по mtime), и каждого не больше одного
раза за сборку. 354 обращения -> 0-8.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: `progressStamp` только тогда, когда он нужен

Посекундный сетевой stat каталога на `V:` стоит в ключе кэша ровно потому, что индекс зависел от отметок хуков помимо дампа. Дамп с полем эту зависимость снял.

**Files:**
- Modify: `/home/popstas/projects/js/windows11-manager/src/claude-wt/sessions.js:84-119`
- Test: `/home/popstas/projects/js/windows11-manager/src/claude-wt/sessions.test.js`

**Interfaces:**
- Consumes: дамп с полем `activityAt` (Task 3), `progressStamp(dir)` из `progress.js`.
- Produces: поле `usesHookStamps` (boolean) в записи кэша `loadDump`.

- [ ] **Step 1: Написать падающий тест**

Мокается модуль целиком — приём принятый в репозитории (`src/mqtt/service.test.js:5-6`): `vi.hoisted` для счётчика, `vi.mock` с `importOriginal`, чтобы `activityAt` рядом остался настоящим. `vi.spyOn` на ESM-экспорт здесь не годится: `sessions.js` держит ссылку на функцию с момента импорта.

Мок действует на весь файл, и это безопасно: остальные тесты зовут `loadSessionIndex(p)` без каталога состояний, а настоящий `progressStamp('')` и так возвращает 0.

В шапку `sessions.test.js`, сразу после импортов, добавить:

```js
const progressStamp = vi.hoisted(() => vi.fn(() => 0));
vi.mock('./progress.js', async (importOriginal) => ({
  ...await importOriginal(),
  progressStamp,
}));
```

и в конец файла:

```js
describe('loadSessionIndex и отметка каталога состояний', () => {
  const withStamps = () => ({
    sessions: [{ id: 's0', title: 'ccfzf', cwd: '/p0', live: true, mtime: 100, activityAt: 50 }],
  });
  const withoutStamps = () => ({
    sessions: [{ id: 's0', title: 'ccfzf', cwd: '/p0', live: true, mtime: 100 }],
  });

  it('перестаёт статить каталог состояний, когда дамп несёт activityAt', () => {
    // progressStamp — сетевой stat на V: в каждом тике демона, то есть раз в
    // секунду. Он там только ради зависимости, которой больше нет.
    const p = freshPath();
    writeDump(p, withStamps(), T0);
    loadSessionIndex(p, '/progress');            // первое чтение: ещё не знаем
    progressStamp.mockClear();
    writeDump(p, withStamps(), T1);
    loadSessionIndex(p, '/progress');
    expect(progressStamp).not.toHaveBeenCalled();
  });

  it('продолжает статить каталог, когда дамп поля не несёт', () => {
    const p = freshPath();
    writeDump(p, withoutStamps(), T0);
    loadSessionIndex(p, '/progress');
    progressStamp.mockClear();
    writeDump(p, withoutStamps(), T1);
    loadSessionIndex(p, '/progress');
    expect(progressStamp).toHaveBeenCalled();
  });
});
```

Импорт vitest в шапке файла дополнить: `import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';` (`vi` там уже есть).

- [ ] **Step 2: Убедиться, что тест падает**

Run: `npx vitest run src/claude-wt/sessions.test.js`
Expected: FAIL — первый тест, `progressStamp` зовётся всегда.

- [ ] **Step 3: Реализовать**

В `sessions.js` заменить инициализацию кэша:

```js
let cache = { path: '', mtimeMs: 0, stamp: 0, readAt: 0, index: {}, agents: {}, usesHookStamps: true };
```

Добавить перед `loadDump`:

```js
/**
 * Нужны ли этому дампу отметки хуков со стороны читателя.
 *
 * Не нужны, когда `activityAt` есть у каждой сессии: ранжировать тёзок тогда
 * нечем, кроме самого дампа, и `progressStamp` в ключе кэша — сетевой stat
 * каталога на V: в каждом тике демона — становится платой ни за что.
 * Пустой список сессий ничего не доказывает, поэтому считается «нужны».
 */
function dumpNeedsHookStamps(dump) {
  const sessions = Array.isArray(dump?.sessions) ? dump.sessions : [];
  return sessions.length === 0 || !sessions.every(s => Number.isFinite(s?.activityAt));
}
```

В `loadDump` заменить вычисление `stamp`:

```js
  // Пока не известно, какой дамп придёт, — спрашиваем. Первое чтение после
  // старта процесса платит один stat, дальше ноль.
  const needStamp = cache.path !== filePath || cache.usesHookStamps !== false;
  const stamp = needStamp ? progressStamp(progressDir) : 0;
```

В успешной ветке записи кэша:

```js
    const dump = readDump(filePath);
    const index = indexSessions(
      dump,
      progressDir ? id => activityAt(progressDir, id) : undefined,
    );
    cache = {
      path: filePath, mtimeMs: stat.mtimeMs, stamp, readAt: nowMs,
      index, agents: indexBackgroundAgents(dump),
      usesHookStamps: dumpNeedsHookStamps(dump),
    };
```

В ветке ошибки — `usesHookStamps: true` (неизвестно — спрашиваем дальше):

```js
    cache = {
      path: filePath, mtimeMs: stat.mtimeMs, stamp, readAt: nowMs,
      index: {}, agents: {}, usesHookStamps: true,
    };
```

В `invalidateSessionIndex` — то же поле:

```js
  cache = { path: '', mtimeMs: 0, stamp: 0, readAt: 0, index: {}, agents: {}, usesHookStamps: true };
```

- [ ] **Step 4: Прогнать тесты**

Run: `npm test`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/claude-wt/sessions.js src/claude-wt/sessions.test.js
git commit -m "perf(claude-wt): progressStamp только для дампов без activityAt

Он стоял в ключе кэша ради зависимости индекса от отметок хуков. Дамп с полем
её снял, а stat каталога на V: шёл в каждом тике демона — раз в секунду.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: замерить и выкатить

**Files:** нет правок.

- [ ] **Step 1: Замер на pc-virt**

Run:
```bash
cd /home/popstas/projects/shell/ccfzf
rm -f ~/.cache/ccfzf/facts.json
time ./ccfzf --state > /dev/null
time ./ccfzf --state > /dev/null
ls -la ~/.ccfzf.sessions.json ~/.cache/ccfzf/facts.json
```
Expected: тёплый прогон ~0.05 с (было 0.32), дамп ~25 КБ (было 184).

- [ ] **Step 2: Прогнать оба набора тестов**

Run:
```bash
cd /home/popstas/projects/shell/ccfzf && python3 -m pytest tests/ -q
cd /home/popstas/projects/js/windows11-manager && npm test
```
Expected: обе зелёные. Без этого дальше не идти.

- [ ] **Step 3: Деплой node-части на Windows**

Правки только в `src/` у `windows11-manager`, значит подходит быстрый путь.

Run: `cd /home/popstas/projects/js/windows-mqtt && npm run deploy-fast`

- [ ] **Step 4: Проверить, что правка действительно доехала**

`deploy-fast` через `ssh popstas-pc` врёт дважды и оба раза молча. Первое: `node_modules\windows11-manager` заведён джанкшеном, а сетевому логону OpenSSH джанкшены запрещены — каталог читается как «не существует», строка молча пропускается, и в отчёте «Скопировано ресурсов: 5» вместо шести.

Run (на Windows): `xcopy "D:\projects\js\windows11-manager\src" "%LOCALAPPDATA%\windows-mqtt\_up_\node_modules\windows11-manager\src" /E /Y /I`

Проверить содержимое доехавшего `sessions-helpers.js` — в нём должно быть `HOOK_SKEW_SEC`.

- [ ] **Step 5: Поднять приложение**

Второе враньё: `cmd /c start` из сетевого логона до рабочего стола не доходит — приложение гасится и не поднимается вовсе. Поднимать временной задачей:

```
schtasks /create /tn ccfzf-restart /tr "%LOCALAPPDATA%\windows-mqtt\windows-mqtt.exe" /sc once /st 00:00 /ru popstas /it /f
schtasks /run /tn ccfzf-restart
schtasks /delete /tn ccfzf-restart /f
```

Run: `tasklist /FI "IMAGENAME eq windows-mqtt.exe" /FO CSV`
Expected: строка с `Console` и сессией 1. `Services`/сессия 0 значит, что поднялось не туда.

- [ ] **Step 6: Убедиться, что связка жива**

- Открыть пикер: список приходит, у сессий с окном стоит ▣.
- `node src/index.js claude-wt status` в `windows11-manager` — привязки окон на месте, заголовки не разъехались.
- Панель openHASP: строки живых сессий обновляются.

Если строка окна встала на давно закончившуюся сессию — смотреть `activityAt` в дампе: `python3 -c "import json;d=json.load(open('/home/popstas/.ccfzf.sessions.json'));print([(s['title'],s['activityAt']) for s in d['sessions'][:10]])"`.

- [ ] **Step 7: Отметить в спеке**

Дописать в конец спеки `docs/superpowers/specs/2026-08-10-session-data-flow-design.md` раздел «Как вышло» с фактическими числами замеров из Step 1 и коммит:

```bash
cd /home/popstas/projects/shell/ccfzf
git add docs/superpowers/specs/2026-08-10-session-data-flow-design.md
git commit -m "docs: фактические числа после правки

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
