# Сессии zellij в списке — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** показать, в какой зелийной сессии живёт агент, и какие зелийные сессии
вообще открыты на машине, — чтобы отсоединённая сессия перестала прятать
работающего внутри агента.

**Architecture:** источник обоих сведений — проход по `/proc`, который
`running_sessions()` уже делает: имя сессии процесса берётся из
`ZELLIJ_SESSION_NAME` в его окружении, список открытых сессий — из argv
процессов `zellij --server <сокет>`. Наружу это уходит полем `zellij` у записи
сессии (рядом с `tmux`) и новым ключом верхнего уровня в `--state`. Пикер
показывает строку на каждую живую зелийную сессию и присоединяется к ней той же
веткой `attach`, что уже есть у tmux.

**Tech Stack:** `ccfzf` — bash-обёртка с python-блоком внутри, тесты
`python3 tests/test_*.py`. `ccfzf-picker` — Tauri 2, фронтенд на простых
`<script>`-модулях в `frontend-src/`, тесты `npm test` (`node --test`).

**Spec:** `docs/superpowers/specs/2026-08-13-zellij-sessions-design.md`

## Global Constraints

- **Два репозитория.** `ccfzf` — `/home/popstas/projects/shell/ccfzf`
  (задачи 1–2). `ccfzf-picker` — `/home/popstas/projects/js/ccfzf-picker`
  (задачи 3–6). Каждая задача называет свой репозиторий явно.
- **Пусто, а не ошибка.** Нет `/proc`, argv поменял форму, окружение не
  читается — список пустой, поле `null`. Без zellij `ccfzf` обязан работать
  ровно как раньше.
- **Ни одного посекундно меняющегося поля в записи zellij.** `poller.rs:38`
  считает отпечаток ответа целиком, вычёркивая только `generated` и `age` у
  сессий. Строка вида `"5m"` в записи zellij меняла бы отпечаток каждую секунду
  и убила бы бэкофф скрытого пикера. Возраст едет только как `created` —
  epoch-секунды, значение неподвижное.
- **Rust не трогаем.** `state_source.rs::fetch` возвращает
  `serde_json::Value` как есть, ответ не разбирается и не чинится — новый ключ
  доезжает до фронтенда сам.
- **Дамп не трогаем.** `DUMP_KEEP` (`ccfzf:1352`) остаётся прежним:
  мультиплексор читателю дампа не нужен.
- **Правки фронтенда — только в `frontend-src/`.** Каталог `frontend/`
  генерируется `scripts/prepare-frontend.js`; правка в нём будет затёрта.

## File Structure

**ccfzf**

| Файл | Ответственность |
|---|---|
| `ccfzf` (python-блок) | `zellij_server_name()`, `zellij_env_name()` — чистый разбор; `proc_zellij()` — чтение `/proc`; сбор в `running_sessions()`; два новых поля в ответе `--state` |
| `tests/test_zellij.py` | новый: чистые разборщики |
| `tests/test_state_mode.py` | форма ответа `--state` |

**ccfzf-picker**

| Файл | Ответственность |
|---|---|
| `frontend-src/zellij-list.js` | новый: строки зелийных сессий из ответа агрегатора |
| `frontend-src/session-list.js` | поле `zellij` в строке сессии |
| `frontend-src/open-strategy.js` | ветка `attach` для zellij |
| `frontend-src/session-groups.js` | группа `Zellij` и подмешивание строк в пакет |
| `frontend-src/session-actions.js` | действия строки `kind: 'zellij'` |
| `scripts/prepare-frontend.js`, `sessions.html` | регистрация нового модуля (только тег `<script>` и список сборки) |
| `test/zellij-list.test.js` | новый |
| `test/open-strategy.test.js`, `test/session-groups.test.js`, `test/session-actions.test.js`, `test/open-transport.test.js`, `test/row-contract.test.js` | дополняются |

Логика открытия в `sessions.html` не меняется: `openSession()` (строка 1045)
собран обобщённо — `chooseOpenStrategy` → `chooseEnterAction` →
`buildOpenCommand` → `spawn_detached`, — и строка zellij проходит его целиком,
не встретив ни одного условия про `kind`. Проверяется это шагом 5 задачи 5.

---

### Task 1: Чистый разбор zellij (ccfzf)

Репозиторий: `/home/popstas/projects/shell/ccfzf`.

**Files:**
- Modify: `ccfzf` — рядом с `proc_tmux` (`ccfzf:834`)
- Test: `tests/test_zellij.py` (создать)

**Interfaces:**
- Consumes: ничего.
- Produces: `zellij_server_name(args) -> str` (имя или `""`),
  `zellij_env_name(items) -> str` (имя или `""`),
  `proc_zellij(pid) -> str | None` (имя или `None`).

- [x] **Step 1: Написать падающий тест**

Создать `tests/test_zellij.py`:

```python
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
```

