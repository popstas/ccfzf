# claude-wt-new: иерархия head и корень каталога ребёнка — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** обёртка `claude-wt-new` пускает ребёнка открывать своих детей и отказывает, если разрешённый каталог ребёнка лежит вне корня `CCFZF_CHILD_CWD_ROOT`. Тест подтверждает, что `--state` отдаёт `head`/`headId` привязанным сессиям.

**Architecture:** обе правки живут в bash-обёртке `claude-wt-new`, а именно в её проверках до записи и запуска. Корень обёртка получает переменной окружения, которую подставляет шаблон запуска менеджера. Агрегатор `ccfzf` не меняется. Для него пишется только тест, который закрепляет поведение `read_children`.

**Tech Stack:** bash (обёртка), python3 (проверка head внутри обёртки, агрегатор, тесты без pytest-зависимостей: `python3 tests/test_*.py`).

**Spec:** `/home/popstas/projects/js/windows11-manager/docs/superpowers/specs/2026-11-12-head-hierarchy-and-spawn-cwd-design.md`, части 1 («Правило», последний абзац) и 2 («Снять одноуровневое правило», «Агрегатор ccfzf»).

## Global Constraints

- **Иерархия.** По решению Стаса 12.11 ребёнок может сам быть head и иметь детей. Глубина не ограничена.
- **Контракт с менеджером** (согласован с исполнителем windows11-manager 12.11):
  - Корень передаётся переменной `CCFZF_CHILD_CWD_ROOT`.
  - Шаблон: `exec env CCFZF_CHILD_CWD_ROOT='{childCwdRoot}' ~/bin/claude-wt-new '{cwd}' '{name}' '{sessionId}' '{promptFile}' '{permissionMode}' '{head}' '{headId}'`.
  - Семь позиционных аргументов не меняются: старая обёртка требует `$# == 7`.
- **Нет корня — нет проверки.** Если переменной нет или она пустая, проверка корня не делается и всё работает как сейчас. Так новая обёртка работает со старым шаблоном, а старая обёртка — с новым.
- **Когда менеджер передаёт корень.** Плейсхолдер `{childCwdRoot}` заполняется, только если `cwd` прошёл по правилу корня. Если `cwd` прошёл точным совпадением с `claudeWt.projects`, значение пустое: старый проход спека не трогает. Уточнение отправлено windows11-manager 12.11, подтверждения пока нет. Обёртка этого не знает и проверяет то, что ей передали.
- **Как сравнивать.** И корень, и `cwd` разрешаются через `pwd -P`. `cwd` должен лежать строго под корнем, сам корень ребёнку не годится. Сравнение идёт с `"<корень>/"`, а корень берётся в кавычки, чтобы `*`, `?` и `[` в пути были буквальными.
- **Коды выхода:**
  - `2` — неверный аргумент. Сюда же относится корень, который задан, но не абсолютный или не каталог.
  - `3` — отказ. Сюда же относится `cwd` вне корня.
  - При любом из них ничего не пишется и не запускается, а в терминале обёртка ждёт Enter, как сейчас (`fail`).
- **Живая обёртка.** `~/bin/claude-wt-new` и `~/bin/ccfzf` — симлинки на рабочую копию `/home/popstas/projects/shell/ccfzf`. Поэтому реализация идёт в git worktree ветки `feat/child-hierarchy-root` (superpowers:using-git-worktrees). Рабочая копия остаётся на `main` до мержа, иначе живые окна head получат недоделанную обёртку.
- **Вендорная копия.** `ccfzf-picker/vendor/ccfzf` — сабмодуль. В репо пикера ничего не править: после релиза сессии ccfzf-picker уходит сообщение с коммитом (задача 4).

## Review Focus

