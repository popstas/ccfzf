#!/usr/bin/env bash
# Стоимость сессии и заполненность контекста для windows11-manager / claude-wt.
#
# Хуку такого не дают: в его stdin есть session_id, transcript_path, cwd,
# permission_mode, effort — и ни одного поля про токены, деньги или время.
# Статуслайну дают всё: context_window (включая размер окна) и cost приходят
# готовыми. Размер окна принципиален — из транскрипта его не вычислить, а без
# него проценты не посчитать: у одной сессии окно 200k, у соседней миллион.
#
# Поэтому вход статуслайна перехватывается здесь и кладётся рядом с состояниями
# сессий, а wt-progress.sh на своём следующем событии складывает эти числа в
# <id>.state.json. Читателю на Windows по-прежнему один файл на сессию, и
# лишних сетевых чтений не появилось.
#
# Регистрируется в settings.json как statusLine.command вместо самого
# ccstatusline — тот запускается отсюда и получает нетронутый вход.

set -uo pipefail

input="$(cat 2>/dev/null || true)"
state_dir="$HOME/.claude/claude-wt"

# Статуслайн вызывается на каждое событие сессии и вдобавок по таймеру
# refreshInterval — много чаще, чем меняется целый процент или целый доллар.
MIN_AGE=5

save_status() {
  command -v jq >/dev/null 2>&1 || return 0

  local id target tmp prev now
  id="$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null || true)"
  [ -n "$id" ] || return 0

  mkdir -p "$state_dir" 2>/dev/null || return 0
  target="$state_dir/$id.status.json"

  now="$(date +%s)"
  prev="$(stat -c %Y "$target" 2>/dev/null || echo 0)"
  [ $((now - prev)) -ge "$MIN_AGE" ] || return 0

  tmp="$target.$$"
  # Округление здесь, а не у того, кто показывает: доллары нужны с точностью до
  # доллара, проценты — до процента, и число, которое дёргается на каждую
  # копейку, заставляло бы панель перерисовывать строку без всякого повода.
  #
  # Знаменатель — context_window_size из того же объекта, а не константа: 200k
  # и 1M дают на одних и тех же токенах впятеро разный процент.
  if jq -c --argjson now "$now" '
      (.context_window // {}) as $c
      | (($c.context_window_size // 0)) as $size
      | {
          sessionId: (.session_id // ""),
          costUsd: (((.cost // {}).total_cost_usd // 0) | round),
          contextPct: (if $size > 0
                       then ((($c.total_input_tokens // 0) + ($c.total_output_tokens // 0))
                             / $size * 100 | round)
                       else 0 end),
          updated: $now
        }' <<<"$input" >"$tmp" 2>/dev/null; then
    # Атомарно, как и всё остальное в этом каталоге: читатель на стороне
    # Windows никогда не увидит половину записи.
    mv -f "$tmp" "$target" 2>/dev/null || rm -f "$tmp" 2>/dev/null || true
  else
    rm -f "$tmp" 2>/dev/null || true
  fi
  return 0
}

# Тот же скрипт висит на UserPromptSubmit и PreToolUse:Skill. Перехвата
# состояния там нет: во входе хука нет ни cost, ни context_window, и save_status
# записал бы нули поверх чисел статуслайна — а wt-progress.sh следом перенёс бы
# их в state.json. Рендерить статуслайн в этих вызовах тоже вредно дважды:
# показывать его некому, а stdout хука уходит в контекст модели вместе с ANSI-
# кодами (~500 символов на каждый промпт и каждый вызов скилла).
#
# Но передать вход дальше всё же надо: виджет "skills" в ccstatusline читает не
# stdin статуслайна, а свой кэш ~/.cache/ccstatusline/skills/skills-<id>.jsonl,
# который пишется только из `ccstatusline --hook`. Раз hook-команды в
# settings.json (в том числе с _tag: ccstatusline-managed) указывают сюда, без
# проброса кэш не пополняется и список скиллов всегда пуст.
if [ "${1:-}" = "--hook" ]; then
  if command -v ccstatusline >/dev/null 2>&1; then
    printf '%s' "$input" | ccstatusline --hook >/dev/null 2>&1 || true
  fi
  exit 0
fi

save_status || true

# Статуслайн важнее перехвата: что бы ни случилось выше, вход уходит дальше
# нетронутым, а сюда возвращается его вывод как есть.
#
# Прямой вызов, а не `npx -y ccstatusline@latest`: спецификатор latest обязан
# резолвиться в реестре заново на каждый запуск, и это давало ~1.7 с на вызов —
# при том, что дёргается statusLine по refreshInterval. npx оставлен запасным
# путём для машины, где пакет не стоит глобально.
if command -v ccstatusline >/dev/null 2>&1; then
  printf '%s' "$input" | ccstatusline
else
  printf '%s' "$input" | npx -y ccstatusline@latest
fi
