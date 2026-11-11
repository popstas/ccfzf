# Child sessions: `claude-wt-new`

One Claude Code session (the *head*) sometimes opens others for a task and
then writes to them through `SendMessage`. To do that it needs to know, at the
moment it asks for the window, both the id and the name of the session it gets.
`claude-wt-new` starts such a session with both fixed in advance and leaves a
note saying who asked for it.

```sh
claude-wt-new <cwd> <name> <sessionId> <promptFile> <permissionMode|-> <head|-> <headId|->
```

`-` means "not given". `promptFile` may be `-` as well: the session then starts
without a first prompt, and so does an empty file. The prompt comes from a file
because the usual caller is a terminal template sent over ssh, where free-form
text would have to survive two rounds of shell quoting.

The checks: `cwd` is a directory; `name` and `head` are one line, not empty and
not starting with `-` (claude would read it as an option); `sessionId` and
`headId` are UUIDs; the permission mode is letters only, and claude itself
checks the value. A wrong argument means exit 2, a message on stderr, and
nothing written or started.

Then, in this order:

1. `$CCFZF_CHILDREN_DIR/<sessionId>.json` is written through a temporary file
   (default `~/.ccfzf/children`):
   `{sessionId, name, head, headId, cwd, createdAt}`. `head` and `headId` are
   left out when not given, `cwd` is the physical path, `createdAt` is unix
   seconds. If claude then fails to start, the record stays: nothing cleans the
   directory up, and nothing has to, since only the ids `--state` lists are ever
   looked up.
2. `claude -n <name> --session-id <id> [--permission-mode <m>] [-- <prompt>]`
   runs in an interactive `$SHELL` after `cd` into `cwd`, the same way ccfzf
   starts its own commands, so the rc file is read and `chpwd` hooks fire. The
   `--` keeps a prompt that starts with a dash from being read as an option;
   trailing newlines are dropped from the prompt.

`CCFZF_CLAUDE_COMMAND` replaces the claude binary here too (the tests put a
fake there).

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

## The parent session's environment

Run from a shell inside another Claude Code session, claude inherits that
session's markers (`CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, the
messaging socket) and does not register as a session of its own. The wrapper
unsets every `CLAUDE_CODE_*` plus `CLAUDECODE`, `CLAUDE_PID`, `CLAUDE_EFFORT`,
`CLAUDE_PLUGIN_DATA`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PROJECT_DIR` and
`CLAUDE_ENV_FILE` before starting it; whatever the rc file sets comes back,
since the shell that runs claude reads it.