1. **`sessionId` ребёнка совпадает с `headId`** или с id любой живой сессии, например предка head. Тогда запись `children/<sid>.json` перезаписывает чужую, и в иерархии появляется цикл, а цикл — антицель спеки. Раньше такого не было, потому что ребёнок не мог быть head. Ожидается отказ `3` до записи. Тест — задача 1, шаг 1.
2. **Соседний префикс:** корень `/x/my`, `cwd` `/x/my project`. Ожидается отказ. Тест — задача 2.
3. **Метасимволы в корне:** корень `/x/r*`, `cwd` `/x/rz/a`. Без кавычек шаблон `[[ == ]]` пропустил бы такой путь. Ожидается отказ. Тест — задача 2.
4. **Корень — симлинк, или задан с хвостовым `/`.** Менеджер нормализует строку, а симлинк не видит. Ожидается: корень разрешается, ребёнок под ним проходит. Тест — задача 2.
5. **Корень `/`.** Ожидается: проходит любой каталог, кроме самого `/`. Это даёт алгоритм с `${root%/}/`. Тест — задача 2.

---

### Задача 1: ребёнок может открывать своих детей

**Files:**
- Modify: `claude-wt-new:20-27` (шапка), `:101-131` (проверка head)
- Modify: `docs/children.md` (раздел «Who may open a child»)
- Test: `tests/test_claude_wt_new.py`

**Interfaces:**
- Produces: проверка head принимает аргументы `mark head_id sid` (без пути к записи ребёнка). Задача 2 вставляет свою проверку перед ней и её не трогает.

- [ ] **Шаг 1: тесты.**
  - В `test_only_a_live_marked_head_that_is_no_child_may_open_one`:
    - убрать случай `head_is_a_child`;
    - добавить `sid_is_running` (`e.alive(HEAD_ID, SID)`) и `sid_is_the_head` (`e.good(sid=HEAD_ID)`), оба ждут `3`;
    - переименовать тест в `test_only_a_live_marked_head_may_open_one`.
  - Новый тест:

```python
def test_a_child_that_is_a_head_opens_a_grandchild():
    e = Env()
    e.children.mkdir()
    own = {"sessionId": HEAD_ID, "name": "h", "head": "top", "headId": OTHER}
    (e.children / (HEAD_ID + ".json")).write_text(json.dumps(own), encoding="utf-8")
    r = e.run(*e.good())
    assert r.returncode == 0, r.stderr
    assert e.record()["headId"] == HEAD_ID and e.record()["head"] == "head-x", e.record()
    # Запись самого head не тронута: у него свой родитель.
    assert e.record(HEAD_ID) == own
```

  - Для `sid_is_the_head` дополнительно проверить `e.record(HEAD_ID) is None`: `nothing_happened` смотрит только на SID.
- [ ] **Шаг 2: прогнать и увидеть падение.** Команда: `python3 tests/test_claude_wt_new.py`. pytest на машине нет, тесты запускаются из `__main__`. Ожидается: новый тест падает с кодом 3 («is itself a child session»), `sid_is_running` и `sid_is_the_head` падают с кодом 0.
- [ ] **Шаг 3: обёртка.**
  - В python-проверке убрать `child` из `sys.argv` и ветку `os.path.exists(child)`.
  - Добавить третий аргумент `sid` и после чтения `agents` отказ: `"session %s is already running" % sid`, если `sid.lower()` равен `sessionId.lower()` какой-нибудь живой сессии. Это закрывает и `sid == headId`, потому что head живой.
  - Вызов: `python3 -c "$head_check" "$heads/$head_id.json" "$head_id" "$sid"`.
  - Шапка, строки 20-27: третий пункт заменить на «sessionId is not a running session: a record must never overwrite a live session's own, and the hierarchy must not loop». Отдельной строкой: «A child may itself be a head and open children; depth is not limited.»
- [ ] **Шаг 4: документация.** `docs/children.md`, «Who may open a child»:
  - первая фраза: «Only a running head session. A child may be one as well: once it has its own mark it opens children of its own, to any depth.»;
  - пункт 3 заменить на проверку из шага 3.
