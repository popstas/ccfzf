# session compact и флаг автокомпакта — план

Часть 1 проекта «автокомпакт и usage в пикере» (нота
`Notes/2026/11/claude-wt автокомпакт и usage в пикере.md`, решения Стаса
27.11.2026), серверная половина в ccfzf. Клиент — таймер ccfzf-picker на nb.

Ветка `feat/session-compact`, worktree `.claude/worktrees/feat-session-compact`.

## Контракт с клиентом (coord 27.11)

- `ccfzf --auto-compact <id> on|off [host]` — флаг сессии, по образцу
  `--comment`; свой файл `~/.ccfzf.autocompact.json` (`CCFZF_AUTOCOMPACT_FILE`,
  пусто — выключено). В `--state` поле сессии `autoCompact: false` на верхнем
  уровне, только когда выключено; нет поля — включено.
- `claude-wt session compact <id> [--min-idle <мин>] [--dry-run] --json` —
  одна строка `{code, ok, result, reason?, error?, ...}`; выход 0 / 1 отказ /
  2 не найдено / 3 исход неизвестен, как у `session type`.
- `reason` (slug) при отказе: `not-idle`, `question`, `min-idle`, `disabled`,
  `no-window`, `not-wezterm`, `input-busy`; сверх контракта: `usage`,
  `not-found`, `ambiguous`, `not-running`, `dialog`, `wrong-window`, `ssh`,
  `journal`, `not-landed`, `state`; у кода 3 — `unknown`.
- `--min-idle` меряется от `agent.cacheAt` (решение coord: `updated` двигают
  idle-уведомление и `fail` без запроса к API). Нет `cacheAt` — `min-idle`.
  Верхнюю границу (60 мин) проверяет пикер.
- `agent.cacheAt` в `--state` уже есть (`cache_stamp`, `tail_facts`); добавить
  тест, что он доезжает до ответа.

## Находка про хук (проверено по живым state.json)

`/compact` не вызывает UserPromptSubmit: у 15 сессий с `event: compact`
`prompt`/`turnAt` — от прошлого хода. Значит `start` не приходит, `turnFrom` не
меняется, `wait_clear_on_prompt` `wait.json` не трогает. Рычаги — только
Pre/PostCompact.

Сейчас PostCompact с `trigger: manual` кладёт `review` в `idle`. Автокомпакт
приходит тоже `manual`, отличить можно только по журналу
`~/.ccfzf/typed.jsonl`: строка-намерение `session compact` (`command:
"compact"`, `id`, `result: "sending"`, `step: "enter"`, `atSec`), свежее
120 с. Решение принимается на PreCompact и кладётся третьим полем
`.precompact` (`autocompact` вместо `manual`): PostCompact может прийти через
минуты.

Тишина: на PostCompact автокомпакта — прежнее состояние (review остаётся
review), прежний `updated` (KEEP_UPDATED), `loudAt` не трогается, `quiet: true`.
Менеджер по `quiet` глушит звонок WezTerm (isQuietAgent), а мигание гасит,
только если итог прошлого нетихого хода уже видели (quietHidesButton,
loudAt) — состояние просмотра не меняется ни в какую сторону.

## Задачи

### 1. Флаг автокомпакта в ccfzf (TDD, pytest)

- `read_autocompact(path)` → множество id с выключенным автокомпактом
  (белый список, битый файл — пусто).
- `set_autocompact(path, sid, on, now, host)` → bool; `on` удаляет запись,
  `off` кладёт `{off: true, at, host}`; прочие записи сохраняются.
- bash: `--auto-compact <id> on|off [host]`, в guard без fzf; неверное
  значение — код 2.
- `--state`: `autoCompact: false` у выключенных; `state_record` не выбрасывает
  этот `False`; `fingerprint` меняется при переключении. Путь — новым
  аргументом `py state` после `VAULTS_CONFIG`, и в дороге без bash
  (`--state` прямо в python) — умолчание той же функцией.
- Тест: `agent.cacheAt` доезжает до `--state`.