- [x] **Step 2: Прогнать тест, убедиться, что падает**

Запуск: `python3 tests/test_zellij.py`
Ожидание: `KeyError: 'zellij_server_name'` — функции ещё нет.

- [x] **Step 3: Написать разборщики**

В `ccfzf`, сразу после `proc_tmux()` (кончается на `return target or None`,
`ccfzf:862`), добавить:

```python
def zellij_server_name(args):
    """Имя зелийной сессии по argv её сервера, иначе "".

    Сервер живёт как `zellij --server <путь-сокета>`, и basename пути — это и
    есть имя сессии, то самое, которым её зовут в `zellij attach`.

    Имя бинаря проверяется отдельно от флага, и это не перестраховка:
    `--server` встречается в argv у кого угодно, а спутать чужой процесс с
    держателем сессии значило бы завести в списке строку, к которой не
    присоединиться.

    Воскресимые сессии (`EXITED - attach to resurrect`) сюда не попадают
    даром: процесса у них нет. Отдельного условия под них не нужно.
    """
    if not args or os.path.basename(args[0]) != "zellij":
        return ""
    try:
        i = args.index("--server")
    except ValueError:
        return ""
    path = args[i + 1] if i + 1 < len(args) else ""
    return os.path.basename(path.rstrip("/"))


def zellij_env_name(items):
    """Имя зелийной сессии по строкам /proc/<pid>/environ, иначе "".

    Сравнение вместе со знаком `=`: без него префикс поймал бы соседнюю
    переменную с более длинным именем.
    """
    tag = "ZELLIJ_SESSION_NAME="
    for item in items:
        if item.startswith(tag):
            return item[len(tag):]
    return ""


def proc_zellij(pid):
    """Имя зелийной сессии, в которой живёт процесс, иначе None.

    Вдвое тоньше proc_tmux, и разница не в стиле: tmux кладёт в окружение id
    панели (`%3`), а адрес, по которому к ней можно присоединиться,
    разворачивает только сам tmux — то есть подпроцессом. Zellij кладёт
    готовое имя, разворачивать нечего, и на горячий путь `--state` не выходит
    ни одного нового процесса.
    """
    try:
        with open("/proc/%s/environ" % pid, "rb") as fh:
            env = fh.read().decode("utf-8", "ignore").split("\0")
    except OSError:
        return None
    return zellij_env_name(env) or None
```

- [x] **Step 4: Прогнать тест, убедиться, что проходит**

Запуск: `python3 tests/test_zellij.py`
Ожидание: `9/9 passed`

- [x] **Step 5: Прогнать весь набор — соседей не задели**

Запуск: `for t in tests/test_*.py; do echo "$t: $(python3 "$t" 2>&1 | tail -1)"; done`
Ожидание: у каждого файла строка `N/N passed`; у `test_windows_merge.py`
итоговой строки нет — там достаточно, чтобы не было ни одного `FAIL`.

- [x] **Step 6: Коммит**

```bash
git add ccfzf tests/test_zellij.py
git commit -m "feat(zellij): разбор argv сервера и переменной окружения"
```

---

### Task 2: Сбор в running_sessions и контракт --state (ccfzf)

Репозиторий: `/home/popstas/projects/shell/ccfzf`.

**Files:**
- Modify: `ccfzf:1158-1247` (`running_sessions`), `ccfzf:1556`, `ccfzf:1654`,
  `ccfzf:1729`, запись сессии (`ccfzf:1794`), `json.dump` режима `state`
  (`ccfzf:1842`)
- Test: `tests/test_state_mode.py`

**Interfaces:**
- Consumes: `zellij_server_name(args)`, `proc_zellij(pid)` из задачи 1.
- Produces: `running_sessions()` возвращает **четыре** значения —
  `(live, agents, procs, zellij)`, где `zellij` это
  `list[{"name": str, "created": int, "pid": int, "agents": int}]`,
  отсортированный по `name`. В ответе `--state` появляются ключ верхнего уровня
  `zellij` (тот же список) и поле `zellij` у каждой записи сессии (`str | null`).

- [x] **Step 1: Написать падающий тест формы ответа**

В `tests/test_state_mode.py`, рядом с
`test_the_state_answer_keeps_its_rich_shape`, добавить:

```python
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
```

- [x] **Step 2: Прогнать тест, убедиться, что падает**

Запуск: `python3 tests/test_state_mode.py`
Ожидание: два `FAIL` — `zellij` нет ни в ответе, ни в записи сессии.

- [x] **Step 3: Собрать список в running_sessions**

В `ccfzf`, в `running_sessions()`. Заменить строку инициализации:

```python
    live, fresh, agents, procs = set(), [], {}, {}
```

на:

```python
    live, fresh, agents, procs = set(), [], {}, {}
    # Держатели зелийных сессий и счётчик агентов по именам. Считается двумя
    # словарями, а не одним: сервер и живущий в нём claude встречаются в
    # произвольном порядке — /proc отдаёт pid'ы как попало, и счётчик обязан
    # пережить случай «агент найден раньше своего сервера».
    zellij, zellij_agents = {}, {}
```

Сразу после `except OSError: continue` (получение `args`) и **до** проверки
`is_claude`, добавить:

```python
        # Сервер зелийной сессии — не сессия агента, и дальше по циклу ему
        # делать нечего. Возраст берётся у каталога процесса: сверено с mtime
        # сокета сессии, совпадает секунда в секунду.
        server = zellij_server_name(args)
        if server:
            try:
                created = int(os.path.getmtime("/proc/%s" % pid))
            except OSError:
                created = 0
            zellij[server] = {"name": server, "created": created,
                              "pid": int(pid), "agents": 0}
            continue
```

Сразу после `if not is_claude(args): continue` добавить:

```python
        # До отсева NOT_A_SESSION намеренно: счётчик отвечает на вопрос «есть
        # ли внутри чему пропасть», а демон фоновых агентов — это ровно оно.
        # Поле про свою сессию берётся здесь же, одним чтением на процесс.
        here = proc_zellij(pid)
        if here:
            zellij_agents[here] = zellij_agents.get(here, 0) + 1
```

В сборке `procs[sid]` добавить поле:

```python
        procs[sid] = {"pid": int(pid), "tty": proc_tty(pid), "tmux": proc_tmux(pid),
                      "zellij": here, "cwd": proc_cwd(pid)}
```

Заменить `return live, agents, procs` (конец `running_sessions`) на:

```python
    for name, n in zellij_agents.items():
        if name in zellij:
            zellij[name]["agents"] = n
    # Порядок по имени, а не по времени: список читает отпечаток ответа
    # (poller.rs), и порядок, зависящий от обхода /proc, дёргал бы его без
    # всякой причины.
    return live, agents, procs, sorted(zellij.values(), key=lambda r: r["name"])
```

- [x] **Step 4: Поправить три места вызова**

`ccfzf:1556` — было `live, _, _ = running_sessions()`, стало:

```python
    live, _, _, _ = running_sessions()
```

`ccfzf:1654` — было `live, agents, _ = running_sessions()`, стало:

```python
    live, agents, _, _ = running_sessions()
```

`ccfzf:1729` — было `live, agents, procs = running_sessions()`, стало:

```python
    live, agents, procs, zellij_rows = running_sessions()
```

- [x] **Step 5: Вывести оба поля наружу**

В записи сессии (`ccfzf:1794`, строка `"tmux": ...`) — добавить следом:

```python
            "tmux": (procs.get(sid) or {}).get("tmux"),
            "zellij": (procs.get(sid) or {}).get("zellij"),
```

В `json.dump` режима `state` — добавить ключ после `"snapshots"`:

```python
               "snapshots": window_snapshots,
               # Открытые зелийные сессии, все до одной. Не только те, внутри
               # которых агента нет: список сессий обрезан (`--limit`), агент
               # может в срез не попасть, и тогда пропала бы и его строка, и
               # строка его зелийной сессии — ровно та невидимость, ради
               # которой всё делается.
               "zellij": zellij_rows},
```

- [x] **Step 6: Прогнать тесты**

Запуск: `python3 tests/test_state_mode.py`
Ожидание: все тесты файла `passed`, включая два новых.

- [x] **Step 7: Проверить на живой машине**

Запуск: `~/bin/ccfzf --state | jq '{zellij, session: .sessions[0] | {id, tmux, zellij}}'`
Ожидание: `zellij` — список записей с четырьмя полями, по одной на каждый
живой `zellij --server` (сверить с `pgrep -af "zellij --server"`); у записи
сессии поле `zellij` присутствует.

- [x] **Step 8: Прогнать весь набор**

Запуск: `for t in tests/test_*.py; do echo "$t: $(python3 "$t" 2>&1 | tail -1)"; done`
Ожидание: ни одного `FAIL`.

- [x] **Step 9: Коммит**

```bash
git add ccfzf tests/test_state_mode.py
git commit -m "feat(state): --state отдаёт зелийные сессии и держателя каждой сессии"
```

---

### Task 3: Поле zellij в строке и ветка attach (ccfzf-picker)

Репозиторий: `/home/popstas/projects/js/ccfzf-picker`.

**Files:**
- Modify: `frontend-src/session-list.js` (поле рядом с `tmux`),
  `frontend-src/open-strategy.js` (`chooseOpenStrategy`, `buildOpenCommand`)
- Test: `test/open-strategy.test.js`

**Interfaces:**
- Consumes: поле `zellij` записи сессии из задачи 2.
- Produces: строка списка несёт `zellij: string | null`; `chooseOpenStrategy`
  возвращает `'attach'` и для zellij; `buildOpenCommand(row, 'attach', opts)`
  собирает `zellij attach <name>`, когда `row.tmux` пуст, а `row.zellij` нет.

