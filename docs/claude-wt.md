# `claude-wt`: the agent's window tool

`claude-wt` is a command for a Claude Code session to read the picture of
sessions and windows and to act on the windows of its own sessions: raise one,
lay out a head's group, restore a layout snapshot, open a window for a session
that has none. It also carries the session commands that used to be separate
skill scripts (find, rename, close, spawn a child; mark a head, adopt
sessions). Its user is an agent, so every command prints one JSON line with
`--json` (the session commands always) and exits with a code that means
something.

```
claude-wt tree [--json]                  sessions, windows, heads and children, snapshots; marks your own
claude-wt waiting [--tree] [--json]      live sessions waiting for something, and how to clear it
claude-wt window focus <session>         raise the existing window of your session (never opens one)
claude-wt window layout <head>           lay out the windows of your head's group
claude-wt window place <session> --zone M:P   move your session's existing window into a FancyZones zone
claude-wt window icon <session> <name>|--clear    window icon from the icons folder of the window's machine
claude-wt window badge <session> <name>|--clear   badge on the taskbar button (beats project and head badges)
claude-wt window taskbar <session> hide|show|auto  hide or show the taskbar button of the window
claude-wt window icons [--machine HOST]  names usable with window icon/badge
claude-wt snapshot list [--json]         snapshots of trackers that have an http manager
claude-wt snapshot restore <id|last> [--sessions a,b]
claude-wt session open <session>         open a window for your session that has none
claude-wt session unread <session>       mark your session unseen for the picker (no window is raised)
claude-wt session seen <session>         mark your session seen: clears unread, puts the taskbar light out

claude-wt session find --session-id <id> [--timeout s] [--interval s] | --name <n> | --list [--cwd c]
claude-wt session rename --session-id <id> --to <name> | --cancel [--settings f]
claude-wt session close --session-id <id> [--force] [--kill] [--wait s]
claude-wt session spawn --task <slug> --prompt-file <f> [...]
claude-wt head mark
claude-wt head adopt [--release] <name|id>...
```

`<session>` is a sessionId, a unique prefix of it (6 characters or more) or a
name: the live name from `claude agents --json`, then the `title` of a closed
session in `ccfzf --state`. Two sessions with the same name are a refusal that
lists both ids, never the first match.

## Only your own sessions

The calling session is `CLAUDE_CODE_SESSION_ID`. Its own sessions are itself
and every descendant in `~/.ccfzf/children/<id>.json` (`headId` is the
parent), however deep: for a head that is the head, its children and the ones
it adopted; for an executor, only itself and its own children. Anything else —
a session started by hand, another head's group — is refused.

Outside Claude Code (no `CLAUDE_CODE_SESSION_ID`) every action is refused;
`tree`, `waiting` and `snapshot list` still work.

## What each command does

- **`tree`** reads `ccfzf --state`, the children records and the head marks
  (`~/.ccfzf/heads/`). Each session row: `id`, `title`, `live`, `cwd`,
  `window: {host, title} | null`, `own`, `head`, `parent`. Each snapshot:
  `id`, `created`, `host`, `sessions` (ids), `own` — true only when all its
  sessions are yours. Without `--json` it prints a short tree of live, own and
  windowed sessions.
