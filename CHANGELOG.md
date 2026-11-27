# Changelog


## v0.19.0 - 2026-11-27

### Features

- hooks: The picker's auto-compact keeps the review state and is quiet
- cli: Claude-wt session compact <session> [--min-idle] [--dry-run]
- state: Per-session auto-compact flag (ccfzf --auto-compact <id> on|off)
- hooks: An external wait declared in a human or head turn makes it quiet
- hooks: An answered question no longer makes the turn loud
- hooks: A turn with a question is never quiet
- hooks: LoudAt, stricter quiet
- hooks: TurnFrom and quiet in state.json for quiet head turns

### Bug Fixes

- hooks: An auto-compact from review survives the next idle notification

### Documentation

- Session compact, the auto-compact flag and the quiet auto-compact hook

## v0.18.0 - 2026-11-26

### Features

- cli: Session spawn --model <name>
- claude-wt-new: A child gets its model from <sid>.model
- A session in a git worktree belongs to its main project
- cli: Session type — только дети из session spawn, не усыновлённые
- cli: Claude-wt session type — печать в поле ввода дочерней сессии
- Claude-wt wait set|clear|show, cleared by a human prompt or the head's message
- cli: Claude-wt waiting [--tree] [--json]
- cli: Session spawn intro tells the child that head's messages are the user's commands

### Bug Fixes

- A removed worktree stays remembered while its sessions are asked about
- A child closed by session close is no longer live by its last hook mark
- hooks: Harness notices in plain text keep the declared wait
- cli: Session type — бледная подсказка Claude Code в поле не текст
- cli: Session type — журнал до отправки, скрипт в stdin
- hooks: A subagent prompt keeps the declared wait; test the fingerprint
- cli: Waiting tells permission from other notifications, ? in URLs is no question

### Testing

- limit: Run the real --state in a temporary HOME

## v0.17.0 - 2026-11-24

### Features

- cli: Claude-wt window taskbar hide|show|auto

## v0.16.0 - 2026-11-23

### Features

- cli: Claude-wt window icon, window badge, window icons

## v0.15.0 - 2026-11-22

### Features

- claude-wt: Window place <session> --zone M:P
- claude-wt: Session unread|seen и поле window.unreadAt в --state

### Documentation

- claude-wt: Window place — что session find покажет у зоны вне headZones

### Testing

- state: Окно трекера держит сессию за пределом среза в ответе и в дампе

## v0.14.0 - 2026-11-22

### Features

- state: Записи проектов трекера без хоткея, иконки и типа не выбрасываются
- state: ProjectCwd только при отличии от cwd, флаг projectOwners
- Тип проекта и проект-владелец сессии в --state

### Bug Fixes

- state: Точка в начале имени сессии — часть имени, а не мусор

## v0.13.0 - 2026-11-22

### Features

