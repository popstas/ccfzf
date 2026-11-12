# Child sessions: `claude-wt-new`

One Claude Code session (the *head*) sometimes opens others for a task and
then writes to them through `SendMessage`. To do that it needs to know, at the
moment it asks for the window, both the id and the name of the session it gets.
`claude-wt-new` starts such a session with both fixed in advance and leaves a
note saying who asked for it.

```sh
claude-wt-new <cwd> <name> <sessionId> <promptFile> <permissionMode|-> <head|-> <headId>
```

`-` means "not given". `promptFile` may be `-` as well: the session then starts
without a first prompt, and so does an empty file. `headId` is required (see
[Who may open a child](#who-may-open-a-child)); `head` left as `-` is taken
from the head's mark. The prompt comes from a file
because the usual caller is a terminal template sent over ssh, where free-form
text would have to survive two rounds of shell quoting.

The checks: `cwd` is a directory; `name` and `head` are one line, not empty and
not starting with `-` (claude would read it as an option); `sessionId` and
`headId` are UUIDs; the permission mode is letters only, and claude itself
checks the value — except `bypassPermissions` (in any case), which a child never
gets: it counts as a wrong argument. A wrong argument means exit 2, a message on stderr, and
nothing written or started.

## Who may open a child

Only a running head session. A child may be one as well: once it has its own
mark it opens children of its own, to any depth. Before anything is written or
started:

1. `$CCFZF_HEADS_DIR/<headId>.json` (default `~/.ccfzf/heads`) exists and
   names `headId` as its `sessionId`. The head session writes this mark —
   `{sessionId, name, cwd, createdAt}` — when it takes the lead.
2. That session is running: `claude agents --json` lists it. A mark outlives
   its session, so the mark alone proves nothing.
3. `sessionId` is not a running session: the new record would otherwise
   overwrite the record of a live session, such as the head itself.
4. `sessionId` is not an ancestor of the head, dead or alive: walking up
   `headId` from the head through the children directory never meets it. A
   record with that id would close the chain of heads into a loop. A loop
   already in the records (they can be edited by hand) ends the walk; it does
   not hang it.

Session ids are compared without regard to case.

The caller checks the same before it asks for a window; the wrapper checks
again because a request can reach the window manager without going through the
caller at all.

A refusal — the head check or the cwd root below — is exit 3 with the reason
on stderr; nothing is written or started.
In a terminal, any failure (2 or 3) waits for Enter, up to ten minutes: the
window was opened by a request that has long had its answer, and it would
otherwise close before anyone could read why.

## Where a child may run

The window manager may let a head open a child in any directory under one root
(its `claudeWt.childCwdRoot`), not only in the projects of its own list. It runs
on Windows and compares strings, so a symlink under the root that leads out of
it would pass there. The wrapper checks again on this machine:
`CCFZF_CHILD_CWD_ROOT` set and not empty means `cwd`, after `pwd -P`, has to lie
strictly under the root, also taken after `pwd -P`. The root itself is no
place for a child.

- Outside the root: exit 3, as any refusal.
- A root that is not an absolute path to a directory, or one the wrapper
  cannot enter: exit 2, a wrong argument. The same goes for a `cwd` it cannot
  enter.

A leading `//` counts as `/` in both: bash keeps it in `pwd -P`, and on Linux
it names the same directory.
- Unset or empty: no check, as before.

The manager's launch command sets it —
`exec env CCFZF_CHILD_CWD_ROOT='{childCwdRoot}' ~/bin/claude-wt-new …` — and
leaves it empty when the directory is in its projects list: a child admitted by
exact match is not held to the root. A variable and not an eighth argument, so
that an older wrapper with a newer command, and the other way round, still
work.

## What happens next

In this order:

1. `$CCFZF_CHILDREN_DIR/<sessionId>.json` is written through a temporary file
   (default `~/.ccfzf/children`):
   `{sessionId, name, head, headId, cwd, createdAt}`. `head` is left out when
   neither the argument nor the mark has a name, `cwd` is the physical path,
   `createdAt` is unix seconds. If claude then fails to start, the record stays: nothing cleans the
   directory up, and nothing has to, since only the ids `--state` lists are ever
   looked up.
2. `claude -n <name> --session-id <id> [--permission-mode <m>] [-- <prompt>]`
   runs in an interactive `$SHELL` after `cd` into `cwd`, the same way ccfzf
   starts its own commands, so the rc file is read and `chpwd` hooks fire. The
   `--` keeps a prompt that starts with a dash from being read as an option;
   trailing newlines are dropped from the prompt.
3. The wrapper waits for claude and ends with its exit code — except that a
   session closed by a signal (HUP, INT or TERM: 129, 130, 143) ends with 0.
   Killing a child, closing its window or losing the ssh link is a normal end,
   and a terminal that keeps the window open on a non-zero code (Windows
   Terminal's `closeOnExit: graceful`) has to close it; a crash still shows. The
   wrapper traps those signals itself, so when the whole window goes it lives
   long enough to report 0.

`CCFZF_CLAUDE_COMMAND` replaces the claude binary here too, for the launch and
for `claude agents` (the tests put a fake there).

## What `--state` makes of it

A session that has a record gets two more keys in its `--state` row:

| Key | Meaning |
|---|---|
| `head` | the name of the session that opened it: the address `SendMessage` takes |
| `headId` | that session's id |

Each key is there only when the record has it, like `todo` and `comment`. They
are not `parent`: that one belongs to background forks, where it is the id of
the session that forked them.

The directory is listed once per `--state` call, and only the files of sessions
in the answer are opened. `CCFZF_CHILDREN_DIR=""` turns the reading off.

## The name that sticks

`-n` sets the name that `ListAgents` and `SendMessage` use: the `name` in
Claude Code's own `~/.claude/sessions/<pid>.json`, with `nameSource: user`. The
title ccfzf shows as `title` comes from the transcript instead, and the two can
part: a hook that answers with `sessionTitle` once wrote its own
`custom-title` into such a session while `ListAgents` went on showing the `-n`
name. A head that wants to be sure of the address can look it up by the id it
chose, in `claude agents --json` or that registry.
The `session-name-from-branch` hook leaves a session alone once it has a
record in the children directory, so a child keeps its `-n` name on a feature branch.

## The parent session's environment

Run from a shell inside another Claude Code session, claude inherits that
session's markers (`CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, the
messaging socket) and does not register as a session of its own. The wrapper
unsets every `CLAUDE_CODE_*` plus `CLAUDECODE`, `CLAUDE_PID`, `CLAUDE_EFFORT`,
`CLAUDE_PLUGIN_DATA`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PROJECT_DIR` and
`CLAUDE_ENV_FILE` before starting it; whatever the rc file sets comes back,
since the shell that runs claude reads it.