- **`waiting`** lists live sessions that wait for something, read-only, for
  any session (not only your own). It reads only what the hooks and `ccfzf
  --state` already know, plus the PR state from `gh`. Kinds, in the order they
  are listed (oldest first within a kind):

  | `kind` | When | `text` | `hint` |
  |---|---|---|---|
  | `permission` | `agent.state` is `question` and `agent.question` is empty: a permission dialog (also plan approval — the hook keeps no text for `ExitPlanMode`) | `agent.message` | approve in its window |
  | `question` | `agent.question` is set: an open `AskUserQuestion`. Keyed on the field, not on the state — the hook sets it on PreToolUse, while the state is still `active` | the question | answer in its window |
  | `reply` | the turn is over (`idle`/`review`) and the summary reads as a question to the human: it contains `?`, «жду твоих/ок/ответа/решения…», «твоё решение», «дай ок», "let me know", "should I", "want me to"… | the summary | reply in its chat |
  | `pr` | the turn is over and `agent.pr_url` is a PR that is not `MERGED` or `CLOSED` | the summary | merge PR \<url\> |

  The summary is the start of the last answer (see the hook), so a question at
  its very end is not seen. "Claude is waiting for your input" is not a sign
  by itself: every session gets it a minute after its turn ends. A session that
  waits for someone other than the human cannot be told from this data. A
  working session (`active`) with a PR is not waiting; a session with both a
  question and an open PR is listed under the question, and its hint adds
  "then merge PR". Closed sessions are left out.

  Each entry: `id`, `short` (8 chars), `name`, `kind`, `since` (`agent.updated`:
  the hook keeps it across the idle notification and compaction, so it is
  when the wait began), `ageSec`, `text` (cut to 200), `hint`, `state`, `pr:
  {url, state, reason?}` when the session has one, `own`, `parent`. The answer
  also carries `live` (how many live sessions there are). `--tree` groups the
  entries by head → children, as `tree` does, and with `--json` adds `tree`:
  nested nodes, a head that does not wait itself is a node with `waiting:
  false`.

  PR state comes from `gh pr view <url> --json state`, one call per URL, all in
  parallel, each killed after `CLAUDE_WT_GH_TIMEOUT_MS` (8 s): the network can
  slow the command down but never hang it. Answers are cached in
  `$XDG_CACHE_HOME/claude-wt/prs.json` (`CLAUDE_WT_CACHE_DIR`): `MERGED` and
  `CLOSED` for good, `OPEN` for 10 minutes. Without `gh`, on a timeout or an
  error the state is `unknown` with a `reason`, the session stays in the list,
  and nothing is cached.
- **`window focus`** only raises a window that exists. A session with no
  window in `--state` is refused with code 2 before anything is sent — an
  older window manager would open a new terminal instead. The request is
  `POST /claude-wt/focus {id, raiseOnly: true}`; `foreground: false` in the
  answer is a refusal ("window did not come to front"). A manager that does not
  report `foreground` gets code 0, `foreground: null` and a warning on stderr.
  A manager answering `no window` (`--state` lagged behind) is code 2 as well.
  `--machine` or `--url` that lead anywhere but the window's own machine are
  refused: that machine has no such window, and an older manager would open one.
- **`window layout <head>`** sends one group — the head and its descendants
  with a window on the head's machine, in the order they were started — as
  `POST /claude-wt/place {mode: "group", groups: [[...]], selected: <head>}`.
  Fewer than two windows is refused without a request. Descendants left out
  are listed in `skipped: [{id, why}]`, `why` being `no window` or
  `other machine`.
