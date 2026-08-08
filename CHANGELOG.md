# Changelog


## v0.2.0 - 2026-08-08

### Features

- --state carries projects, and liveness stops trusting mtime
- Attach a process to its session by pid, not by guesswork
- A fresh hook stamp is proof of life on its own
- Move a process to the session id it is actually writing
- state: Optional window data from a tracker elsewhere
- Land the deployed script — --state, usage, background agents
- Name new sessions by basename
- Add --dump for sync sessions rewrite

### Bug Fixes

- Live_by_hook was undoing the reattribute it ran right after
- state: Refresh a stale session dump on the way

### Documentation

- Pid from the hook is now the first argument for a moved session
- Where the live flag comes from

### Testing

- A harness for the embedded python block, and hook stamps


## v0.1.0 - 2026-08-01

### Features

- Name the terminal while a picker is on screen
- --session <id> for non-interactive resume
- Dump every project too, and sessions across all of them
- Dump the shown session list to CCFZF_SESSIONS_FILE
- Kiosk widget on ctrl-t, zsh completion, docs
- Configurable claude command via CCFZF_CLAUDE_COMMAND
- ccfzf — fzf picker for Claude Code projects and sessions

### Bug Fixes

- Run picked commands in an interactive shell

