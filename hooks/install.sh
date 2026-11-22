#!/usr/bin/env bash
# Поставить хуки claude-wt симлинками: ~/.claude/hooks/<файл> → <клон>/hooks/<файл>.
#
# Симлинк, а не копия, по той же причине, что и ~/bin/ccfzf: `git pull` в
# клоне обновляет хуки сразу, и разъехаться живой копии с репозиторием нечем.
#
# Идемпотентен. Правильный симлинк не трогает; файл с тем же содержимым
# заменяет молча; другой файл или чужой симлинк сначала уводит в
# <файл>.bak-<дата> (второй за день — .bak-<дата>-2 и дальше, прежний бэкап не
# затирается).
#
# settings.json не правит: печатает фрагмент, который туда надо влить руками.
# Слить его с чужими хуками и statusLine надёжно может только человек.
#
# Из git worktree ставить отказывается: worktree удаляют после мержа, и
# симлинки повисли бы. Ставить надо из основного клона.
#
#   hooks/install.sh             поставить
#   hooks/install.sh --dry-run   только сказать, что сделал бы

set -euo pipefail

dry=0
case "${1:-}" in
  "") ;;
  --dry-run|-n) dry=1 ;;
  -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "install.sh: unknown argument: $1" >&2; exit 2 ;;
esac

FILES="wt-progress.sh claude-wt-statusline.sh claude-wt-agent-state.sh ccfzf-dump.sh"

self="$(readlink -f "${BASH_SOURCE[0]}")"
src_dir="$(dirname "$self")"
root="$(dirname "$src_dir")"

if command -v git >/dev/null 2>&1 \
    && git_dir="$(git -C "$root" rev-parse --path-format=absolute --git-dir 2>/dev/null)" \
    && common="$(git -C "$root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
    && [ "$git_dir" != "$common" ]; then
  main="$(dirname "$common")"
  echo "install.sh: $root is a git worktree; the links would dangle once it is removed." >&2
  echo "install.sh: run it from the main clone instead: $main/hooks/install.sh" >&2
  exit 1
fi

dst_dir="$HOME/.claude/hooks"
say() { printf '%s\n' "$*"; }
run() { [ "$dry" = 1 ] || "$@"; }

backup_name() {
  local base="$1.bak-$(date +%Y-%m-%d)" name n=2
  name="$base"
  while [ -e "$name" ] || [ -L "$name" ]; do
    name="$base-$n"
    n=$((n + 1))
  done
  printf '%s' "$name"
}

run mkdir -p "$dst_dir"
for f in $FILES; do
  src="$src_dir/$f"
  dst="$dst_dir/$f"
  [ -f "$src" ] || { echo "install.sh: missing $src" >&2; exit 1; }
  if [ -L "$dst" ] && [ "$(readlink -f "$dst")" = "$src" ]; then
    say "ok       $dst"
    continue
  fi
  if [ -L "$dst" ] || [ -e "$dst" ]; then
    if [ ! -L "$dst" ] && [ -f "$dst" ] && cmp -s "$dst" "$src"; then
      say "replace  $dst (same content)"
      run rm -f -- "$dst"
    else
      bak="$(backup_name "$dst")"
      say "backup   $dst -> $bak"
      run mv -- "$dst" "$bak"
    fi
  fi
  say "link     $dst -> $src"
  run ln -s -- "$src" "$dst"
done

cat <<'EOF'

settings.json is not edited. Merge this into ~/.claude/settings.json by hand
(keep your own hooks; claude-wt-statusline.sh runs ccstatusline itself, so it
replaces an existing ccstatusline statusLine):

{
  "statusLine": {
    "type": "command",
    "command": "bash ~/.claude/hooks/claude-wt-statusline.sh",
    "padding": 0,
    "refreshInterval": 30
  },
  "hooks": {
    "SessionStart": [
      { "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/claude-wt-agent-state.sh session" },
        { "type": "command", "command": "bash ~/.claude/hooks/ccfzf-dump.sh" }
      ] }
    ],
    "UserPromptSubmit": [
      { "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh start" },
        { "type": "command", "command": "bash ~/.claude/hooks/claude-wt-statusline.sh --hook" }
      ] }
    ],
    "PreToolUse": [
      { "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh tool-start" }
      ] },
      { "matcher": "Skill", "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/claude-wt-statusline.sh --hook" }
      ] }
    ],
    "PostToolUse": [
      { "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh tool-done" } ] }
    ],
    "Notification": [
      { "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh attention" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh stop" } ] }
    ],
    "StopFailure": [
      { "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh fail" } ] }
    ],
    "PreCompact": [
      { "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh compact" } ] }
    ],
    "PostCompact": [
      { "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/wt-progress.sh compact" },
        { "type": "command", "command": "bash ~/.claude/hooks/claude-wt-agent-state.sh session" }
      ] }
    ]
  }
}
EOF
