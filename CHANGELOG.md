# Changelog


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

