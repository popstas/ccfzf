#!/usr/bin/env bash
# Метаданные сессии Claude Code для windows11-manager / claude-wt.
#
# Пишет по файлу на сессию в ~/.claude/claude-wt, который с Windows виден через
# сетевой диск, смонтированный на домашний каталог. Состояние (active/question/
# review/idle) пишет соседний wt-progress.sh в *.state.json — здесь только то,
# что известно на старте и дальше не меняется.
#
# Смысл отдельного файла: дамп ccfzf генерируется на хосте пачкой и успевает
# устареть — переименованная или только что созданная сессия в нём ещё не
# значится, и claude-wt не может связать окно с сессией. Этот хук закрывает
# дыру: id, cwd и путь к транскрипту становятся известны в момент старта.
#
# Регистрируется на SessionStart:
#   bash ~/.claude/hooks/claude-wt-agent-state.sh session

set -euo pipefail

action="${1:-}"
input="$(cat 2>/dev/null || true)"

case "$action" in
  session) ;;
  *) exit 0 ;;
esac

command -v jq >/dev/null 2>&1 || exit 0

session_id="$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null || true)"
[ -n "$session_id" ] || exit 0

transcript="$(jq -r '.transcript_path // empty' <<<"$input" 2>/dev/null || true)"
cwd="$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null || true)"
# startup | resume | clear | compact — по нему видно, поднялась сессия заново
# или это продолжение уже существующей.
source_kind="$(jq -r '.source // empty' <<<"$input" 2>/dev/null || true)"
# У Pre/PostCompact поля .source нет (там .trigger = manual|auto), а хук тот же:
# после сжатия транскрипт может смениться, и meta надо переписать. Без фолбэка
# источник затёрся бы пустой строкой.
if [ -z "$source_kind" ]; then
  case "$(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null || true)" in
    PreCompact|PostCompact) source_kind=compact ;;
  esac
fi

# pid процесса claude и момент его запуска.
#
# Хук — потомок claude, поэтому pid берётся подъёмом по родителям до первого
# процесса с comm == claude (замерено: два прыжка через zsh-обёртку).
#
# Зачем он тут: ccfzf связывает окно терминала с сессией по argv процесса, а
# Claude Code меняет id сессии на ходу — после /clear или сжатия argv называет
# транскрипт, в который больше никто не пишет. Замерено 2026-08-06: процесс
# 3049996 сутки писал 86d67681, а argv у него так и остался 6c6931cf, и окно
# уехало не к той сессии. Этот файл пишется ровно в момент смены (source=clear),
# так что pid — единственная связь процесса с сессией, которая не гадает.
#
# Время старта (22-е поле /proc/*/stat) и boot_id идут рядом: pid'ы
# переиспользуются, а тики считаются от загрузки. Без этой пары читатель не
# отличит тот же процесс от нового, занявшего освободившийся номер.
claude_proc() {
  local p="${PPID}" hop stat_line rest
  for hop in 1 2 3 4 5 6 7 8; do
    [ -r "/proc/$p/stat" ] || return 0
    stat_line="$(cat "/proc/$p/stat" 2>/dev/null || true)"
    [ -n "$stat_line" ] || return 0
    # Хвост после ") " — поля с третьего. Резать по нему, а не по номеру поля:
    # comm во втором поле берётся в скобки и может содержать пробелы.
    rest="${stat_line##*') '}"
    set -- $rest
    if [ "$(cat "/proc/$p/comm" 2>/dev/null || true)" = "claude" ]; then
      printf '%s %s' "$p" "${20:-}"
      return 0
    fi
    p="${2:-}"
    [ -n "$p" ] && [ "$p" != 0 ] || return 0
  done
}

claude_pid=""
claude_pid_started=""
read -r claude_pid claude_pid_started <<<"$(claude_proc)" || true
boot_id="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"

state_dir="$HOME/.claude/claude-wt"
mkdir -p "$state_dir" 2>/dev/null || exit 0

target="$state_dir/$session_id.meta.json"
tmp="$target.$$"

# Атомарно: временный файл рядом, затем mv. Читатель на стороне Windows
# никогда не увидит половину записи.
if jq -nc \
    --arg id "$session_id" \
    --arg transcript "$transcript" \
    --arg cwd "$cwd" \
    --arg source "$source_kind" \
    --arg host "$(hostname 2>/dev/null || true)" \
    --arg boot "$boot_id" \
    --argjson pid "${claude_pid:-0}" \
    --argjson pidStarted "${claude_pid_started:-0}" \
    --argjson started "$(date +%s)" \
    '{sessionId: $id, transcript: $transcript, cwd: $cwd, source: $source,
      host: $host, started: $started, pid: $pid, pidStarted: $pidStarted,
      boot: $boot}' \
    >"$tmp" 2>/dev/null; then
  mv -f "$tmp" "$target" 2>/dev/null || rm -f "$tmp" 2>/dev/null || true
else
  rm -f "$tmp" 2>/dev/null || true
fi

exit 0