- **`window place <session> --zone <monitor>:<position>`** moves the existing
  window of your session into a FancyZones zone of its machine (Windows: the
  numbering is FancyZones', the same as `claudeWt.headZones`). A `--zone` that
  is missing or is not two integers from 1 is refused with code 1 before
  anything else; a session with no window is code 2 before a request, like
  `focus` — it never opens a window. The request is
  `POST /claude-wt/place {mode: "zone", id, zone: {monitor, position}}`. The
  manager checks the zone against the FancyZones layout of a monitor that is
  connected now — it does not have to be one of `claudeWt.headZones` — and
  answers `{ok: true, placed, zone}`; `placed: 0` means the window already
  stood there. A zone outside the layout, a minimized or too narrow window is
  code 1 with the manager's reason; `no window` from the manager is code 2; a
  manager that predates the mode answers `bad payload`, which is code 1 with
  `manager does not know mode zone`. The window is not raised or focused and
  stays on its desktop. `session find` reports `monitor`/`zone`/`slot` by the
  main zones (`headZones`) only: a window in another zone shows up as the main
  zone it falls into (on nb `1:3` lies inside `1:2`: `zone: 2, slot: 2`), or
  `zone: null` when it falls into none. `--machine`/`--url` that lead anywhere but the window's machine
  are refused, as with `focus`.
- **`snapshot list`** lists snapshots of machines whose tracker has an http
  manager, newest first.
- **`snapshot restore <id|last>`** restores a snapshot whose sessions are all
  yours, or only the sessions named with `--sessions` (each yours and in the
  snapshot). `last` is the newest snapshot of your own. The manager answers at
  once and raises the windows over the next half minute, so success is
  `pending: true` — "accepted, outcome unknown".
- **`session open <session>`** opens a window for your session when it has
  none — it never opens a second one: a session with a window in `--state` is
  refused before anything is sent (`window exists, use window focus`), and so
  is a live session without a window — just spawned, its window not yet in
  `--state`, or a window lost with its ssh connection: opening it would start a
  second claude on the same session (`session is running without a window —
  wait for its window (just spawned) or use the picker's Reopen
  (disconnected)`). Only a closed session is opened. The
  request is `POST /claude-wt/session-open {id, action: "terminal", cwd}` to
  a tracker with an http manager that takes such requests (`openSession` in
  its tracker file; absent means yes, `false` means no): the machine of the
  caller's own window, or of its nearest ancestor's, else the freshest one.
  `--machine`/`--url` choose another one, but never a machine with
  `openSession: false`. The answer's `action` (`resume`, `restore`, …) comes
  back with code 0; `pending` — the same session is already opening — is code 0
  too, with `pending: true`. A timeout or a connection lost after sending is
  code 3, `outcome unknown — do not retry; check with tree in 30 s`: a repeat
  could open a second window. The timeout is 20 seconds unless
  `CLAUDE_WT_TIMEOUT_MS` is set.
- **`window icon <session> <name>`** and **`window badge <session> <name>`**
  set your session's window icon (`WM_SETICON`) and the badge in the corner of
  its taskbar button by name — a `.ico` file of the manager's icons folder
  (`claudeWt.windowIcons.dir`, case-insensitive, no subfolders, no paths;
  `window icons` lists the names). What is set this way beats everything
  automatic: the project icon, the `badges` rules and the head badge (Stas's
  decision, 2026-11-23); `--clear` drops it and the automatic one comes back.
  The manager keeps it per sessionId in its own file (`data/session-icons.json`),
  so it survives a tray restart and `--resume`, not a new session. `POST
  /claude-wt/window-icon {id, icon: name|null}` (`window-badge`, `badge`) answers
  `applied: true`, or `applied: false` with `reason` (`no window`, `icons
  disabled`, `no overlay support`, `no icon service`, `not applied (see tray
  log)`) — saved anyway, code 0, it lands by itself once the reason is gone.
  Refused (code 1) only for an unknown name (`unknown icon <name>; see
  claude-wt window icons`) or a manager without the icons folder. All machines
  of the session's windows get it, like `session unread`; no window is code 2
  unless `--machine`/`--url` names one.
- **`window taskbar <session> hide|show|auto`** hides or shows the taskbar
  button of your session's window. `show` keeps it visible even when the
  picker would hide it automatically (dimmed sessions); `hide` hides it and
  drops itself on the session's next turn and when its window closes; `auto`
  gives the decision back to the manager. A signal (a question, an unseen
  finished turn, the cache blink) keeps the button whatever the mode. `POST
  /claude-wt/window-taskbar {id, taskbar: 'hide'|'show'|null}` answers
  `applied: true`, or `applied: false` with `reason` (saved anyway, code 0);
  `auto` sends an explicit `null`, a missing key is refused. All machines of
  the session's windows get it; no window is code 2. Any other mode is code 1,
  `need hide, show or auto`. A manager without the route answers 404, shown as
  `manager has no /claude-wt/window-taskbar (old manager?)`.
- **`window icons`** asks the machine of your session's first window
  (`--machine`/`--url` — another one, and no caller session is needed); prints
  a name per line, `--json` — `{host, dir, names}`.
- **`session unread <session>`** and **`session seen <session>`** set the
  "seen" marks of your session at the trackers of **all** its windows — no
  window is raised and focus stays where it is, only marks (head's decision,
  2026-11-22). The picker has two "seen" marks and takes the later one: its own
  (`seen.json`) and the tracker's `focusedAt`; rolling back `focusedAt` alone
  never beat the picker's own mark. So `unread` (`POST
  /claude-wt/session-unread {id}`) makes the tracker roll back `focusedAt` and
  set `unreadAt` to now, and the picker shows the session unseen while
  `unreadAt` is newer than both marks — the next focus of the window clears it
  by itself. `seen` (`POST /claude-wt/session-seen {id}`) sets `focusedAt` to
  now, clears `unreadAt` and puts out the window's taskbar light. Every machine
  gets its own attempt whatever the others answered; the result lists them in
  `results`. A session without a window is code 2 `no window` — the mark lives
  in the window's tracker record. `unknown session` from a manager (it holds no
  slot for the session) is code 2 too, `no agent record yet` is code 1.
  `pending: true` — the manager handed the mark to its daemon, it lands on the
  next tick (a second). A manager that answers `ok` without `unreadAt`
  (`focusedAt` for `seen`) is an old one: code 0 with a warning. Both are
  idempotent, so code 3 is safe to retry.

## Session and head commands

`session find`, `session rename`, `session close`, `session spawn`, `head mark`
and `head adopt` moved here from the scripts of the `session-*` and
`head-session` skills. **They are compatible with those scripts**: the same
arguments (`--key value`, a flag without a value), the same JSON object with
the same keys, the same exit codes — only on one line instead of indented, and
printed always, without `--json`. The scripts become thin wrappers that call
`claude-wt` with their arguments, so every caller that reads `next`, `hint`,
`prevHead` or `sessionId` by name keeps working.

| Command | What it does | Exit codes |
|---|---|---|
| `session find` | a live session by id (waits up to `--timeout`, 45 s), by name, or the list; name, registry name history, window place (`windowHost`, `monitor`, `zone`, `slot`) | 0 found, 2 not found, 1 error |
| `session rename` | queues a name for the rename hook, which applies it on the target's next prompt; refuses a multi-line name, a taken one, or when the hook is not registered | 0 / 1 |
| `session close` | SIGTERM to a child of this head (busy only with `--force`, SIGKILL only with `--kill`); only from a head with a live mark, only its own children, only when the pid still matches the registry | 0 closed / 1 |
| `session spawn` | opens a child in a claude-wt window: `POST /claude-wt/session-new` to the freshest tracker with http; the child starts with a short intro, the task stays in `taskFile`. Never `bypassPermissions` for a child; `--fork` only with a `claude-wt-new` that supports it | 0, 1, 3 = outcome unknown — never resend, look the child up by the printed `sessionId` |
| `head mark` | marks this session a head (`~/.ccfzf/heads/<id>.json`) | 0 / 1 |
| `head adopt` | records live sessions as children of this head (`adopted: true`); `--release` only adopted ones | 0 nothing refused / 1 |

They need `CLAUDE_CODE_SESSION_ID` and, for `head mark` and `session spawn`,
`CLAUDE_PID` — both set by Claude Code in every session.

## Where the command goes

Each window names its machine (`window.host` in `--state`). The command goes to
that machine's window manager over http, at `http.host`:`http.port` from its
tracker file in `~/.ccfzf/windows/<host>.json`. A tracker file older than 15
minutes is refused as stale (the machine is asleep or its share dropped), and
so is one without `http`. `--machine HOST` picks another tracker, `--url URL`
skips trackers altogether. The timeout is 5 seconds (`CLAUDE_WT_TIMEOUT_MS`).

A manager refusal is an `ok: false` body with a `reason`, whatever the status
code; a non-2xx answer without one is a refusal with `HTTP <status>`. Success
is a 2xx answer with `ok: true` only — anything else on that port (a proxy
page, an empty body) is a refusal, not a silent success. A connection that
never happened is a refusal (`manager unreachable`); a connection lost after
the request was sent is code 3, since the manager may already be acting on it.
A snapshot that lists no sessions by id is refused: an empty list means
"every session of the snapshot" to the manager.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | done, or accepted when `pending: true` |
| 1 | refused; the reason is on stderr and in `error` with `--json` |
| 2 | not found: session, window, snapshot or machine |
| 3 | outcome unknown (timeout, or the connection dropped after the request was sent). `focus`, `layout`, `place`, `session unread`, `session seen`, `window icon`, `window badge` and `window taskbar` are safe to retry; `snapshot restore`, `session open` and `session spawn` are not — they could open a second window |

## Environment

Every path can be replaced, which is how the tests run without touching a
live machine: `CCFZF_BIN` (default `ccfzf`), `CLAUDE_BIN` (`claude`),
`CCFZF_WINDOWS_DIR` (`~/.ccfzf/windows`), `CCFZF_CHILDREN_DIR`
(`~/.ccfzf/children`), `CCFZF_HEADS_DIR` (`~/.ccfzf/heads`), and for
`waiting` `GH_BIN` (`gh`), `CLAUDE_WT_CACHE_DIR` (`$XDG_CACHE_HOME/claude-wt`)
and `CLAUDE_WT_GH_TIMEOUT_MS` (8000). The session
commands read `~/.claude/sessions` and `~/.ccfzf/prompts` under `HOME`, and
keep the overrides of their scripts: `SESSION_RENAME_DIR` (the rename queue)
and `SPAWN_TEST_HEAD_MODE` (tests only: the head's permission mode instead of
its transcript).

## Install

`hooks/install.sh` links `~/bin/claude-wt` to `<clone>/cli/claude-wt.mjs`
next to the hooks, by the same rules (idempotent, a different file is backed
up, refuses to run from a git worktree). It needs Node 18 or newer and has no
dependencies.

Tests: `node --test tests/cli/*.test.mjs`.
