#!/usr/bin/env bash
set -euo pipefail

event="${1:-}"
input="$(cat 2>/dev/null || true)"

# Каталог состояний сессий. Читается и с Windows — через сетевой диск,
# смонтированный на домашний каталог этой машины, — см. src/claude-wt в
# windows11-manager.
state_dir="$HOME/.claude/claude-wt"

# Как часто сводку можно пересчитывать посреди хода. Полторы минуты — компромисс
# между «строка живая» и «хвост транскрипта читается на каждый вызов
# инструмента»: на ходу их бывает по десятку в минуту.
SUMMARY_TTL=90

# Сколько ждать на stop, пока финальный ответ доедет до транскрипта.
#
# Замерено пробником: на момент запуска Stop-хука последнего ответа в файле нет
# — ни разу из восьми подряд, с запасом от 32 до 195 мс, — а появляется он
# примерно через 110 мс и завершения хука не ждёт. Записи Claude Code копит и
# сбрасывает пачкой, и хук успевает прочитать файл до сброса.
#
# Без ожидания сводка на stop вечно отстаёт на ответ. Чинилось это само, но
# позже и не всегда: следующим событием, обычно уведомлением о простое через
# минуту. Пока оно не пришло — а к сфокусированному окну оно не приходит вовсе,
# — сессия висит в review с позапрошлым ответом.
STOP_WAIT_MS=1500
STOP_POLL_MS=50

emit() {
  local seq="$1"
  jq -nc --arg seq "$seq" '{terminalSequence: $seq, suppressOutput: true}'
}