- [ ] **Шаг 5: прогнать.** Команда: `for t in tests/test_*.py; do python3 "$t" >/dev/null || echo FAIL $t; done`. Ожидается: пусто.
- [ ] **Шаг 6: коммит.** `feat(claude-wt-new): ребёнок может открывать своих детей`. В тело коммита — что `sessionId` живой сессии теперь отказ.

### Задача 2: корень каталога ребёнка

**Files:**
- Modify: `claude-wt-new` (новый блок перед `# --- the head check`, строка 94; список переменных в шапке, строки 40-42)
- Modify: `docs/children.md` (новый раздел «Where a child may run» после «Who may open a child»)
- Test: `tests/test_claude_wt_new.py`

**Interfaces:**
- Consumes: `cwd`, уже разрешённый через `pwd -P` (строка 68); `die`/`refuse`.
- Produces: переменная окружения `CCFZF_CHILD_CWD_ROOT` по контракту из Global Constraints.

- [ ] **Шаг 1: тест.** `test_child_cwd_root`. Один `Env` на случай, корень передаётся через `extra_env={"CCFZF_CHILD_CWD_ROOT": ...}`. Каталоги создаются в `e.root`. Для каждого отказа — `e.nothing_happened(label)` и `"claude-wt-new:" in r.stderr`.

| Случай | Корень | `cwd` | Код |
|---|---|---|---|
| пусто | `""` | `e.proj` | 0 |
| под корнем | `e.root` | `e.proj` | 0, `record()["cwd"] == str(e.proj.resolve())` |
| хвостовой `/` | `str(e.root) + "/"` | `e.proj` | 0 |
| корень — симлинк | `e.root/"link"` → `e.root` | `e.proj` | 0 |
| корень `/` | `/` | `e.proj` | 0 |
| сам корень | `e.root` | `e.root` | 3 |
| соседний префикс | `e.root/"my"` (mkdir) | `e.proj` (`my project`) | 3 |
| метасимволы | `e.root/"r*"` (mkdir) | `e.root/"rz"/"a"` (mkdir) | 3 |
| симлинк наружу | `e.root/"in"` | `e.root/"in"/"out"` → `e.root/"outside"` | 3 |
| вне корня | `e.root/"in"` | `e.proj` | 3 |
| относительный | `"in"` | `e.proj` | 2 |
| нет каталога | `e.root/"nope"` | `e.proj` | 2 |

- [ ] **Шаг 2: прогнать и увидеть падение.** Ожидается: случаи с кодами 3 и 2 дают 0.
- [ ] **Шаг 3: обёртка.** Блок ставится до проверки head: отказ по месту не требует спрашивать `claude agents`. Тело задано, потому что ловушки (`/`, префикс, глоб) тестом не исчерпываются:

```bash
# --- where the child may run ---------------------------------------------------
root=${CCFZF_CHILD_CWD_ROOT:-}
if [[ -n $root ]]; then
  [[ $root == /* && -d $root ]] || die "child cwd root must be an absolute directory: '$root'"
  root=$(cd -- "$root" && pwd -P)
  prefix=${root%/}/
  [[ $cwd == "$prefix"?* ]] || refuse "$cwd is not inside the child cwd root $root"
fi
```

  Над блоком — комментарий: менеджер на Windows сравнивает строки и симлинков не видит, поэтому здесь сравнивается разрешённый путь. Объяснить, почему корень передаётся env, а не восьмым аргументом: при восьмом аргументе старая обёртка сломалась бы на новом шаблоне. В список переменных шапки добавить `CCFZF_CHILD_CWD_ROOT  children start only under it (default: no check)`. В шапке «Exit code … 3 when the head check refuses» заменить на «3 when a check refuses (head, cwd root)».