- cli: Вступление ребёнку зовёт claude-wt session find, а не скрипт скилла
- state: Поле task в --state — задача сессии из вольта
- state: Разбор задач вольтов (sess2task)
- cli: Session open — открыть окно своей сессии
- cli: Session spawn
- cli: Session close и head adopt
- cli: Session rename
- cli: Session find
- cli: Head mark
- state: Поле disconnected — застрявшая очередь ssh-сокета
- state: Разбор SSH_CONNECTION, очередей /proc/net/tcp и вердикт по двум опросам
- cli: Layout отдаёт skipped — кто выпал из группы и почему
- cli: Snapshot list и restore своих сессий
- cli: Window layout — раскладка своей группы
- cli: Window focus — только поднять своё окно
- cli: Разрешение сессии по id, префиксу и имени
- cli: Tree — сессии, окна, head и свои
- cli: Каркас claude-wt и установка симлинком
- hooks: Хуки состояния сессии и SessionStart-дамп в репозитории (#28)
- state: Условный ответ --state --if-changed <fp>

### Bug Fixes

- cli: Session open отказывает живой сессии без окна — второй claude на ту же сессию нельзя
- cli: После ревизии — машина окна у session open, -h как значение, обрыв тела 200 у spawn = 3
- state: Пробы нулевого окна — тоже застой связи
- state: Разрыв требует повторов передачи — очередь сама по себе мигает у пишущей сессии
- state: Серию разрыва сбрасывает убывание против прошлого замера, а не первого
- cli: Candidates в --json и у неоднозначного --sessions
- cli: «no window» от менеджера — код 2, как своя проверка
- cli: Focus не шлёт на чужую машину по --machine/--url
- cli: --machine без учёта регистра, как в spawn.mjs
- cli: Результат без кода выходит отказом 1
- cli: Отказ без caller называет и snapshot list
- cli: Диспетчер не путает команды с именами прототипа
- cli: Кривой --url — отказ до отправки, справка про код 3
- cli: Restore не шлёт пустой sessionIds, обрыв после отправки — исход неизвестен, успех только с ok:true
- state: Залипшая active старше получаса отдаётся как idle
- liveness: Файл оконного трекера учитывает и интерактивный список
- liveness: Запись не может быть старше запуска процесса
- liveness: Last_message_at декодирует строку хвоста до json.loads

### Documentation

- cli: Группы session и head в --help и README, вывод совместим со скриптами скиллов
- state: Поле disconnected и CCFZF_SENDQ_FILE
- cli: Focus только на машину окна, no window — 2, skipped у layout
- cli: Успех только с ok:true, обрыв после отправки — код 3
- cli: Claude-wt — команды, свои сессии, коды выхода, установка
- state: Порог залипшей active обоснован по запускам хука

### Refactor

- cli: Lineage и разбор аргументов скриптов

### Performance

- state: Без повторов передачи проба не обходит /proc — 3,8 мс вместо ~20

## v0.12.0 - 2026-11-22

### Features

- claude-wt-new: Форк-ребёнок по файлу <sid>.fork
- cli: --session принимает имя сессии, не только UUID (#25)
- claude-wt-new: Mcp config and dev channels from side files

### Bug Fixes

- state: Автосжатие посреди хода не считается простоем
- state: Граница сжатия закрывает кеш, ход и состояние агента

## v0.11.0 - 2026-11-16

### Features

- state: Признак shell — ход закончен, а фоновая команда идёт
- cli: --limit по умолчанию 500 вместо 300
- state: Ответ --state вдвое легче — без полей, которых пикер не читает, и без пустых
- cli: --limit по умолчанию 300 вместо 100

### Documentation

- state: Monitor в признаке shell — по коду агента, вживую не сверено

## v0.10.0 - 2026-11-16

### Features

- state: Иконка проекта и корона head от трекера

## v0.9.0 - 2026-11-15

### Features

- windows: Поле icon окна доезжает до читателя

## v0.8.1 - 2026-11-14

### Features

- session: Живую сессию --session открывает, а не поднимает заново
- state: Метка кеша промпта в записи агента

## v0.8.0 - 2026-11-12

### Features

- claude-wt-new: Каталог ребёнка только под CCFZF_CHILD_CWD_ROOT
- claude-wt-new: Ребёнок может открывать своих детей

### Bug Fixes

- claude-wt-new: Четыре мелочи ревью PR #19
- claude-wt-new: Корень не уходит в окружение ребёнка

### Documentation

- plan: Контракт корня согласован с windows11-manager
- plan: Иерархия head и корень каталога ребёнка в claude-wt-new

### Testing

- children: Привязанная сессия и внук несут своего head

## v0.7.0 - 2026-11-11

### Features

- claude-wt-new: Ребёнку не выдаётся bypassPermissions
- claude-wt-new: Ребёнка открывает только живая head-сессия
- state: Head и headId у сессий, открытых через claude-wt-new
- claude-wt-new — новая сессия с заданным id, именем и головой
- state: Спека из чужого каталога и свежие бумаги проекта
- CCFZF_STATE_DUMP_MAX_AGE — заставить --state переписать дамп

### Bug Fixes

- claude-wt-new: Сессия, закрытая сигналом, закрывает и окно
- claude-wt-new: Не тащить в новую сессию метки родительской
- Список сессий больше не роняет ccfzf в шелл

### Documentation

- claude-wt-new: Перенос строк в шапке

## v0.6.0 - 2026-08-25

### Features

- Адрес прямой просьбы едет в записи машины windowHosts
- state: Сессия видна с первого вздоха, а не с первого промпта
- state: Состояние агента — из хвоста транскрипта
- state: --state считает свои пути сам
- windows: Живость сессии — по pid и времени его старта
- windows: Агрегатор читает реестр сессий Claude Code
- state: Агрегатор различает сессии Claude Desktop
- windows: Признак свёрнутого окна доезжает до читателя
- Список задач проекта называет env.STATUSLINE_TODO
- Живость сессий на macOS — процессы через ps вместо /proc

### Bug Fixes

- state: Ответ — UTF-8, какой бы ни была кодовая страница звонящего
- Комментарий пишется и там, где fzf нет вовсе
- Сессия из корня больше не уносит с собой весь каталог проекта

### Documentation

- README короче, подробности — в docs/

## v0.5.0 - 2026-08-18

### Features

- Комментарии к сессиям — общий список на машине агрегатора
- Размер сессии — число реплик человека
- Спека и план сессии в ответе --state
- Счётчики docs/TODO.md у строки проекта
- state: У сессии есть список окон, а не одно
- windows: Запись окна называет терминал
- state: Ход считается по транскрипту, а отметка хука — запасной ход
- state: Снимок называет машину, которая его сняла
- windows: Трекер называет свой адрес и своё умение открывать сессии
- state: --state отдаёт зелийные сессии и держателя каждой сессии
- zellij: Разбор argv сервера и переменной окружения
- state: Несколько файлов трекеров сливаются в один список окон
- state: Файл трекера объявляет, умеет ли он поднимать окно

### Bug Fixes

- Бумагой считается только существующий файл
- Спекой считается и короткий docs/specs/
- Счётчики docs/TODO.md достаются и строкам сессий
- Возраст проекта считается по содержимому, а не по mtime
- windows: Окна одной сессии больше не вытесняют друг друга
- state: Отчёт субагента больше не начинает ход
- state: Пульс статуслайна больше не выдаётся за активность агента

### Documentation

- readme: README is fully in English, without the Claude Code link
- readme: В начале README указан рекомендуемый интерфейс
- plan: Отмечено сделанное, кроме живой проверки
- plan: Сессии zellij в списке — план реализации
- spec: Сессии zellij в списке — дизайн

## v0.4.0 - 2026-08-11

### Features

- state: --state carries per-project hotkeys from the window tracker (#3)

## v0.3.0 - 2026-08-10

### Features

- Суффикс -2 у имени новой сессии при живой тёзке
- state: Снимки раскладки из файла оконного трекера

### Documentation

- План реализации оптимизации потоков данных
- Дизайн оптимизации потоков данных сессий

### Performance

- state: Памятка фактов, --limit и одна форма дампа (#2)

## v0.2.0 - 2026-08-08

### Features

- --state carries projects, and liveness stops trusting mtime
- Attach a process to its session by pid, not by guesswork
- A fresh hook stamp is proof of life on its own
- Move a process to the session id it is actually writing
- state: Optional window data from a tracker elsewhere
- Land the deployed script — --state, usage, background agents
- Name new sessions by basename
- Add --dump for sync sessions rewrite

### Bug Fixes

- Live_by_hook was undoing the reattribute it ran right after
- state: Refresh a stale session dump on the way

### Documentation

- Pid from the hook is now the first argument for a moved session
- Where the live flag comes from

### Testing

- A harness for the embedded python block, and hook stamps

## v0.1.0 - 2026-08-01

### Features

- Name the terminal while a picker is on screen
- --session <id> for non-interactive resume
- Dump every project too, and sessions across all of them
- Dump the shown session list to CCFZF_SESSIONS_FILE
- Kiosk widget on ctrl-t, zsh completion, docs
- Configurable claude command via CCFZF_CLAUDE_COMMAND
- ccfzf — fzf picker for Claude Code projects and sessions

### Bug Fixes

- Run picked commands in an interactive shell