- [x] **Step 1: Написать падающие тесты**

В `test/open-strategy.test.js` добавить:

```javascript
test('строка внутри zellij открывается присоединением, а не вторым процессом', () => {
  const row = { id: 'a', live: true, pid: 42, zellij: 'obsidian-agent-base' };
  assert.strictEqual(chooseOpenStrategy(row, { reptyr: true }, {}), 'attach');
  const cmd = buildOpenCommand(row, 'attach', { sshHost: 'pc-virt', terminal: { file: 'wt', args: [] } });
  assert.ok(cmd.argv.includes("zellij attach 'obsidian-agent-base'"), cmd.argv);
  assert.strictEqual(cmd.destructive, false);
});

test('при обоих мультиплексорах выигрывает tmux', () => {
  // Порядок веток — по убыванию сохранности, и между двумя одинаково
  // сохранными решает то, что было раньше: менять привычное поведение
  // tmux-строк эта правка не должна.
  const row = { id: 'a', live: true, tmux: 'main:0.1', zellij: 'home' };
  const cmd = buildOpenCommand(row, 'attach', { sshHost: 'pc-virt', terminal: { file: 'wt', args: [] } });
  assert.ok(cmd.argv.includes("tmux attach -t 'main:0.1'"), cmd.argv);
});

test('строка зелийной сессии присоединяется своим же именем', () => {
  // У строки kind: 'zellij' нет ни pid, ни живой сессии — только имя, и его
  // хватает: поле одно и то же, ветка одна и та же.
  const row = { id: 'zellij:home', kind: 'zellij', zellij: 'home' };
  assert.strictEqual(chooseOpenStrategy(row, {}, {}), 'attach');
  const cmd = buildOpenCommand(row, 'attach', { sshHost: 'pc-virt', terminal: { file: 'wt', args: [] } });
  assert.ok(cmd.argv.includes("zellij attach 'home'"), cmd.argv);
});
```

- [x] **Step 2: Прогнать тесты, убедиться, что падают**

Запуск: `npm test -- --test-name-pattern="zellij"`
Ожидание: FAIL — `chooseOpenStrategy` возвращает `'reptyr'`/`'resume'`, а
команда собирается с `tmux attach -t 'undefined'` либо `null`.

- [x] **Step 3: Поле в строке сессии**

В `frontend-src/session-list.js`, в возвращаемом объекте после `tmux:`:

```javascript
          tmux: s.tmux || null,
          // Зелийная сессия, в которой живёт процесс. Того же рода, что и
          // `tmux`, и читает её то же место (chooseOpenStrategy): отсоединённая
          // зелийная сессия — единственный случай, когда терминал сессии
          // существует, но не открыт нигде, и без этого поля найти его нечем.
          zellij: s.zellij || null,
```

- [x] **Step 4: Ветка привязки**

В `frontend-src/open-strategy.js`, в `chooseOpenStrategy`, заменить строку
`if (row.tmux) return 'attach';` на:

```javascript
    if (row.tmux || row.zellij) return 'attach';
```

и дописать в её докблок, к абзацу про порядок ветвей:

```javascript
   * Мультиплексоров два, и оба стоят до reptyr по одной причине: присоединение
   * ничего не трогает. Между собой решает не сохранность — она одинаковая, — а
   * то, что tmux-ветка была здесь раньше; менять её поведение эта правка не
   * должна. Одно и то же поле `zellij` обслуживает и строку агента, живущего
   * внутри zellij, и строку самой зелийной сессии: у второй в нём её
   * собственное имя, и разбирать `kind` тут не приходится.
```

В `buildOpenCommand`, в ветке `attach`:

```javascript
    if (strategy === 'attach') {
      remote = row.tmux ? `tmux attach -t ${q(row.tmux)}` : `zellij attach ${q(row.zellij)}`;
    } else if (strategy === 'reptyr') {
```

- [x] **Step 5: Прогнать тесты**

Запуск: `npm test`
Ожидание: все тесты проходят, включая три новых.

- [x] **Step 6: Коммит**

```bash
git add frontend-src/session-list.js frontend-src/open-strategy.js test/open-strategy.test.js
git commit -m "feat(zellij): строка знает свою зелийную сессию и присоединяется к ней"
```

---

### Task 4: Модуль строк зелийных сессий (ccfzf-picker)

Репозиторий: `/home/popstas/projects/js/ccfzf-picker`.

**Files:**
- Create: `frontend-src/zellij-list.js`, `test/zellij-list.test.js`
- Modify: `scripts/prepare-frontend.js` (список `FILES`), `sessions.html`
  (теги `<script>`)

**Interfaces:**
- Consumes: ключ `zellij` ответа агрегатора из задачи 2.
- Produces: `ZellijList.buildZellijList({ zellij }) -> rows`, где строка это
  `{kind: 'zellij', id: 'zellij:<name>', label, name, zellij, agents,
  lastActivity, live: true, cwd: ''}`.

