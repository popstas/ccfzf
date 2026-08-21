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

## Features

- **Fast enough to bind to a key** — the project list is up in 0.05 s, with no cache to go stale and no truncation window.
- **Two pickers, one flow** — projects, then that project's sessions, with `esc` walking back up.
- **Running sessions are marked** — `●`, from process state and the agent's own hooks rather than from guesswork.
- **Kiosk mode** — stay inside ccfzf: quit a session and land back on the row you came from.
- **Your own commands** — up to three per project, on `ctrl-s` / `ctrl-f` / `ctrl-g`, plus a shell on `ctrl-d`.
- **zsh widget and completion** — `ctrl-t` from anywhere, and completion for flags and marks.
- **Machine-readable dumps** — every run leaves a JSON list of sessions and projects for whatever else you script.
- **`--state` for remote readers** — one JSON answer a picker on another machine can live on.

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

**Kiosk mode** (`--kiosk`, or `ctrl-t`) keeps ccfzf on screen instead of replacing itself with what you picked: quit a session and you are back on the row you came from; `esc` walks out. Not compatible with `--print`.

→ New-session behaviour, the terminal title, and why picked commands run in an interactive shell: [docs/kiosk.md](docs/kiosk.md).

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

## Machine-readable output

Every run also writes down what it saw, so whatever else you script around Claude Code can read it without paying for its own scan — a sessions dump and a projects dump, both replaced on every launch, both written atomically. `ccfzf --dump` rewrites them without opening the picker.

`ccfzf --state` is the richer output: one JSON answer on stdout — sessions, projects, snapshots and window information — for a picker on another machine. The window half is the one thing this side cannot derive, since it sees processes and not windows, so `CCFZF_WINDOWS_FILE` is *read* rather than written, dropped next to the dumps by whoever tracks the windows.

→ File formats, fields and the facts memo: [docs/dumps.md](docs/dumps.md).

→ The `--state` answer and the windows file it reads: [docs/state.md](docs/state.md).

## Why

The obvious way to build this is to shell out to a session lister and format its output. That turned out to cost 2–3 seconds per launch, because listing sessions that way reads every `~/.claude/projects/**/*.jsonl` in full — 757 MB of history in my case.

`ccfzf` reads only what it needs: `cwd` is on the first line of a session file, the title and the latest activity are in the last 256 KB, and the first prompt is found near the start under a size cap.

| | |
|---|---|
| project list (first thing you see) | **0.05 s** |
| detecting running sessions | 0.006 s |
| session list, 117 files / 101 MB | 0.24 s |

There is no cache to go stale, and no truncation window — the list is always complete.

→ How a running session is recognised, and the five pieces of evidence behind `●`: [docs/live-detection.md](docs/live-detection.md).

## Requirements

- `bash`, `python3` (3.4+), and the usual POSIX tools
- `fzf` **0.36+** — that is where `pos()` and the `load` event came from; older builds fail loudly with `unknown action: pos`
- `claude`

Optional, degrades quietly when absent:

- `~/.fzf-marks` — gives `★`, human names, and rolls up sessions started in a project's subdirectories. Without it, projects come from `~/.claude/projects` alone and are named after their directory.
- `lsof` — on macOS only, and only for the working directory of a session started without
  arguments. Everything else about the `●` running markers comes from one `ps` call;
  on Linux they come from `/proc` and need nothing extra.
- `~/.claude/ccsessions-frozen.json` — a yellow `*` on sessions pinned with [`ccsessions`](https://github.com/ponytail-dev/ccsessions).
- `CCFZF_WINDOWS_FILE` — the `window` field in `--state`, and the fifth `live` argument in `--state` and `--dump`. Nobody writes it by default.

## How sessions map to projects

A session belongs to its own `cwd`. It additionally shows up under the nearest ancestor **mark**, so a session started in a config subrepo or a git worktree is visible from the project root. The restriction to marks is deliberate: without it, a mark on `~` would swallow the sessions of every project below it.

## Documentation

- [docs/kiosk.md](docs/kiosk.md) — kiosk mode in full
- [docs/dumps.md](docs/dumps.md) — the sessions and projects dumps, and the facts memo
- [docs/state.md](docs/state.md) — the `--state` answer and the windows file it reads
- [docs/live-detection.md](docs/live-detection.md) — how a running session is recognised
- [CHANGELOG.md](CHANGELOG.md) — what changed between versions

## Related

- [ccfzf-picker](https://github.com/popstas/ccfzf-picker) — the desktop interface built on `--state`.
- [macos-windows-manager](https://github.com/popstas/macos-windows-manager) — the window tracker that writes `CCFZF_WINDOWS_FILE`.

## License

MIT
