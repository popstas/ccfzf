# ccfzf

Pick a Claude Code project and session with `fzf`, then resume it — or start something else in that directory.

> The recommended interface is [ccfzf-picker](https://github.com/popstas/ccfzf-picker).

Two pickers. First the projects, sorted by how recently you touched them:

```
★ webapp                14   1●  12m  ~/projects/js/webapp
★ scraper               23       3d   ~/projects/python/scraper
  sandbox               46       9d   ~/tmp/sandbox
★ blog                  -             ~/projects/site/blog
```

Then the sessions of the one you picked, newest first:

```
[+] new session
[>] codex     ctrl-s
[$] shell     ctrl-d
 ●  12m  Add a session picker · I need a command that takes a project path…
    3d   Fix flaky retry test · the CI job fails once every few runs, look into it
```

`★` marks a project from [fzf-marks](https://github.com/urbainvaes/fzf-marks). `●` marks a session that is running right now. The cyan part of a session row is its title (`/rename` or the generated one), the dim part is the first prompt; the preview pane below shows both in full.

## Why

The obvious way to build this is to shell out to a session lister and format its output. That turned out to cost 2–3 seconds per launch, because listing sessions that way reads every `~/.claude/projects/**/*.jsonl` in full — 757 MB of history in my case.

`ccfzf` reads only what it needs: `cwd` is on the first line of a session file, the title and the latest activity are in the last 256 KB, and the first prompt is found near the start under a size cap. Running sessions are detected through `/proc` rather than `lsof`.

| | |
|---|---|
| project list (first thing you see) | **0.05 s** |
| detecting running sessions | 0.006 s |
| session list, 117 files / 101 MB | 0.24 s |

There is no cache to go stale, and no truncation window — the list is always complete.

## Install

```sh
git clone https://github.com/popstas/ccfzf.git
ln -s "$PWD/ccfzf/ccfzf" ~/bin/ccfzf   # anywhere on your PATH
```

### zsh key binding

[`ccfzf.zsh`](ccfzf.zsh) defines two widgets and binds `ctrl-t` to the first one:

```sh
source /path/to/ccfzf/ccfzf.zsh
```

| Widget | What it does | Bound to |
|---|---|---|
| `ccfzf-kiosk-widget` | runs `ccfzf --kiosk` — you stay inside ccfzf until you `esc` out | `$CCFZF_KEY`, default `ctrl-t` |
| `ccfzf-widget` | runs `ccfzf --print` — the real command lands in your shell history and the shell stays in the project directory afterwards | `$CCFZF_PRINT_KEY`, unbound by default |

Set `CCFZF_KEY` before sourcing to move the binding, or bind `ccfzf-widget` to `ctrl-t` instead if you prefer the second behaviour.

### zsh completion

[`_ccfzf`](_ccfzf) completes the flags, the marks from `~/.fzf-marks` and directories. Put the repository on your `fpath` **before** `compinit` runs:

```sh
fpath=(/path/to/ccfzf $fpath)
autoload -Uz compinit && compinit
```

If something else already ran `compinit` for you — oh-my-zsh, antigen, a framework — register it afterwards instead:

```sh
fpath=(/path/to/ccfzf $fpath)
autoload -Uz _ccfzf && compdef _ccfzf ccfzf
```

## Usage

```
ccfzf                       pick a project, then a session
ccfzf webapp                go straight to a project (mark, path or substring)
ccfzf ~/projects/js/webapp  the same, by path
ccfzf webapp --model opus   trailing arguments are passed on to claude
ccfzf --kiosk               run everything inside, return to the list on exit
ccfzf --print               print the command instead of running it
ccfzf --session <id>        go straight into a session by id, no picker
ccfzf --limit <n>           how many newest sessions to look at at all (100)
```

`--session` is for scripts, not people: a missing or unknown id is a hard error (message on stderr, exit 1) rather than a fall back to the picker, which would hang with nobody at the keyboard. It composes with `--kiosk` (runs the session, then lands on that project's session list) and with `--print` (prints `cd <dir> && claude --resume <id>` instead of running it).

In the session list:

| Key | Action |
|---|---|
| `enter` | resume the session (or run the highlighted entry) |
| `ctrl-s` / `ctrl-f` / `ctrl-g` | project commands 1 / 2 / 3 |
| `ctrl-d` | drop into a shell there |
| `esc` | back to the project list, cursor on the project you left |

Hotkeys act on the directory of the highlighted row, so `ctrl-d` on a session started in a subdirectory takes you to that subdirectory.

Note that `--expect` takes these keys away from fzf itself: `ctrl-f` no longer moves the cursor in the query and `ctrl-g` no longer aborts (`esc` still does).

## Kiosk mode

```sh
ccfzf --kiosk          # or just press ctrl-t
```

Normally `ccfzf` replaces itself with whatever you picked and is gone. In kiosk mode it stays: the command runs as a child, and when it exits you are back in the session list of the same project with the cursor on the row you came out of. So a session you resume, quit, and want back is two keystrokes away, and `ctrl-d` into a shell followed by `exit` returns to the list rather than to your prompt.

Start a new session and the cursor lands on the session that was actually created, not on `[+] new session`. New sessions are started with `claude -n <basename>` so the terminal title and ccfzf row match the project folder immediately. The index is rebuilt on the way back, so titles, ages and running markers are current — that costs about as much as one fzf redraw.

`esc` goes back to the project list, `esc` again quits. Not compatible with `--print`, which exists precisely to hand a command back to the shell.

While a picker is on screen it names the terminal `ccfzf project select` / `ccfzf session select`. In kiosk mode you come back to the list from a session that has renamed the window after itself, and a window still wearing that name was indistinguishable from the live session; the picker now takes the title back and whatever you launch next sets its own.

Picked commands run in an interactive shell (`$SHELL -ic 'cd <dir> && <cmd>'`), so your rc file is read and the `cd` fires its `chpwd` hooks for the project directory. Without that a command started from ccfzf would inherit the environment of the shell you pressed the key in — a per-directory variable would still name the project you came from. The cost is one rc load per launch; `--print` needs none of this, because there the `cd` happens in your own shell.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CCFZF_PROJECT_COMMAND` | `codex` | command 1, run in the project directory |
| `CCFZF_PROJECT_COMMAND2` | — | command 2 |
| `CCFZF_PROJECT_COMMAND3` | — | command 3 |
| `CCFZF_PROJECT_COMMAND_NAME[2,3]` | first word of the command | label shown in the list |
| `CCFZF_CLAUDE_COMMAND` | `claude` | the claude binary itself — a wrapper or extra flags |
| `CCFZF_SESSIONS_FILE` | `~/.ccfzf.sessions.json` | dump for a window tracker on another machine, `--limit` newest sessions; empty turns it off |
| `CCFZF_FACTS_FILE` | `$XDG_CACHE_HOME/ccfzf/facts.json` | memo of per-transcript facts, so a fresh `--state` process does not recompute them; empty turns it off |
| `CCFZF_PROJECTS_FILE` | `~/.ccfzf.projects.json` | dump of the project list; empty turns it off |
| `CCFZF_WINDOWS_FILE` | `~/.ccfzf.sessions.claude-wt.json` | file *written by someone else*, read by `--state` and `--dump`; empty turns it off |
| `FZF_MARKS_FILE` | `~/.fzf-marks` | where the marks live |

An empty command drops both its list entry and its hotkey. A command may carry arguments (`CCFZF_PROJECT_COMMAND2="codex --yolo"`). Every command value is a shell fragment, so quoting works as usual (`CCFZF_CLAUDE_COMMAND='"/opt/my tools/claude"'`).

Border, height and layout are left to your `FZF_DEFAULT_OPTS`.

## The dumps

Every run also writes down what it saw, so whatever else you script around Claude Code can read it without paying for its own scan. Two files, both replaced on every launch (and again on the way back from a kiosk command, where the data has changed underneath). `ccfzf --dump` rewrites the same files and exits — for callers that need a fresh dump without opening the picker.

`CCFZF_SESSIONS_FILE` — the newest sessions across **all** projects (`--limit`, 100 by default), newest first, plus every live session and every session with a window open, so the file always holds whoever a window on screen might belong to. The reader is a window tracker on another machine, and the fields are the ones it needs — nothing else:

```json
{
 "generated": 1785460168.138,
 "total": 860,
 "shown": 104,
 "sessions": [
  {
   "id": "c5bf2507-7381-4aa9-979d-b66242f39d7f",
   "title": "Add a session picker",
   "cwd": "/home/you/projects/js/webapp",
   "live": true,
   "mtime": 1785460166.26,
   "kind": "interactive",
   "parent": "",
   "activityAt": 1785460166
  }
 ]
}
```

`total` is how many sessions exist, `shown` how many made it into the file. `activityAt` is when this session's hook last wrote, in epoch seconds, or 0 if it never did — the reader ranks same-titled candidates by it, and computing it here saves it a network `stat` per candidate. `kind` is `interactive` or `background`, and `parent` names the session a background agent was forked from.

`ccfzf --state` is the other output and a richer one: it prints everything above plus `file`, `projects`, `gist`, `doing`, `age`, `frozen`, `pid`, `tty`, `tmux`, `agent` and `window` on stdout, for a picker on another machine. The dump is not a subset by accident — the two have different readers.

### The facts memo

`CCFZF_FACTS_FILE` caches what the last run learned about each transcript — its title, first prompt and size — keyed by path, so the next `--state` or `--dump` does not reread every transcript's tail just to get `title` back. `--dump` never needs the first prompt, so its record carries no `gist`/`gistDone` keys at all — not "looked and found nothing" but "did not look" — and a later `--state`, even when the transcript's `mtime` still matches, sees the missing keys and goes looking anyway rather than trusting a half-empty record. A record is recomputed once its transcript's `mtime` moves; the cached `gist` is separately dropped whenever the transcript's `size` has shrunk since it was last measured, the signature of a transcript replaced outright — restored from a backup, compacted — rather than appended to, which an `mtime` bump alone would not catch (a stable `gist` otherwise survives any number of appends unchanged). The stored `gist` is capped at 200 characters, matching the field it feeds in `--state`. The file carries a version number; a version it does not recognise is read as an empty memo, so a format change costs one cold run rather than a wrong one.

### Where `live` comes from

Five pieces of evidence, in the order they are applied:

1. **The process argv** — `--session-id <uuid>` or `--resume <uuid>` names the
   session outright. A process carrying neither flag claims the newest transcript
   in its directory — newest **by content**, not by mtime: the age is taken from
   the last record with a `timestamp`, because bookkeeping records bump the mtime
   days after the conversation ended. Transcripts older than two hours are not
   candidates at all, and `K` processes in one directory take the `K` newest
   files between them.
2. **The pid from the hook.** Claude Code can change the id inside a live process
   (`/clear`, compaction), and the argv then points at a transcript nobody writes
   to any more. That change is a SessionStart like any other, so the hook writes
   `~/.claude/claude-wt/<id>.meta.json` at exactly that moment, with its own pid
   inside. The process moves to the named session, and the former id stops
   counting as live. The `pidStarted` + `boot` pair guards against reused
   numbers. This evidence does not decay: as long as the process lives, that is
   the session it writes to. It is also the only thing that gives a pid to
   sessions started as `claude -n <name>` — their argv has no uuid at all.
3. **A move by hook mark.** The fallback for sessions started before the hook
   learned to write a pid: if a neighbour in the same project directory has a
   fresher hook mark, less than two minutes old, the process moves to it.
   Processes already settled by the second piece of evidence are left alone.
4. **The hook mark.** A session whose `~/.claude/claude-wt/<id>.state.json` was
   updated within the last two minutes is live even with no process naming it.
5. **An open window.** A session named in `CCFZF_WINDOWS_FILE` is live whatever
   its transcript says: a window on screen is an observation, not a guess, and
   the two-hour cutoff of the first piece of evidence does not apply to it. This
   one acts only in `--state` and `--dump`; the `projects` and `sessions` modes
   and the interactive list never read the windows file, and `●` there follows
   the first four.

The fourth and fifth pieces of evidence only ever add. A session waiting on a
human sends no hooks and is recognised by the first one — by its live process.

`CCFZF_PROJECTS_FILE` — the project list, in the order the first picker shows it:

```json
{
 "generated": 1785460168.138,
 "projects": [
  {"path": "/home/you/projects/js/webapp", "name": "webapp", "mark": true,
   "sessions": 14, "live": 1, "mtime": 1785460166.26, "age": "12m"}
 ]
}
```

Both files are written through a temporary file and renamed into place, so a reader never sees half a list. The dump runs as a detached child and nothing on screen waits for it — reading `--limit` file tails costs more than the picker itself: ~0.12 s cold, ~0.08 s once the facts memo is warm, here, at the default of 100. Set either variable to an empty string to turn that half off; set both and nothing is spawned at all.

## The one file that comes the other way

`ccfzf --state` prints the whole answer as JSON on stdout, for a reader on another machine: `generated`, `sessions`, `projects`, `windowHost`, `windowPid` and `snapshots`. The sessions are the same set as in the dump, with the extra fields listed above. `projects` is close to what the `projects` mode shows, minus the colouring — `{path, name, mark, sessions, live, mtime}`, no `age`, because a reader that formats the age itself would otherwise carry two answers that drift apart — plus an optional `hotkey` on any row a window tracker has registered a shortcut for. A project with a hotkey but no sessions and no bookmark gets a synthetic row here that the `projects` mode itself would never show, so the shortcut does not drop out of the answer exactly when nobody has touched the project in a while. A marked project nobody has ever opened has no transcripts to date it, so its `mtime` is `0` — and those are precisely the rows the reader needs the list for.

The one file it writes is the sessions dump, and only when that has gone stale (30 s) — the picker that used to keep it fresh is the one that now calls `--state`.

Everything in the answer is derived here — except one thing, which cannot be: whether a session has a terminal **window** open. This side sees processes, not windows, and on a remote setup the windows are not even on this machine.

So `CCFZF_WINDOWS_FILE` is read rather than written. Whoever tracks the windows drops it next to the dumps:

```json
{
 "host": "the-machine-with-the-screen",
 "pid": 4312,
 "generated": 1785460168,
 "windows": {
  "c5bf2507-7381-4aa9-979d-b66242f39d7f": {"title": "webapp", "desktop": 2, "lastSeen": 1785460166}
 },
 "snapshots": [
  {"id": "s1", "created": 1785460100,
   "sessions": [{"id": "c5bf2507-7381-4aa9-979d-b66242f39d7f", "title": "webapp", "cwd": "/home/you/projects/js/webapp"}]}
 ],
 "projects": [
  {"cwd": "/home/you/projects/js/webapp", "name": "webapp", "hotkey": "Ctrl+F11"}
 ]
}
```

Sessions listed there gain a `window` field; `host` and `pid` come out as `windowHost` and `windowPid`. `host` lets the reader tell whether those windows are on the screen it is sitting in front of; `pid` is there because Windows hands the foreground only to the process that already owns it or caught the last input event, so a reader raising a window must first grant that right to the tracker by pid. `snapshots` is saved window layouts the tracker remembers, echoed into the answer's own `snapshots` field so a reader can offer "restore this layout" without asking anyone. `projects` is `cwd`/`name`/`hotkey` triples for whatever shortcuts the tracker has registered; joined into the answer's `projects` list by `cwd`, and the reason a project can show up there with no sessions and no bookmark at all.

The file is optional in every direction, field by field. Missing, unparseable, missing its keys, or older than two minutes — the whole file is treated as absent and nothing in the answer says otherwise. A malformed `windows`, `snapshots`, or `projects` entry costs only that entry, not the list it sits in. A stale file is treated as no file: the tracker rewrites it at least every half minute, so silence means the machine went away, not that the layout stopped moving.

## Requirements

- `bash`, `python3` (3.4+), and the usual POSIX tools
- `fzf` **0.36+** — that is where `pos()` and the `load` event came from; older builds fail loudly with `unknown action: pos`
- `claude`

Optional, degrades quietly when absent:

- `~/.fzf-marks` — gives `★`, human names, and rolls up sessions started in a project's subdirectories. Without it, projects come from `~/.claude/projects` alone and are named after their directory.
- `/proc` — the `●` running markers. Linux only; everything else works on macOS.
- `~/.claude/ccsessions-frozen.json` — a yellow `*` on sessions pinned with [`ccsessions`](https://github.com/ponytail-dev/ccsessions).
- `CCFZF_WINDOWS_FILE` — the `window` field in `--state`, and the fifth `live` argument in `--state` and `--dump`. Nobody writes it by default.

## How sessions map to projects

A session belongs to its own `cwd`. It additionally shows up under the nearest ancestor **mark**, so a session started in a config subrepo or a git worktree is visible from the project root. The restriction to marks is deliberate: without it, a mark on `~` would swallow the sessions of every project below it.

## License

MIT