- [x] **Step 1: Написать падающий тест**

Создать `test/zellij-list.test.js`:

```javascript
const { test } = require('node:test');
const assert = require('node:assert');
const { buildZellijList } = require('../frontend-src/zellij-list');

test('строка собирается из записи агрегатора', () => {
  const [row] = buildZellijList({
    zellij: [{ name: 'obsidian-agent-base', created: 1785591360, pid: 1228224, agents: 1 }],
  });
  assert.strictEqual(row.kind, 'zellij');
  assert.strictEqual(row.id, 'zellij:obsidian-agent-base');
  assert.strictEqual(row.label, 'obsidian-agent-base');
  assert.strictEqual(row.zellij, 'obsidian-agent-base');
  assert.strictEqual(row.lastActivity, 1785591360);
  assert.strictEqual(row.agents, 1);
  assert.strictEqual(row.live, true);
});

test('id носит префикс, чтобы не столкнуться с uuid сессии', () => {
  // Ключ строки в DOM общий на весь список; зелийную сессию законно назвать
  // как угодно, в том числе тридцатью шестью шестнадцатеричными знаками.
  const [row] = buildZellijList({ zellij: [{ name: '0624d3a3-be36-4c4c-a383-269d3490a398' }] });
  assert.ok(row.id.startsWith('zellij:'), row.id);
});

test('мусор отсеивается, а не роняет список', () => {
  assert.deepStrictEqual(buildZellijList({}), []);
  assert.deepStrictEqual(buildZellijList({ zellij: null }), []);
  assert.deepStrictEqual(buildZellijList({ zellij: 'нет' }), []);
  assert.deepStrictEqual(buildZellijList({ zellij: [null, {}, { name: '' }] }), []);
});

test('недостающие числа становятся нулями, а не NaN', () => {
  // NaN в lastActivity утопил бы строку мимо missingLast, а в колонке
  // возраста нарисовался бы словом.
  const [row] = buildZellijList({ zellij: [{ name: 'home' }] });
  assert.strictEqual(row.lastActivity, 0);
  assert.strictEqual(row.agents, 0);
});
```

- [x] **Step 2: Прогнать тест, убедиться, что падает**

Запуск: `npm test -- --test-name-pattern="строка собирается"`
Ожидание: FAIL — `Cannot find module '../frontend-src/zellij-list'`.

- [x] **Step 3: Написать модуль**

Создать `frontend-src/zellij-list.js`:

```javascript
// Loaded twice: as a <script> in sessions.html and as a module in the tests.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ZellijList = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  /**
   * Строки зелийных сессий из ответа агрегатора.
   *
   * Строка заводится каждой живой зелийной сессии, а не только тем, внутри
   * которых нет агента. Причина не в полноте ради полноты: список сессий в
   * ответе обрезан (`--limit`, по умолчанию 100), и агент внутри зелийной
   * сессии может в срез не попасть — тогда не стало бы ни его строки, ни
   * строки его зелийной сессии, то есть ровно той невидимости, ради которой
   * режим и заведён. Сколько агентов внутри, говорит `agents`.
   *
   * `label` и `lastActivity` названы так же, как у сессии и у проекта: имя
   * рисует и ищет общий код, колонку возраста — общая ageHtml, и второе имя
   * для того же смысла им пришлось бы объяснять.
   *
   * `zellij` — своё же имя. Через это поле строка попадает в ветку `attach`
   * (open-strategy.js) без единого условия про `kind`.
   *
   * `live: true` — сессия существует, пока жив её сервер; строка мёртвой
   * зелийной сессии сюда не приезжает вовсе (агрегатор их не видит).
   */
  function buildZellijList({ zellij } = {}) {
    const list = Array.isArray(zellij) ? zellij : [];
    return list
      .filter(z => z && typeof z.name === 'string' && z.name)
      .map(z => ({
        kind: 'zellij',
        // Префикс обязателен: ключ строки в DOM общий на весь список, а
        // зелийную сессию законно назвать как угодно — хоть uuid сессии.
        id: `zellij:${z.name}`,
        label: z.name,
        name: z.name,
        zellij: z.name,
        agents: Number(z.agents) || 0,
        lastActivity: Number(z.created) || 0,
        live: true,
        // Каталога у зелийной сессии нет: панели в ней могут стоять в разных.
        // Пустая строка, а не undefined, — действия папки спрашивают именно
        // её и на пустой молчат.
        cwd: '',
      }));
  }

  return { buildZellijList };
});
```

- [x] **Step 4: Прогнать тест**

Запуск: `npm test -- --test-name-pattern="zellij"`
Ожидание: четыре новых теста проходят.

- [x] **Step 5: Зарегистрировать модуль в сборке фронтенда**

