# Where `live` comes from

The `●` marker, and the `live` field in the dumps, come from five pieces of
evidence, applied in this order.

1. **The process argv** — `--session-id <uuid>` or `--resume <uuid>` names the
   session outright. A process carrying neither flag claims the newest transcript
   in its directory — newest **by content**, not by mtime: the age is taken from
   the last record with a `timestamp`, because bookkeeping records bump the mtime
   days after the conversation ended. A transcript whose last record is older
   than the process itself was not written by it and is never a candidate; one
   written after the process started is a candidate however long it has been
   silent since. `K` processes in one directory take the `K` newest files
   between them, the latest-started process choosing first. When the start
   time cannot be read, the old rule applies: transcripts silent for more than
   two hours are not candidates.

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
   Not after `claude-wt session close`: it leaves `<id>.closed.json` next to
   the state file, and a hook mark no newer than that file is the trace of a
   closed session, not evidence of work — neither for this step nor for the
   move by hook mark above. A hook that writes after the close (the session
   was resumed) counts again; a process naming the id never asks. Other exits
   (`/exit`, a window closed by hand) leave no such file and keep the tail of
   up to two minutes after the last hook event.

5. **An open window.** A session named in `CCFZF_WINDOWS_FILE` is live whatever
   its transcript says: a window on screen is an observation, not a guess, and
   no cutoff of the first piece of evidence applies to it. It acts the same in
   `--state`, `--dump` and the interactive list (`projects`, and through its
   index `sessions`), so a session is never live in one view and dead in
   another. The one exception is direct entry by id (`--session`): there
   "live" means a local process holds the session, and a session that only
   has a window on another machine is still resumed.

The fourth and fifth pieces of evidence only ever add. A session waiting on a
human sends no hooks and is recognised by the first one — by its live process.

## How it is detected at all

Running sessions are found through `/proc` on Linux and a single `ps` call on
macOS, rather than through `lsof`. Which session a process is writing comes from
the agent's own registry at `~/.claude/sessions/<pid>.json`.

That registry is also how a session that has just started shows up at all: the
transcript file is created by the first turn, not by the session, so before the
first prompt there is no file to list.
