# `claude-wt`: the agent's window tool

`claude-wt` is a command for a Claude Code session to read the picture of
sessions and windows and to act on the windows of its own sessions: raise one,
lay out a head's group, restore a layout snapshot. Its user is an agent, so
every command prints one JSON line with `--json` and exits with a code that
means something.

```
claude-wt tree [--json]                  sessions, windows, heads and children, snapshots; marks your own
claude-wt window focus <session>         raise the existing window of your session (never opens one)
claude-wt window layout <head>           lay out the windows of your head's group
claude-wt snapshot list [--json]         snapshots of trackers that have an http manager
claude-wt snapshot restore <id|last> [--sessions a,b]
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
`tree` and `snapshot list` still work.

## What each command does

- **`tree`** reads `ccfzf --state`, the children records and the head marks
  (`~/.ccfzf/heads/`). Each session row: `id`, `title`, `live`, `cwd`,
  `window: {host, title} | null`, `own`, `head`, `parent`. Each snapshot:
  `id`, `created`, `host`, `sessions` (ids), `own` — true only when all its
  sessions are yours. Without `--json` it prints a short tree of live, own and
  windowed sessions.
- **`window focus`** only raises a window that exists. A session with no
  window in `--state` is refused with code 2 before anything is sent — an
  older window manager would open a new terminal instead. The request is
  `POST /claude-wt/focus {id, raiseOnly: true}`; `foreground: false` in the
  answer is a refusal ("window did not come to front"). A manager that does not
  report `foreground` gets code 0, `foreground: null` and a warning on stderr.
- **`window layout <head>`** sends one group — the head and its descendants
  with a window on the head's machine, in the order they were started — as
  `POST /claude-wt/place {mode: "group", groups: [[...]], selected: <head>}`.
  Fewer than two windows is refused without a request.
- **`snapshot list`** lists snapshots of machines whose tracker has an http
  manager, newest first.
- **`snapshot restore <id|last>`** restores a snapshot whose sessions are all
  yours, or only the sessions named with `--sessions` (each yours and in the
  snapshot). `last` is the newest snapshot of your own. The manager answers at
  once and raises the windows over the next half minute, so success is
  `pending: true` — "accepted, outcome unknown".

## Where the command goes

Each window names its machine (`window.host` in `--state`). The command goes to
that machine's window manager over http, at `http.host`:`http.port` from its
tracker file in `~/.ccfzf/windows/<host>.json`. A tracker file older than 15
minutes is refused as stale (the machine is asleep or its share dropped), and
so is one without `http`. `--machine HOST` picks another tracker, `--url URL`
skips trackers altogether. The timeout is 5 seconds (`CLAUDE_WT_TIMEOUT_MS`).

A manager refusal is an `ok: false` body with a `reason`, whatever the status
code; a non-2xx answer without one is a refusal with `HTTP <status>`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | done, or accepted when `pending: true` |
| 1 | refused; the reason is on stderr and in `error` with `--json` |
| 2 | not found: session, window, snapshot or machine |
| 3 | outcome unknown (timeout). `focus` and `layout` are safe to retry; `snapshot restore` is not — it could open a second window |

## Environment

Every path can be replaced, which is how the tests run without touching a
live machine: `CCFZF_BIN` (default `ccfzf`), `CLAUDE_BIN` (`claude`),
`CCFZF_WINDOWS_DIR` (`~/.ccfzf/windows`), `CCFZF_CHILDREN_DIR`
(`~/.ccfzf/children`), `CCFZF_HEADS_DIR` (`~/.ccfzf/heads`).

## Install

`hooks/install.sh` links `~/bin/claude-wt` to `<clone>/cli/claude-wt.mjs`
next to the hooks, by the same rules (idempotent, a different file is backed
up, refuses to run from a git worktree). It needs Node 18 or newer and has no
dependencies.

Tests: `node --test tests/cli/*.test.mjs`.