В `scripts/prepare-frontend.js`, в массиве `FILES`, после
`'frontend-src/project-list.js',` добавить:

```javascript
  'frontend-src/zellij-list.js',
```

В `sessions.html`, после `<script src="project-list.js"></script>` (строка 329)
добавить:

```html
<script src="zellij-list.js"></script>
```

- [x] **Step 6: Прогнать весь набор**

Запуск: `npm test`
Ожидание: все тесты проходят. `frontend-load.test.js` сторожит, что каждый
тег `<script>` в `sessions.html` имеет файл в списке сборки, — забытая
регистрация упадёт здесь.

- [x] **Step 7: Коммит**

```bash
git add frontend-src/zellij-list.js test/zellij-list.test.js scripts/prepare-frontend.js sessions.html
git commit -m "feat(zellij): строки зелийных сессий из ответа агрегатора"
```

---

### Task 5: Группа в списке и действия строки (ccfzf-picker)

Репозиторий: `/home/popstas/projects/js/ccfzf-picker`.

**Files:**
- Modify: `frontend-src/session-groups.js` (`groupSessions`,
  `buildSessionsPayload`), `frontend-src/session-actions.js`
  (`availableActions`)
- Test: `test/session-groups.test.js`, `test/session-actions.test.js`

**Interfaces:**
- Consumes: `ZellijList.buildZellijList` из задачи 4.
- Produces: `buildSessionsPayload(res, sort, opts)` кладёт группу
  `{label: 'Zellij - N', sessions: [...]}` последней; `availableActions(row)`
  на строке `kind: 'zellij'` даёт только `[{id: 'info', label: 'Session info'}]`.

- [x] **Step 1: Написать падающие тесты**

В `test/session-groups.test.js` добавить:

```javascript
test('зелийные сессии идут своей группой, и она последняя', () => {
  const res = {
    ok: true,
    sessions: [
      { id: 'a', title: 'жив', live: true, agent: { state: 'active', updated: 100 } },
      { id: 'b', title: 'мёртв', live: false },
    ],
    zellij: [{ name: 'home', created: 50, agents: 0 }],
  };
  const out = buildSessionsPayload(res, 'recent');
  const labels = out.groups.map(g => g.label);
  assert.strictEqual(labels[labels.length - 1], 'Zellij - 1');
  const last = out.groups[out.groups.length - 1].sessions;
  assert.strictEqual(last.length, 1);
  assert.strictEqual(last[0].kind, 'zellij');
  // Живая группа не должна их всосать: у строки live: true, и без явной
  // ветки она встала бы среди работающих агентов.
  assert.ok(!out.groups[0].sessions.some(s => s.kind === 'zellij'));
});

test('без зелийных сессий группы не появляется вовсе', () => {
  const res = { ok: true, sessions: [{ id: 'a', title: 'жив', live: true }], zellij: [] };
  const out = buildSessionsPayload(res, 'recent');
  assert.ok(!out.groups.some(g => g.label.startsWith('Zellij')));
});

test('отсев onlyLive и onlyWindow зелийных строк не касается', () => {
  // Оба отсева про сессии агента: у зелийной строки окна нет никогда, и
  // onlyWindow вычистил бы весь режим.
  const res = {
    ok: true,
    sessions: [{ id: 'a', title: 'жив', live: true }],
    zellij: [{ name: 'home', created: 50 }],
  };
  const out = buildSessionsPayload(res, 'recent', { onlyWindow: true });
  assert.ok(out.groups.some(g => g.label === 'Zellij - 1'));
});
```

В `test/session-actions.test.js` добавить:

```javascript
test('строке зелийной сессии предлагается только информация', () => {
  // Ни записи агента, ни pid, ни каталога — всё сессионное ей не подходит, а
  // присоединение висит на Enter и в меню не прячется.
  const actions = availableActions({ kind: 'zellij', id: 'zellij:home', zellij: 'home', live: true });
  assert.deepStrictEqual(actions, [{ id: 'info', label: 'Session info' }]);
});
```

- [x] **Step 2: Прогнать тесты, убедиться, что падают**

Запуск: `npm test -- --test-name-pattern="зелийн"`
Ожидание: FAIL — группы `Zellij - 1` нет, а `availableActions` возвращает
`New session`/`Session info`.

- [x] **Step 3: Завести группу**

В `frontend-src/session-groups.js`, в начало `groupSessions`, сразу после
`const mode = normalizeSort(sort);`:

```javascript
    const mode = normalizeSort(sort);
    // Зелийные строки отбираются до всего остального: у них live: true, и
    // живая группа всосала бы их к работающим агентам, где им не место.
    // Своя группа стоит последней — это справочник «что ещё открыто на
    // машине», а не то, к чему возвращаются в первую очередь.
    const zellij = [];
    const rest = [];
    for (const s of sessions) (s.kind === 'zellij' ? zellij : rest).push(s);
    sessions = rest;
```