### 2. `claude-wt session compact` (TDD, node --test)

- `session-type.mjs`: только `export` у `where`, `trackerWindow`, `call`
  (поведение `type` не меняется, его тесты не трогаются).
- `cli/lib/commands/session-compact.mjs`: без вызывающей сессии, без проверки
  «свои/не усыновлённые»; `picture(env)` + `resolveSession`.
  Порядок: usage → state → разрешение id → `disabled` → готовность (реестр +
  state.json: `not-running`/`question`/`not-idle`) → `min-idle` по cacheAt →
  окно (`no-window`, `not-wezterm`) → проба (`ssh`, `wrong-window`, `dialog`,
  `input-busy`: любой непустой текст, даже `/compact`) → `--dry-run`: вернуть
  `result: "dry-run"`, журнал не писать → готовность ещё раз → намерение
  `text` → вставка `/compact` → поле содержит `/compact` (`not-landed`) →
  готовность и min-idle ещё раз → намерение `enter` (маркер для хука) → Enter.
- Журнал — `typed.jsonl` (`CLAUDE_WT_TYPED_LOG`), строки с `command:
  "compact"` и `atSec`; `reason` — slug, `error` — текст.
- `claude-wt.mjs`: команда, флаги `--dry-run`, `--min-idle <мин>`, справка.

### 3. Хук wt-progress.sh (TDD, pytest)

- `typed_log` (`CLAUDE_WT_TYPED_LOG`, умолчание `~/.ccfzf/typed.jsonl`).
- PreCompact: свежая строка-намерение `session compact` этой сессии →
  `trigger=autocompact` в `.precompact`.
- PostCompact `autocompact`: без review → idle, `QUIET=true`, прежний
  `updated`.
- Тесты: ручной `/compact` — как было (review → idle, quiet прежний); авто —
  review остаётся, updated/loudAt прежние, quiet true; wait.json цел; старая
  (>120 с) или чужая строка журнала — ручной; строка `session type` — ручной;
  idle-уведомление после авто поверх idle запись не трогает.

### 4. Документация

- `docs/claude-wt.md` — команда, коды, причины, журнал.
- `docs/hooks.md` — автокомпакт тихий, как опознаётся.
- `docs/state.md` — `autoCompact`; README/справка ccfzf — `--auto-compact`.
- Скилл `claude-wt-cli` в репо не живёт (`~/.claude/skills`) — не трогать,
  упомянуть в отчёте.

### 5. Проверка до отчёта

- `node --test tests/cli/*.test.mjs`, `.venv/bin/pytest -q tests`
  (известный флейк: `waiting.test.mjs` «объявленное ожидание…» под нагрузкой,
  в main тоже).
- Вживую из worktree: `env -u CLAUDE_CODE_SESSION_ID CCFZF_BIN=<worktree>/ccfzf
  node cli/claude-wt.mjs session compact <idle wezterm-сессия> --dry-run --json`;
  флаг туда-обратно в `ccfzf --state` worktree-версии.
- Настоящий `/compact` в чужую сессию не слать.

### 6. Деплой (только по команде coord)

- Выкатка: `git checkout feat/session-compact` в живом
  `~/projects/shell/ccfzf` на pc-virt (перед этим `git status` чист, другой
  сессии с этим cwd нет). Переезжают разом `~/bin/ccfzf`, `~/bin/claude-wt`,
  хуки `~/.claude/hooks/`. На Windows ничего не едет: правка только в ccfzf и
  хуках. Мак пропущен, недоступен.
- Проверка: `ccfzf --state` отдаёт `autoCompact: false` у выключенной;
  `claude-wt session compact <id> --dry-run --json` живым бинарём; с coord —
  один настоящий автокомпакт: карточка без оранжевой точки, кнопка не мигает,
  в журнале WezTerm `bell mute`, state.json: состояние прежнее, `quiet: true`.
- Затем мерж PR, `git checkout main && git pull --ff-only` в живом каталоге.