# Первая содержательная строка последнего ответа агента, без разметки.
# Проверено на десятке живых сессий: именно она работает как заголовок ответа —
# «Закоммитил — ea527f0, рабочее дерево чистое», «Дизайн, секция 1 из 5:
# границы ответственности». Заголовок `##` встречается лишь в каждом пятом
# ответе, последняя строка обычно оговорка, а вопрос в конце — редкость.
#
# Нижний порог в 12 знаков не случаен: половина ответов открывается голым
# «Готово.», и без порога сводка была бы бесполезна. С ним подтягивается
# следующая строка.
#
# Верхняя граница щедрая. Резать здесь незачем: у каждого, кто это показывает,
# своя ширина — в списке сессий её больше сотни знаков, на панели вдвое меньше,
# — и обрезают они сами, многоточием по месту. Двести знаков стоят только как
# страховка от ответа, начинающегося простынёй в один абзац.
summary_program=$(cat <<'JQ'
def strip_md:
  gsub("`"; "")
  | gsub("\\*\\*"; "")
  | gsub("\\[(?<t>[^\\]]+)\\]\\([^)]*\\)"; .t)
  | sub("^[[:space:]]*[#>]+[[:space:]]*"; "")
  | sub("^[[:space:]]*[-*+][[:space:]]+"; "")
  | sub("^[[:space:]]*[0-9]+\\.[[:space:]]+"; "")
  | gsub("[[:space:]]+"; " ")
  | sub("^ "; "")
  | sub(" $"; "");

split("\n")
| map(fromjson? // empty)
| map(select(.type == "assistant"))
| map((.message.content // []) | map(select(.type == "text") | .text) | join("\n"))
| map(select(length > 0))
| (last // "")
| split("\n") | map(strip_md) | map(select(length >= 3))
| . as $l
| (if ($l | length) == 0 then ""
   else ([range(1; ($l | length) + 1) | $l[0:.] | join(" ")]
         | map(select(length >= 12)) | first // ($l | join(" ")))
   end)
| if length == 0 then ""
  elif length <= 200 then .
  else ((.[0:200] | sub("[[:space:]]+[^[:space:]]*$"; "")) | sub("[[:space:][:punct:]]+$"; "")) + "…"
  end
JQ
)

# Последний запрос человека — одной строкой, без обёрток slash-команд и без
# ANSI. Сырой текст приходит в stdin на UserPromptSubmit (поле `prompt`); из
# транскрипта достаём только запасным путём: для сессий, поднятых до этой
# правки, и на stop, если в файле ещё пусто.
#
# tool_result в type=user — это не запрос, а ответ инструмента; их отбрасываем.
# Мусор вроде toolu_… /tmp/claude-… и Compacted — тоже: иначе в списке сессий
# вместо «что спросили» оказывается служебная строка.
prompt_program=$(cat <<'JQ'
def strip_md:
  gsub("`"; "")
  | gsub("\\*\\*"; "")
  | gsub("\\[(?<t>[^\\]]+)\\]\\([^)]*\\)"; .t)
  | sub("^[[:space:]]*[#>]+[[:space:]]*"; "")
  | sub("^[[:space:]]*[-*+][[:space:]]+"; "")
  | sub("^[[:space:]]*[0-9]+\\.[[:space:]]+"; "")
  | gsub("[[:space:]]+"; " ")
  | sub("^ "; "")
  | sub(" $"; "");

def unwrap:
  if test("<command-args>") then
    (capture("<command-args>(?<a>[\\s\\S]*?)</command-args>").a // .)
  elif test("<command-message>") then
    (capture("<command-message>(?<a>[\\s\\S]*?)</command-message>").a // .)
  else .
  end
  | gsub("<[^>]+>"; " ")
  | gsub("\u001b\\[[0-9;]*[A-Za-z]"; "")
  | gsub("[[:space:]]+"; " ")
  | sub("^ "; "")
  | sub(" $"; "");

def human_text:
  select(.type == "user" and .isMeta != true)
  | (.message.content // empty)
  | if type == "string" then .
    elif type == "array" then
      if any(.[]; type == "object" and .type == "tool_result") then empty
      else
        [ .[]
          | if type == "string" then .
            elif type == "object" and .type == "text" then (.text // "")
            else empty end
        ] | join("\n")
      end
    else empty end
  | select(type == "string" and length > 0);

split("\n")
| map(fromjson? // empty)
| map(human_text)
| map(unwrap | strip_md)
| map(select(length >= 3))
| map(select((test("toolu_")) or (test("/tmp/claude-"))
            or (test("Compacted \\(")) or (test("local-command-stdout"))
            or (test("This session is being continued")) | not))
| (last // "")
| if length == 0 then ""
  elif length <= 200 then .
  else ((.[0:200] | sub("[[:space:]]+[^[:space:]]*$"; "")) | sub("[[:space:][:punct:]]+$"; "")) + "…"
  end
JQ
)

# Тот же unwrap/обрезка, но для строки из stdin UserPromptSubmit — без разбора
# jsonl. Держим рядом с prompt_program, чтобы правила не разъехались.
normalize_prompt_program=$(cat <<'JQ'
def unwrap:
  if test("<command-args>") then
    (capture("<command-args>(?<a>[\\s\\S]*?)</command-args>").a // .)
  elif test("<command-message>") then
    (capture("<command-message>(?<a>[\\s\\S]*?)</command-message>").a // .)
  else .
  end
  | gsub("<[^>]+>"; " ")
  | gsub("\u001b\\[[0-9;]*[A-Za-z]"; "")
  | gsub("[[:space:]]+"; " ")
  | sub("^ "; "")
  | sub(" $"; "");

$p | unwrap
| if length == 0 then ""
  elif length <= 200 then .
  else ((.[0:200] | sub("[[:space:]]+[^[:space:]]*$"; "")) | sub("[[:space:][:punct:]]+$"; "")) + "…"
  end
JQ
)

# Ход закрыт: последний ответ агента в хвосте помечен `end_turn`.
#
# Промежуточный текст посреди хода — «Теперь tasks.md:», «Дневной лог:» —
# лежит в транскрипте такой же записью type=assistant с текстовым блоком, и
# отличается от финального ответа только этим полем: у него stop_reason
# "tool_use". Для сводки внутри хода это и нужно (см. SUMMARY_TTL), а на stop —
# ровно то, что нельзя показывать: ход ещё не кончился.
turn_closed_program=$(cat <<'JQ'
split("\n")
| map(fromjson? // empty)
| map(select(.type == "assistant"))
| map(select(((.message.content // []) | map(select(.type == "text") | .text)
              | join("")) != ""))
| (last // null)
| if . != null and (.message.stop_reason == "end_turn") then "1" else "0" end
JQ
)

# Тот же фильтр «только текст, который написал сам агент», что и у
# summary_program, — отдельно, для pr_from_transcript: ей не нужна ни
# markdown-зачистка, ни выбор последнего абзаца, только сырой текст ответов
# одним куском, чтобы поймать ссылку, если она разбита строками.
assistant_text_program=$(cat <<'JQ'
split("\n")
| map(fromjson? // empty)
| map(select(.type == "assistant"))
| map((.message.content // []) | map(select(.type == "text") | .text) | join("\n"))
| map(select(length > 0))
| join("\n")
JQ
)

# Транскрипты бывают на мегабайты, поэтому читается хвост. Окно растёт, а не
# берётся сразу большим: замерено, что у сессии со свежими служебными записями
# (deferred_tools_delta, agent_listing_delta и подобные весом в десятки
# килобайт) в первые 64 КБ не попадает ни одного ответа, и нужен следующий шаг.
# Обычно же хватает первого.
summarize_transcript() {
  local file="$1" size out win
  [ -n "$file" ] && [ -f "$file" ] || return 0
  size="$(stat -c %s "$file" 2>/dev/null || echo 0)"
  for win in 65536 262144 1048576; do
    if [ "$size" -gt "$win" ]; then
      out="$(tail -c "$win" "$file" 2>/dev/null | tail -n +2 \
        | jq -Rs -r "$summary_program" 2>/dev/null || true)"
    else
      out="$(jq -Rs -r "$summary_program" <"$file" 2>/dev/null || true)"
    fi
    [ -n "$out" ] && { printf '%s' "$out"; return 0; }
    [ "$size" -le "$win" ] && break
  done
  return 0
}

turn_closed() {
  local file="$1" size out
  [ -n "$file" ] && [ -f "$file" ] || return 1
  size="$(stat -c %s "$file" 2>/dev/null || echo 0)"
  if [ "$size" -gt 65536 ]; then
    out="$(tail -c 65536 "$file" 2>/dev/null | tail -n +2 \
      | jq -Rs -r "$turn_closed_program" 2>/dev/null || true)"
  else
    out="$(jq -Rs -r "$turn_closed_program" <"$file" 2>/dev/null || true)"
  fi
  [ "$out" = "1" ]
}

# То же, что summarize_transcript, но с ожиданием дописи финального ответа.
#
# Признак «ответ дописан» — метка end_turn у последнего ответа в хвосте
# (turn_closed). Сменившаяся сводка на эту роль не годится, и это стоило
# одной из сессий неверной строки: агент за ход успел написать «Дневной
# лог:» перед последней порцией инструментов, к моменту stop в файле лежал
# именно этот текст, от прошлой сводки он отличался — и цикл вышел на нём, не
# дождавшись «Задача закрыта». Отличие от прошлой сводки означает лишь «в
# транскрипте появился новый текст агента», а таких внутри одного хода бывает
# сколько угодно.
#
# Рост файла сам по себе тоже не признак: файл растёт и от служебных записей
# (например, attachment хука, отработавшего раньше нашего). Зато он — дешёвый
# сторож: пересчёт стоит чтения хвоста и запуска jq, поэтому дёргается он не на
# каждый шаг, а только после того, как размер сдвинулся. stat на шаг — копейки.
#
# Ожидание ограничено STOP_WAIT_MS. Метки может не быть вовсе — ход оборвали,
# упёрлись в предел токенов, — и тогда цикл отстаивает весь срок, после чего
# берётся последний текст как есть: он всё равно лучше позапрошлого.
summarize_after_turn() {
  local file="$1"
  local waited=0 size size_now closed=0
  [ -n "$file" ] && [ -f "$file" ] || return 0
  size="$(stat -c %s "$file" 2>/dev/null || echo 0)"
  if turn_closed "$file"; then closed=1; fi
  while [ "$closed" = 0 ] && [ "$waited" -lt "$STOP_WAIT_MS" ]; do
    sleep "$(printf '%d.%03d' "$((STOP_POLL_MS / 1000))" "$((STOP_POLL_MS % 1000))")"
    waited=$((waited + STOP_POLL_MS))
    size_now="$(stat -c %s "$file" 2>/dev/null || echo 0)"
    if [ "$size_now" != "$size" ]; then
      size="$size_now"
      if turn_closed "$file"; then closed=1; fi
    fi
  done
  summarize_transcript "$file"
}

normalize_prompt() {
  local raw="${1:-}"
  [ -n "$raw" ] || return 0
  jq -nr --arg p "$raw" "$normalize_prompt_program" 2>/dev/null || true
}

prompt_from_transcript() {
  local file="$1" size out win
  [ -n "$file" ] && [ -f "$file" ] || return 0
  size="$(stat -c %s "$file" 2>/dev/null || echo 0)"
  for win in 65536 262144 1048576; do
    if [ "$size" -gt "$win" ]; then
      out="$(tail -c "$win" "$file" 2>/dev/null | tail -n +2 \
        | jq -Rs -r "$prompt_program" 2>/dev/null || true)"
    else
      out="$(jq -Rs -r "$prompt_program" <"$file" 2>/dev/null || true)"
    fi
    [ -n "$out" ] && { printf '%s' "$out"; return 0; }
    [ "$size" -le "$win" ] && break
  done
  return 0
}

# Ссылка на PR из хвоста транскрипта. Ищется тем же чтением, что и сводка, и
# только там же: PR агент называет в ответе, а ответы — в хвосте. Берётся
# последняя, потому что сессия за день может открыть второй PR.
#
# Раньше grep гонялся по сырому хвосту .jsonl целиком — по результатам
# инструментов, по промптам человека, по содержимому прочитанных файлов, по
# выводу `gh`. Спека прямо требует: «PR берётся только из того, что агент сам
# назвал» — тот же принцип, по которому summary_program уже отбирает
# .type == "assistant" и только текстовые блоки. Последствие шире, чем неверная
# метка: найденная ссылка уходит в общую карту prs.json (pr_map_put ниже),
# откуда её подхватывают все будущие сессии на той же ветке — одна сессия,
# один раз выполнившая `gh pr list` или прочитавшая чужое ревью, навсегда
# прикрепляла бы чужой PR к своей ветке.
pr_from_transcript() {
  local file="$1" size
  [ -n "$file" ] && [ -f "$file" ] || return 0
  size="$(stat -c %s "$file" 2>/dev/null || echo 0)"
  if [ "$size" -gt 262144 ]; then
    tail -c 262144 "$file" 2>/dev/null | tail -n +2
  else
    cat "$file" 2>/dev/null
  fi | jq -Rs -r "$assistant_text_program" 2>/dev/null \
     | grep -oE 'https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/pull/[0-9]+' \
     | tail -n 1 || true
  return 0
}

# Текущая ветка проекта. PR принадлежит ветке, а не сессии: сессия
# перезапускается под новым id, ветка остаётся, и вторая сессия на той же ветке
# должна видеть тот же PR.
git_branch() {
  local dir="$1"
  [ -n "$dir" ] && [ -d "$dir" ] || return 0
  git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || true
}

# owner/repo проекта из origin, в нижнем регистре: с ним сравнивается
# owner/repo ссылки на PR (pr_repo ниже), чтобы не приписать сессии чужой PR,
# который она всего лишь упомянула в разговоре (обсуждала соседний проект,
# сослалась на чужое ревью) — см. pr_from_transcript.
#
# Форм origin две: git@github.com:owner/repo.git и
# https://github.com/owner/repo.git, «.git» на конце необязателен. Всё
# остальное — другой хост, локальный путь, origin отсутствует вовсе — пусто,
# и это не ошибка: «не знаем, чей репозиторий» ниже трактуется как «не наш»,
# а не как повод пропустить сравнение.
git_repo() {
  local dir="$1" url
  [ -n "$dir" ] && [ -d "$dir" ] || return 0
  url="$(git -C "$dir" remote get-url origin 2>/dev/null || true)"
  [ -n "$url" ] || return 0
  case "$url" in
    git@github.com:*) url="${url#git@github.com:}" ;;
    https://github.com/*) url="${url#https://github.com/}" ;;
    *) return 0 ;;
  esac
  url="${url%.git}"
  printf '%s' "$url" | tr 'A-Z' 'a-z' || true
  return 0
}

# owner/repo из ссылки на PR, тем же приведением к нижнему регистру, что и
# git_repo, — иначе сравнение в save_state ловило бы регистр вместо смысла
# (GitHub сам к нему нечувствителен, а человек в ответе может написать
# MyOrg там, где в origin myorg).
pr_repo() {
  local url="$1"
  [ -n "$url" ] || return 0
  printf '%s' "$url" \
    | sed -E 's#^https://github\.com/([^/]+)/([^/]+)/pull/[0-9]+$#\1/\2#' \
    | tr 'A-Z' 'a-z' || true
  return 0
}

# Карта «<cwd>#<branch> → PR». Общий файл на все сессии, запись атомарная, как у
# состояний. Потеря карты не страшна: следующий ответ с ссылкой её восстановит.
pr_map_get() {
  local key="$1" map="$state_dir/prs.json"
  [ -n "$key" ] && [ -f "$map" ] || return 0
  jq -r --arg k "$key" '.[$k].url // empty' "$map" 2>/dev/null || true
}

pr_map_put() {
  local key="$1" url="$2" now="$3" map="$state_dir/prs.json" tmp
  [ -n "$key" ] && [ -n "$url" ] || return 0
  tmp="$map.$$"
  if [ -f "$map" ]; then
    jq -c --arg k "$key" --arg u "$url" --argjson t "$now" \
      '.[$k] = {url: $u, updated: $t}' "$map" >"$tmp" 2>/dev/null || { rm -f "$tmp"; return 0; }
  else
    jq -nc --arg k "$key" --arg u "$url" --argjson t "$now" \
      '{($k): {url: $u, updated: $t}}' >"$tmp" 2>/dev/null || { rm -f "$tmp"; return 0; }
  fi
  mv -f "$tmp" "$map" 2>/dev/null || rm -f "$tmp" 2>/dev/null || true
  return 0
}

# Состояние сессии для windows11-manager: по файлу на сессию, запись атомарная
# (временный файл + mv). Общий файл рвали бы друг у друга хуки параллельных
# сессий, а на V: это ещё и сетевой доступ с чужой стороны.
#
# Сохранение никогда не должно ронять хук: терминальная последовательность
# важнее файла, поэтому каждый шаг заглушён, а функция всегда возвращает 0.
save_state() {
  local state="$1" message="${2:-}"
  local session_id transcript cwd target tmp now stamp
  now="$(date +%s)"
  # `updated` — это «агент сказал что-то новое»: с ним пикер и менеджер
  # сравнивают отметку взгляда (seenSinceUpdate, markHolds), и всякая запись
  # со свежим `now` делает сессию непросмотренной. Событию без новостей
  # (PostCompact, уведомление о простое) прежняя отметка передаётся через
  # KEEP_UPDATED. 21.11, сессии 06ad и 1eb4: окно посмотрели, набрали
  # /compact — и через минуту оба снова мигали непросмотренными.
  stamp="$now"
  case "${KEEP_UPDATED:-}" in '' | *[!0-9]*) ;; *) [ "$KEEP_UPDATED" -gt 0 ] && stamp="$KEEP_UPDATED" ;; esac

  session_id="$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null || true)"
  [ -n "$session_id" ] || return 0

  transcript="$(jq -r '.transcript_path // empty' <<<"$input" 2>/dev/null || true)"
  cwd="$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null || true)"

  mkdir -p "$state_dir" 2>/dev/null || return 0
  target="$state_dir/$session_id.state.json"
  tmp="$target.$$"

  # Сводка считается только там, где ответ уже дописан. На tool-start и
  # tool-done она бессмысленна (ход ещё идёт), а событий этих десятки на ход —
  # чтение хвоста транскрипта на каждое стоило бы дороже всего остального
  # хука вместе взятого. В остальное время прошлая сводка переносится как есть.
  #
  # Запрос человека — наоборот: на start он уже есть в stdin (поле `prompt`),
  # и его не стираем у работающей сессии — вопрос задан, пикер показывает его
  # под карточкой рядом с ответом. Из транскрипта достаём только если в stdin
  # пусто или файл ещё без поля (сессия стартовала до правки).
  local summary="" last_summary="" prompt="" summary_at=0 prev_at=0 rescan=0
  case "$event" in
    start)
      prompt="$(normalize_prompt "$(jq -r '.prompt // empty' <<<"$input" 2>/dev/null || true)")"
      [ -n "$prompt" ] || prompt="$(prompt_from_transcript "$transcript")"
      ;;
    stop)
      # Конец хода: финальный ответ ещё дописывается, поэтому с ожиданием.
      summary="$(summarize_after_turn "$transcript")"
      prompt="$(prompt_from_transcript "$transcript")"
      rescan=1
      ;;
    fail|attention)
      # fail — это StopFailure: прерывание или ошибка, финального ответа может
      # не быть вовсе, и ожидание там всякий раз выстаивалось бы впустую.
      # attention приходит через минуту после конца хода, там давно всё на месте.
      summary="$(summarize_transcript "$transcript")"
      prompt="$(prompt_from_transcript "$transcript")"
      rescan=1
      ;;
    tool-start | tool-done)
      # Ход бывает длиной в час: цикл /do, фоновый агент, ветка субагентов. Всё
      # это время stop не приходит, и сводка стоит на позапрошлом ответе, хотя
      # в транскрипт уже легли новые. Замерено на сессии shared: в списке
      # висела строка часовой давности, пока агент писал каждые полминуты.
      #
      # Отсюда срок годности вместо «только на stop». Событий этих десятки на
      # ход, но чтение хвоста — одно в SUMMARY_TTL на сессию, а не одно на
      # событие: ровно то, ради чего сводку сюда изначально не пускали.
      if [ -f "$target" ]; then
        prev_at="$(jq -r '.summaryAt // 0' "$target" 2>/dev/null || echo 0)"
        case "$prev_at" in '' | *[!0-9]*) prev_at=0 ;; esac
      fi
      summary_at="$prev_at"
      if [ "$((now - prev_at))" -ge "$SUMMARY_TTL" ]; then
        summary="$(summarize_transcript "$transcript")"
        # Отметка ставится за попытку, а не за удачу. Пустой хвост бывает — и
        # без этого он читался бы заново на каждое следующее событие, то есть
        # ровно там, где сроку годности и место.
        summary_at="$now"
        rescan=1
      fi
      ;;
  esac
  if [ -n "$summary" ]; then
    summary_at="$now"
  elif [ -f "$target" ]; then
    summary="$(jq -r '.lastSummary // .summary // empty' "$target" 2>/dev/null || true)"
  fi
  if [ -z "$prompt" ] && [ -f "$target" ]; then
    prompt="$(jq -r '.prompt // empty' "$target" 2>/dev/null || true)"
  fi

  # Вопрос, на котором сессия стоит. Берётся из аргументов AskUserQuestion на
  # PreToolUse: это самый ранний и самый дешёвый источник — stdin уже в руках,
  # транскрипт читать не нужно. Уведомление Notification для этого не годится:
  # приходит с общей фразой «Claude needs your permission» и о чём спросили не
  # сообщает.
  #
  # Источник этот не единственный. Прежде здесь стояло, что запись с вызовом
  # ложится в транскрипт не раньше ответа человека, — это неверно: 2026-08-21
  # снято живьём на ждущей сессии (2.1.234), последняя запись файла несла
  # tool_use AskUserQuestion с полным input — все вопросы, заголовки и
  # варианты. Отвеченные вызовы несут input во всех просмотренных транскриптах,
  # с 2.1.159; что запись есть и пока вызов открыт, держится на том одном
  # наблюдении. Этой дорогой — хвостом транскрипта — вопрос берёт ccfzf на
  # машинах без хуков (tail_facts).
  #
  # Без него строка ждущей сессии показывала прошлый ответ. У сессии shared это
  # была голая ссылка на PR: агент ответил ею на «какой адрес pr?», а следующим
  # ходом задал вопрос — и в списке осталась ссылка, хотя сессия стояла с
  # вопросом на экране.
  #
  # Живёт ровно между началом и концом вызова: на ответ (tool-done той же
  # команды), на новый промпт и на конец хода стирается. Иначе следующий запрос
  # разрешения — у него состояние такое же, `question`, — показал бы вопрос,
  # на который давно ответили.
  local question=""
  local tool_name=""
  tool_name="$(jq -r '.tool_name // empty' <<<"$input" 2>/dev/null || true)"
  case "$event" in
    start | stop | fail) ;;
    tool-start)
      if [ "$tool_name" = "AskUserQuestion" ]; then
        question="$(jq -r '[.tool_input.questions[]?.question // empty] | first // empty' \
          <<<"$input" 2>/dev/null || true)"
        question="$(normalize_prompt "$question")"
      elif [ -f "$target" ]; then
        question="$(jq -r '.question // empty' "$target" 2>/dev/null || true)"
      fi
      ;;
    tool-done)
      if [ "$tool_name" != "AskUserQuestion" ] && [ -f "$target" ]; then
        question="$(jq -r '.question // empty' "$target" 2>/dev/null || true)"
      fi
      ;;
    *)
      if [ -f "$target" ]; then
        question="$(jq -r '.question // empty' "$target" 2>/dev/null || true)"
      fi
      ;;
  esac

  # Начало текущего хода. Двух других отметок для этого не хватает: `updated`
  # сдвигается каждым tool-*, и у работающей сессии возраст всегда «now», а
  # `started` из meta.json — возраст всей сессии, там и час, и сутки. Вопрос
  # «сколько уже работает эта команда» не отвечал никто.
  #
  # Ставится на start (UserPromptSubmit) и дальше только переносится: ход
  # кончается, но отметка остаётся жить до следующего промпта — по ней видно и
  # то, сколько последний ход занял. У сессий, поднятых до этой правки, поля
  # нет, там ноль, и показывающий откатывается на прежний возраст.
  #
  # UserPromptSubmit приходит не только от человека: отчёт субагента, доставшийся
  # простаивающей сессии, начинает новый ход и потому идёт тем же событием.
  # Замерено 2026-08-16 на сессии a973: человек спросил в 22:39, субагенты
  # отчитывались до 23:19, и отметка переезжала на каждый отчёт. Признак —
  # пустой `prompt` в stdin: у набранного человеком текст там есть всегда, а
  # у вставки поле пустое (потому же `prompt` ниже и берётся из транскрипта).
  # На всякий случай проверяется и сам текст: обёртка уведомления узнаётся
  # сразу, и на ней отметка тоже стоит на месте.
  local turn_at=0 raw_prompt=""
  raw_prompt="$(jq -r '.prompt // empty' <<<"$input" 2>/dev/null || true)"
  case "$raw_prompt" in '<task-notification>'*) raw_prompt="" ;; esac
  if [ "$event" = "start" ] && [ -n "$raw_prompt" ]; then
    turn_at="$now"
  elif [ -f "$target" ]; then
    turn_at="$(jq -r '.turnAt // 0' "$target" 2>/dev/null || echo 0)"
    case "$turn_at" in '' | *[!0-9]*) turn_at=0 ;; esac
  fi

  # Ветка и PR стоят столько же, сколько чтение хвоста, поэтому считаются ровно
  # там, где хвост уже прочитан. В остальное время переносятся из прошлой
  # записи — как сводка.
  local branch="" pr_url="" found_pr="" repo="" found_repo=""
  if [ "$rescan" = "1" ]; then
    branch="$(git_branch "$cwd")"
    repo="$(git_repo "$cwd")"
    found_pr="$(pr_from_transcript "$transcript")"
    if [ -n "$found_pr" ]; then
      # Ссылка идёт в карту и в состояние только если её репозиторий и есть
      # репозиторий проекта. Пустой $repo (origin не github или его вовсе
      # нет) тоже отбрасывает ссылку молча — «не знаем» здесь не «наш».
      found_repo="$(pr_repo "$found_pr")"
      [ -n "$repo" ] && [ "$found_repo" = "$repo" ] || found_pr=""
    fi
    if [ -n "$found_pr" ] && [ -n "$branch" ]; then
      pr_map_put "$cwd#$branch" "$found_pr" "$now"
    fi
    pr_url="$found_pr"
    [ -n "$pr_url" ] || pr_url="$(pr_map_get "$cwd#$branch")"
  elif [ -f "$target" ]; then
    branch="$(jq -r '.branch // empty' "$target" 2>/dev/null || true)"
    pr_url="$(jq -r '.pr_url // empty' "$target" 2>/dev/null || true)"
  fi

  # Полей два, потому что вопросов тоже два.
  #
  # `summary` отвечает «что сессия говорит сейчас», и у работающей сессии
  # честный ответ — ничего: последний дописанный ответ относится к прошлому
  # ходу, а показывать его как текущий значит врать. `lastSummary` отвечает
  # «на чём она остановилась в прошлый раз» и не стирается никогда.
  last_summary="$summary"
  [ "$state" = "active" ] && summary=""

  # Деньги и контекст приходят не в хук, а в статуслайн: в stdin хука таких
  # полей нет вовсе. Их перехватывает claude-wt-statusline.sh и кладёт рядом,
  # отсюда они переезжают в состояние — чтобы у читателя на Windows остался
  # один файл на сессию, а не два.
  local cost_usd=0 context_pct=0 status_file="$state_dir/$session_id.status.json"
  if [ -f "$status_file" ]; then
    cost_usd="$(jq -r '.costUsd // 0' "$status_file" 2>/dev/null || echo 0)"
    context_pct="$(jq -r '.contextPct // 0' "$status_file" 2>/dev/null || echo 0)"
  fi
  # --argjson роняет всю запись на нечисловом значении, а состояние важнее
  # цифр: сомнительное превращается в ноль, то есть «данных нет».
  case "$cost_usd" in '' | *[!0-9]*) cost_usd=0 ;; esac
  case "$context_pct" in '' | *[!0-9]*) context_pct=0 ;; esac

  if jq -nc \
      --arg id "$session_id" \
      --arg state "$state" \
      --arg event "$event" \
      --arg message "$message" \
      --arg summary "$summary" \
      --arg last_summary "$last_summary" \
      --arg prompt "$prompt" \
      --arg question "$question" \
      --arg branch "$branch" \
      --arg pr_url "$pr_url" \
      --arg transcript "$transcript" \
      --arg cwd "$cwd" \
      --argjson cost_usd "$cost_usd" \
      --argjson context_pct "$context_pct" \
      --argjson summary_at "$summary_at" \
      --argjson turn_at "$turn_at" \
      --argjson updated "$stamp" \
      '{sessionId: $id, state: $state, event: $event, message: $message,
        summary: $summary, lastSummary: $last_summary, summaryAt: $summary_at,
        turnAt: $turn_at,
        prompt: $prompt, question: $question, branch: $branch, pr_url: $pr_url,
        costUsd: $cost_usd, contextPct: $context_pct,
        transcript: $transcript, cwd: $cwd, updated: $updated}' \
      >"$tmp" 2>/dev/null; then
    mv -f "$tmp" "$target" 2>/dev/null || rm -f "$tmp" 2>/dev/null || true
  else
    rm -f "$tmp" 2>/dev/null || true
  fi
  return 0
}

# Файлы закрытых сессий никто не удаляет, а каталог читается целиком. Чистка
# висит на start: событие редкое (одно на промпт), в отличие от tool-*.
prune_state() {
  [ -d "$state_dir" ] || return 0
  # Карта «ветка → PR» из чистки исключена: это не состояние закрытой сессии, а
  # общий кэш, и его возраст ни о чём не говорит. Ветка, чей PR не называли
  # неделю, теряла бы метку молча, и вернуть её было бы некому: агент второй раз
  # ту же ссылку не произносит.
  #
  # Считается сессиями, а не файлами, и это не аккуратности ради. У сессии их
  # три, и пишут их разные хуки с разной частотой: state.json — этот, на
  # событиях агента; status.json — статуслайн, по таймеру, пока открыт
  # терминал. Открытая и молчащая неделю сессия теряла из-за этого ровно
  # state.json: он старше недели, а status.json чистку переживал, потому что
  # его всё это время переписывали. Дальше ccfzf (agent_of) на осиротевшем
  # status.json откатывался на его отметку времени и выдавал пульс статуслайна
  # за активность агента — сессия, молчащая с 1 августа, 13-го стояла первой в
  # сортировке `recent` с возрастом в секунду.
  #
  # Поэтому уходит вся тройка сразу или не уходит ничего: сессия жива, пока
  # хоть один её файл моложе недели. `! -mtime +7` — точное дополнение к
  # `-mtime +7`, а не `-mtime -7`: между ними сутки, за которые файлы не
  # попадают ни туда, ни сюда, и тройка снова разъехалась бы на день.
  local alive
  alive="$(find "$state_dir" -maxdepth 1 -name '*.json' ! -name 'prs.json' \
             ! -mtime +7 2>/dev/null | sed -e 's#.*/##' -e 's#\.[^.]*\.json$##' \
           | sort -u)" || true
  find "$state_dir" -maxdepth 1 -name '*.json' ! -name 'prs.json' \
       -mtime +7 2>/dev/null | while IFS= read -r f; do
    sid="${f##*/}"
    sid="${sid%.*.json}"
    printf '%s\n' "$alive" | grep -qxF -- "$sid" || rm -f -- "$f" 2>/dev/null || true
  done
  return 0
}

case "$event" in
  compact)
    # Автосжатие приходит и после конца хода: PreCompact/PostCompact без
    # следующего stop оставляли сессию зелёной (active) навсегда — 16.11, на
    # дочерней сессии. Поэтому законченное состояние (review/idle/question)
    # запоминается на PreCompact и возвращается на PostCompact.
    hook="$(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null || true)"
    sid="$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null || true)"
    #
    # Вместе с состоянием запоминается и `updated`: сжатие — не новость, и
    # возвращённое состояние не должно выглядеть непросмотренным (см.
    # KEEP_UPDATED в save_state). Ручное (`trigger: manual`, набранный
    # /compact) сверх того кладёт законченную сессию в idle: сжимают то, с
    # чем уже разобрались, — звать после этого нечем. Вопрос остаётся
    # вопросом: агент на нём по-прежнему стоит.
    #
    # Файл — «состояние updated trigger» одной строкой; прежний формат (одно
    # слово) читается тоже: остальные поля тогда пустые.
    keep="$state_dir/$sid.precompact"
    if [ "$hook" = "PreCompact" ] && [ -n "$sid" ]; then
      prev="$(jq -r '"\(.state // "") \(.updated // 0)"' "$state_dir/$sid.state.json" 2>/dev/null || true)"
      trigger="$(jq -r '.trigger // empty' <<<"$input" 2>/dev/null || true)"
      case "${prev%% *}" in
        review|idle|question) printf '%s %s' "$prev" "$trigger" >"$keep" 2>/dev/null || true ;;
        *) rm -f -- "$keep" 2>/dev/null || true ;;
      esac
    elif [ "$hook" = "PostCompact" ] && [ -n "$sid" ] && [ -s "$keep" ]; then
      read -r prev prev_updated trigger <"$keep" 2>/dev/null || true
      rm -f -- "$keep" 2>/dev/null || true
      if [ "$trigger" = "manual" ] && [ "$prev" = "review" ]; then prev=idle; fi
      KEEP_UPDATED="${prev_updated:-}" save_state "$prev" || true
      if [ "$prev" = "question" ]; then emit "$(printf '\033]9;4;4;22\007')"
      else emit "$(printf '\033]9;4;0;0\007')"; fi
      exit 0
    fi
    save_state active || true
    emit "$(printf '\033]9;4;1;100\007')"
    ;;

  start|tool-start|tool-done)
    # Во время работы всегда показываем залитый на 100% бар (state 1 = normal).
    # compact — это Pre/PostCompact: сжатие идёт посреди хода, сессия занята,
    # и без этого события хук свалился бы в `unknown` с серым баром.
    save_state active || true
    if [ "$event" = "start" ]; then prune_state || true; fi
    emit "$(printf '\033]9;4;1;100\007')"
    ;;

  attention)
    # Хук Notification приходит как на реальные запросы (разрешение/вопрос),
    # так и на простой («Claude is waiting for your input») через ~60с после
    # завершения работы. Во втором случае жёлтый не нужен — статус обычный.
    msg="$(jq -r '.message // empty' <<<"$input" 2>/dev/null || true)"
    case "$msg" in
      *"waiting for your input"*)
        # Простой. Считается «проверено»: других сигналов о том, что человек
        # посмотрел на результат, у хуков нет, а это уведомление приходит уже
        # после того, как окно постояло законченным.
        #
        # Новостей в нём нет, поэтому `updated` остаётся от прошлой записи:
        # иначе взгляд на окно между концом хода и уведомлением терялся бы, и
        # сессия снова выглядела бы непросмотренной. Уже idle — не трогаем
        # запись вовсе: там нечего менять, а event `compact` после ручного
        # /compact превратился бы в `attention` и снова позвал бы.
        sid="$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null || true)"
        prev="$(jq -r '"\(.state // "") \(.updated // 0)"' "$state_dir/$sid.state.json" 2>/dev/null || true)"
        if [ "${prev%% *}" = "idle" ]; then
          emit "$(printf '\033]9;4;0;0\007')"
          exit 0
        fi
        keep_at=""
        [ "${prev%% *}" = "review" ] && keep_at="${prev#* }"
        KEEP_UPDATED="$keep_at" save_state idle "$msg" || true
        emit "$(printf '\033]9;4;0;0\007')"          # простой → обычный
        ;;
      *)
        save_state question "$msg" || true
        emit "$(printf '\033]9;4;4;22\007\007')"     # внимание → жёлтый + bell
        ;;
    esac
    ;;

  stop)
    # Работа закончена, результат ещё никто не смотрел.
    save_state review || true
    emit "$(printf '\033]9;4;0;0\007')"
    ;;

  fail)
    # Звоним в bell для внимания, но прогресс-бар сразу гасим,
    # чтобы статус не «висел» после прерывания/ошибки.
    # Для списка сессий это тот же «ждёт проверки»: агент встал, к нему надо
    # вернуться — тем более после ошибки.
    save_state review || true
    emit "$(printf '\007\033]9;4;0;0\007')"
    ;;

  *)
    save_state unknown || true
    emit "$(printf '\033]9;4;3;0\007')"
    ;;
esac