В конце `groupSessions` заменить два `return`:

```javascript
    const tail = zellij.length
      ? [{ desktop: null, label: `Zellij - ${zellij.length}`, sessions: sortGroupSessions(zellij, mode) }]
      : [];

    if (!open.length) return [...past, ...tail];
    sortGroupSessions(open, mode);
    return [{ desktop: null, label: `Active sessions - ${open.length}`, sessions: open },
            ...past, ...tail];
```

В `buildSessionsPayload` заменить тело после отсевов:

```javascript
    let rows = listApi.buildSessionList({ sessions: res.sessions, seen: res.seen });
    if (opts.onlyLive) rows = rows.filter(r => r.live);
    if (opts.onlyWindow) rows = rows.filter(r => r.window);
    // Отсевы выше — про сессии агента, и на зелийные строки они не
    // распространяются: окна у зелийной сессии нет никогда, и onlyWindow
    // вычистил бы весь режим целиком. Поэтому строки подмешиваются после.
    const zellij = zellijApi.buildZellijList({ zellij: res.zellij });
    return { ok: true, groups: groupSessions([...labelSessions(rows), ...zellij], mode), sort: mode };
```

И объявить зависимость рядом с уже существующей `listApi` (верх файла):

```javascript
  const zellijApi = typeof module === 'object' && module.exports
    ? require('./zellij-list')
    : globalThis.ZellijList;
```

- [x] **Step 4: Ограничить действия**

В `frontend-src/session-actions.js`, в `availableActions`, сразу после ветки
`kind === 'project'`:

```javascript
    // Зелийная сессия — терминал, а не работа агента: записи агента, pid и
    // истории у неё нет, а каталог у её панелей может быть разный. Открытие в
    // меню не значится намеренно — оно висит на Enter, как у всех строк.
    if ((row || {}).kind === 'zellij') return [{ id: 'info', label: 'Session info' }];
```

- [x] **Step 5: Закрепить, что Enter уходит местной дорогой**

`sessions.html` править не нужно, и это не везение, а уже заложенная защита:
`chooseEnterAction` (`open-transport.js:156`) уводит в `'local'` любой вид
строки, которого нет в позитивном списке `SESSION_ID_ROW_KINDS`
(`['interactive', 'snapshot-session']`), — там же и записано, почему список
позитивный: чтобы новый вид строки не уехал в `claude-session-open` с чужим
`id`. Строка zellij проходит по нему в `buildOpenCommand`, то есть ровно туда,
куда нужно.

Держится это на списке, который легко «починить» не глядя, поэтому
закрепляется тестом. В `test/open-transport.test.js` добавить:

```javascript
test('строка зелийной сессии не уезжает к менеджеру со своим id', () => {
  // `zellij:home` — не id сессии, и менеджер ответил бы `unknown session` в
  // свой лог, а пикер бы этого не увидел: у публикации нет ответа.
  const row = { id: 'zellij:home', kind: 'zellij', zellij: 'home' };
  const state = { windowHost: 'popstas-pc' };
  assert.strictEqual(chooseEnterAction(row, 'attach', state, 'popstas-pc', true), 'local');
  assert.strictEqual(canOpenRemote(row, state, 'другой-хост', true), false);
});
```

В `test/row-contract.test.js` добавить — это единственный тест, который гоняет
строку настоящим путём до отрисовщиков:

```javascript
test('строка зелийной сессии доезжает до отрисовки и не пустует', () => {
  // Строки проектов живут в своём режиме, а эта идёт в общий список сессий —
  // дорогой, которой строка-не-сессия ещё не ходила. Здесь и видно, если
  // отрисовщик спросит поле, которого у неё нет.
  const state = { ok: true, sessions: [], zellij: [{ name: 'home', created: 1785591360, agents: 0 }] };
  const payload = buildSessionsPayload(state, 'recent');
  const group = payload.groups.find(g => g.label === 'Zellij - 1');
  assert.ok(group, payload.groups.map(g => g.label));
  const html = renderRows(group.sessions);
  assert.ok(html.includes('home'), html);
});
```

Если вспомогательной `renderRows` в файле нет под этим именем — взять ту,
которой пользуются соседние тесты этого файла (`renderProjectRows`,
`renderSnapshotRows` собраны там же по одному образцу), и добавить сестринскую
для строк общего списка.

- [x] **Step 6: Прогнать весь набор**

Запуск: `npm test`
Ожидание: все тесты проходят, включая шесть новых.

- [x] **Step 7: Коммит**

```bash
git add frontend-src/session-groups.js frontend-src/session-actions.js \
        test/session-groups.test.js test/session-actions.test.js \
        test/open-transport.test.js test/row-contract.test.js
git commit -m "feat(zellij): своя группа в списке и действия её строк"
```

---

### Task 6: Деплой на Windows

Репозиторий: `/home/popstas/projects/js/ccfzf-picker`.