- [ ] **Шаг 4: документация.** Раздел «Where a child may run»:
  - кто ставит переменную (шаблон менеджера, `{childCwdRoot}`) и когда она пустая (проход по `claudeWt.projects`);
  - сравнение после `pwd -P`, сам корень не годится;
  - коды 2 и 3.
  В абзаце про отказы заменить «A refusal is exit 3» на «A refusal — head or cwd root — is exit 3».
- [ ] **Шаг 5: прогнать все тесты.** Команда та же, что в задаче 1, шаг 5. Ожидается: пусто.
- [ ] **Шаг 6: коммит.** `feat(claude-wt-new): каталог ребёнка только под CCFZF_CHILD_CWD_ROOT`.

### Задача 3: `--state` и привязанные сессии

Что видно по коду:
- `read_children` (ccfzf:1336) читает записи ровно для строк ответа `--state`: это `picked` и `extra` (ccfzf:3420).
- Окна и `session-new` его не касаются.
- Привязанный исполнитель живой, а `pick_files` держит живые сессии сверх `limit`.
- Лишние поля записи (`adopted`, `prevHeadId`, `prevHead`) белый список отбрасывает.
- Дамп `sessions` (`~/.ccfzf/sessions.json`) `head` не несёт и раньше не нёс. Спека его не просит.

Задача закрепляет это тестом. Правки кода не ожидается.

**Files:**
- Test: `tests/test_children.py`

- [ ] **Шаг 1: тест.** Тест `test_an_adopted_session_and_a_grandchild_carry_their_heads`:
  - `build_home(tmp, [A, B])`, без файла трекера окон;
  - запись A: `head="new-h"`, `headId=B`, `adopted=True`, `prevHeadId=HEAD_ID`, `prevHead="old-h"`, `cwd="/x"`, `createdAt=1`;
  - запись B: `head="top"`, `headId=HEAD_ID`.
  - Ожидается:
    - `got[A]["head"] == "new-h"`, `got[A]["headId"] == B`;
    - `got[B]["headId"] == HEAD_ID`;
    - у строки A нет ключей `adopted`, `prevHeadId`, `prevHead`.
- [ ] **Шаг 2: прогнать.** Команда: `python3 tests/test_children.py`. Ожидается: `ok` у всех. Если тест падает, код не чинить, а доложить head-session-auto-head: это противоречит части 2 спеки («Ничего не нужно»).
- [ ] **Шаг 3: коммит.** `test(children): привязанная сессия и внук несут своего head`.

### Задача 4: релиз и передача

Начинается после утверждения Стасом и мержа PR. Мерж — только с его разрешения.

- [ ] **Шаг 1: PR.** `feat/child-hierarchy-root` → `main`. После мержа рабочая копия переводится на `main`. Проверка:
  - `ccfzf --state` отвечает;
  - `bash -c` с семью аргументами, где `headId` = `-`, даёт 3;
  - `CCFZF_CHILD_CWD_ROOT=/home/popstas/projects` с `cwd /etc` даёт 3.
- [ ] **Шаг 2: релиз v0.8.0** по процессу репо:
  - `git cliff --tag v0.8.0 -o CHANGELOG.md`;
  - коммит `chore(release): v0.8.0` в `main`;
  - аннотированный тег `v0.8.0` с сообщением `v0.8.0`;
  - push тега;
  - когда workflow отработает, добавить в заметки раздел «Главное» и заголовок, как у v0.7.0.
- [ ] **Шаг 3: сообщения.**
  - ccfzf-picker: тег и мерж-коммит, чтобы он поднял сабмодуль `vendor/ccfzf`.
  - windows11-manager: обёртка с `CCFZF_CHILD_CWD_ROOT` на pc-virt.
  - head-session-auto-head: итог.
- [ ] **Шаг 4: живая проверка** после того, как менеджер выкатит шаблон. Пункты спеки:
  - 2 — симлинк под `~/projects` наружу даёт отказ обёртки;
  - 7 — ребёнок открывает внука.
