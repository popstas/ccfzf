# Session state hooks

`ccfzf --state` gives every session an `agent` record: what the agent is doing
(working, asking, waiting for review, idle), the first line of its last answer,
the last prompt, the question it stands on, the branch and its PR, cost and
context fill. Most of that is written by Claude Code hooks into
`~/.claude/claude-wt/`, one set of files per session, and `ccfzf` merges them
(`agent_of`). The hooks live in [`hooks/`](../hooks).

| Hook | Events | Writes |
|---|---|---|
| [`wt-progress.sh`](../hooks/wt-progress.sh) | UserPromptSubmit, Pre/PostToolUse, Notification, Stop, StopFailure, Pre/PostCompact | `<id>.state.json` — state, summary, prompt, question, branch, PR, turn start; `prs.json` — PR per `<cwd>#<branch>`; `<id>.precompact` across a compaction; removes `<id>.wait.json` when a prompt answers it ([below](#declared-wait)). Also sets the terminal progress bar (OSC 9;4) |
| [`claude-wt-statusline.sh`](../hooks/claude-wt-statusline.sh) | `statusLine`, plus `--hook` on UserPromptSubmit and PreToolUse:Skill | `<id>.status.json` — cost and context %. Hooks get neither number; the status line gets both, together with the context window size. Then it runs `ccstatusline` with the untouched input and prints its output. With `--hook` it writes nothing and prints nothing: it only passes the hook input to `ccstatusline --hook` |
| [`claude-wt-agent-state.sh`](../hooks/claude-wt-agent-state.sh) | SessionStart, PostCompact | `<id>.meta.json` — id, cwd, transcript, source, the claude pid and its start time. The pid is what ties a process to the session it writes after `/clear` or compaction — see [live-detection.md](live-detection.md) |
| [`ccfzf-dump.sh`](../hooks/ccfzf-dump.sh) | SessionStart | Runs `ccfzf --dump` in the background (≈0.4 s wall, on every SessionStart: startup, resume, clear, compact) |

`wt-progress.sh` folds the numbers from `status.json` into `state.json` on its
next event, so a reader that only gets one file per session still has them.
Files of sessions silent for a week are pruned on UserPromptSubmit, all of a
session's files at once.

## Declared wait

`claude-wt wait set` writes `<id>.wait.json` next to the session's state
([claude-wt.md](claude-wt.md)). `wt-progress.sh start` (UserPromptSubmit)
removes it when the prompt is an answer, and only then. The hook tells by the
`prompt` field of its stdin (measured on 2.1.332):

| `prompt` | Clears |
|---|---|
| plain text — typed by the human | yes |
| `<cross-session-message from="uds:/run/user/<uid>/cc-socks/<pid>.sock" …>` from the session's own head: `<pid>` is the sender's claude, `~/.claude/sessions/<pid>.json` names its `sessionId`, and it equals `headId` in `~/.ccfzf/children/<id>.json` (`CCFZF_CHILDREN_DIR`) | yes |
| the same from any other session, from an unknown pid, or without a children record | no |
| a harness wrapper — the whole text is one `<tag …>…</tag>` element: `<task-notification>` (a subagent report), `<teammate-message>` and the like | no |
| empty | no |

The transcript cannot help here: the prompt's own record is not in it yet when
the hook runs. Human text that merely starts with a tag (`<div> is off`) still
clears — only a closed wrapper counts as the harness. A loop or schedule wakeup
arrives as a plain prompt too and clears the wait; nothing in stdin tells it
from the human. The file is pruned with the rest of the session's files after
a week of silence.

## Why the dump hook

Without it, only the picker's own polling rewrites the dump (`--state` does it
when the dump is older than `CCFZF_STATE_DUMP_MAX_AGE`), and a hidden picker
polls as rarely as every eight minutes. Until then a window tracker cannot bind
the window of a session started by hand in a terminal: the session is not in
the dump yet. The hook breaks that loop by rewriting the dump the moment a
session is born — `ccfzf` finds it in `~/.claude/sessions/<pid>.json` even
before its transcript exists. Sessions opened from the picker do not need it;
the picker polls right after opening one.

It looks for `ccfzf` in this order: `CCFZF_BIN`; the `ccfzf` of the clone the
hook's symlink points into; `ccfzf` on `PATH`. If none is found it exits
quietly.

## Install

```sh
/path/to/ccfzf/hooks/install.sh --dry-run   # see what it would do
/path/to/ccfzf/hooks/install.sh
```

It links `~/.claude/hooks/<file>` to `<clone>/hooks/<file>`, the same way
`~/bin/ccfzf` is a symlink, so `git pull` updates the hooks too. It is
idempotent: a correct link is left alone, a file with the same content is
replaced, anything else is moved to `<file>.bak-<date>` first. It links
`~/bin/claude-wt` to `<clone>/cli/claude-wt.mjs` by the same rules
([docs/claude-wt.md](claude-wt.md)). It refuses to
run from a git worktree, whose links would dangle once the worktree is removed.

It does **not** edit `~/.claude/settings.json`. It prints the fragment to merge
by hand instead — every event above, the `statusLine` entry, and the
SessionStart dump hook. Keep your own hooks next to these ones;
`claude-wt-statusline.sh` replaces a `ccstatusline` status line, since it runs
`ccstatusline` itself. The `--hook` entries are there for `ccstatusline`'s
skills widget, which fills its cache only from `ccstatusline --hook`.

```json
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
```

## Requirements

- Linux: `bash`, `jq`, GNU `stat` (`stat -c`), `/proc` (for the claude pid in
  `meta.json`)
- `git` — branch and origin for the PR field
- `ccstatusline` on `PATH` for the status line, or `npx` as a slow fallback

## Not on Windows or macOS

These hooks run where the sessions run, and only on Linux. On a Windows or
macOS machine — and for sessions of the desktop app — there is no
`~/.claude/claude-wt/` directory at all. `ccfzf` then builds the `agent` record
from the transcript tail instead (`tail_facts` → `from_tail`), and marks it with
`source` so a reader can tell the two apart. That record carries only the
state, the question and the turn start: no summary, prompt, branch or PR, and
no cost or context % — those keys are absent rather than zero, since only the
status line knows them.