Отдельной задачей, а не строчкой в предыдущей: код лежит на pc-virt, а
работает на Windows, и до выкатки правка не проверена ничем, кроме тестов.
`ccfzf` при этом никуда не едет — его читают по ssh с машины пикера, и он уже
на месте после задач 1–2.

**Files:** правок нет, только выкатка и проверка.

- [x] **Step 1: Запушить коммиты пикера**

Обязательно **до** выкатки, а не после: `deploy-win.sh` не копирует файлы с
этой машины — он делает `git fetch && git checkout && git pull --ff-only` в
`D:\projects\js\ccfzf-picker` на самой Windows-машине. Незапушенные задачи
3–5 туда просто не доедут, а скрипт при этом отработает без единой ошибки и
соберёт прежний код.

```bash
git push
git log --oneline origin/HEAD -1
```

Ожидание: последний коммит на origin — из задачи 5.

Ветка, которую скрипт выкатывает, задана в нём же (`BRANCH`, по умолчанию
`windows-mqtt-migrate`). Если работа шла в другой ветке — либо влить её в эту,
либо запустить деплой с `BRANCH=<своя> ./data/scripts/deploy-win.sh`.

- [x] **Step 2: Убедиться, что сторона агрегатора уже на месте**

Запуск: `ssh pc-virt 'cd ~/projects/shell/ccfzf && git log --oneline -1 && ~/bin/ccfzf --state | jq -c ".zellij"'`
Ожидание: последний коммит — из задачи 2, и список зелийных сессий непустой
(сверить с `ssh pc-virt 'pgrep -af "zellij --server"'` — записей должно быть
столько же).

`ccfzf` выкатывать не нужно: он читается по ssh прямо из рабочего каталога на
pc-virt, и задачи 1–2 уже положили его туда.

- [x] **Step 3: Выкатить пикер**

Запуск: `./data/scripts/deploy-win.sh`
Ожидание: по шагам — обновление репозитория, `EXE_OK`, сборка, регистрация
задачи планировщика, запуск, и в конце `tasklist` показывает `ccfzf-picker.exe`
в сессии 1 (не 0 — там нет рабочего стола). Скрипт лежит вне git
(`data/` в .gitignore).

- [x] **Step 4: Проверить, что новый модуль доехал**

Запуск: `ssh popstas-pc 'dir /b D:\projects\js\ccfzf-picker\frontend\zellij-list.js'`
Ожидание: файл назван, а не `File Not Found`. Забытая регистрация в
`prepare-frontend.js` даёт именно эту картину: тесты зелёные, файл в
`frontend-src/` есть, в `frontend/` его нет, а в приложении группа пуста и в
консоли `ZellijList is not defined`.

- [ ] **Step 5: Живая проверка**

1. Открыть пикер.
2. Ожидание: внизу списка группа `Zellij - N`, по строке на каждую живую
   зелийную сессию pc-virt.
3. Встать на строку, нажать Enter.
4. Ожидание: открывается терминал, присоединённый к этой зелийной сессии.
5. Найти строку агента, живущего внутри zellij (`agents` у его сессии больше
   нуля), нажать Enter.
6. Ожидание: открывается та же зелийная сессия, а не второй процесс `claude`
   рядом с первым.

- [x] **Step 6: Убедиться, что скрытый пикер не крутится впустую**

Правка добавила ключ в ответ, а `poller.rs::fingerprint` хеширует ответ
целиком — посекундно меняющееся поле в записи zellij убило бы бэкофф скрытого
пикера (см. Global Constraints). Проверка прямая: два вызова подряд при
неизменной обстановке обязаны дать одинаковый список.

```bash
ssh pc-virt '~/bin/ccfzf --state | jq -cS ".zellij"' > /tmp/z1.json
sleep 5
ssh pc-virt '~/bin/ccfzf --state | jq -cS ".zellij"' > /tmp/z2.json
diff /tmp/z1.json /tmp/z2.json && echo "отпечаток стабилен"
```

Ожидание: `отпечаток стабилен`. Разница означает, что в запись просочилось
живое поле — исправлять в задаче 2, а не мириться.

---

## Что этот план намеренно не делает

- **Признака «присоединена/отсоединена» у зелийной сессии.** Клиентских
  процессов zellij на машине не бывает вовсе, отличать нечего.
- **Действия `kill-session`.** Строка умеет только присоединять; убийство
  сессии вместе со всем, что в ней работает, потребовало бы отдельного
  подтверждения, как у ветки `takeover`.
- **Отдельного списка tmux-сессий.** Запущенных сессий tmux на машине нет ни
  одной, поле `tmux` осталось от прежней схемы и работает.
- **Правок в Rust.** `state_source.rs::fetch` отдаёт ответ как есть, а
  `poller.rs::fingerprint` хеширует его целиком — новый ключ и будит пикер, и
  доезжает до фронтенда без единой строчки на Rust.
