# Where `live` comes from

The `●` marker, and the `live` field in the dumps, come from five pieces of
evidence, applied in this order.

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

## How it is detected at all

Running sessions are found through `/proc` on Linux and a single `ps` call on
macOS, rather than through `lsof`. Which session a process is writing comes from
the agent's own registry at `~/.claude/sessions/<pid>.json`.

That registry is also how a session that has just started shows up at all: the
transcript file is created by the first turn, not by the session, so before the
first prompt there is no file to list.
