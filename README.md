# ccfzf

Pick a [Claude Code](https://claude.com/claude-code) project and session with `fzf`, then resume it — or start something else in that directory.

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
```

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

Start a new session and the cursor lands on the session that was actually created, not on `[+] new session`. The index is rebuilt on the way back, so titles, ages and running markers are current — that costs about as much as one fzf redraw.

`esc` goes back to the project list, `esc` again quits. Not compatible with `--print`, which exists precisely to hand a command back to the shell.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CCFZF_PROJECT_COMMAND` | `codex` | command 1, run in the project directory |
| `CCFZF_PROJECT_COMMAND2` | — | command 2 |
| `CCFZF_PROJECT_COMMAND3` | — | command 3 |
| `CCFZF_PROJECT_COMMAND_NAME[2,3]` | first word of the command | label shown in the list |
| `CCFZF_CLAUDE_COMMAND` | `claude` | the claude binary itself — a wrapper or extra flags |
| `FZF_MARKS_FILE` | `~/.fzf-marks` | where the marks live |

An empty command drops both its list entry and its hotkey. A command may carry arguments (`CCFZF_PROJECT_COMMAND2="codex --yolo"`). Every command value is a shell fragment, so quoting works as usual (`CCFZF_CLAUDE_COMMAND='"/opt/my tools/claude"'`).

Border, height and layout are left to your `FZF_DEFAULT_OPTS`.

## Requirements

- `bash`, `python3` (3.4+), and the usual POSIX tools
- `fzf` **0.36+** — that is where `pos()` and the `load` event came from; older builds fail loudly with `unknown action: pos`
- `claude`

Optional, degrades quietly when absent:

- `~/.fzf-marks` — gives `★`, human names, and rolls up sessions started in a project's subdirectories. Without it, projects come from `~/.claude/projects` alone and are named after their directory.
- `/proc` — the `●` running markers. Linux only; everything else works on macOS.
- `~/.claude/ccsessions-frozen.json` — a yellow `*` on sessions pinned with [`ccsessions`](https://github.com/ponytail-dev/ccsessions).

## How sessions map to projects

A session belongs to its own `cwd`. It additionally shows up under the nearest ancestor **mark**, so a session started in a config subrepo or a git worktree is visible from the project root. The restriction to marks is deliberate: without it, a mark on `~` would swallow the sessions of every project below it.

## License

MIT
