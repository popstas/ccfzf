# `--state`, and the one file that comes the other way

`ccfzf --state` prints the whole answer as JSON on stdout, for a reader on
another machine: `generated`, `sessions`, `projects`, `windowHost`, `windowPid`
and `snapshots`.

The sessions are the same set as in [the dump](dumps.md). Each record carries
`id`, `cwd`, `title`, `mtime`, `live` and `kind` always, and beyond them only
what is set: `pid`, `tty`, `tmux`, `zellij`, `parent`, `frozen`, `prompts`,
`todo`, `comment`, `task`, `entrypoint`, `spec`/`plan`, `agent`, `window`/`windows`,
`projectCwd`/`projectType`,
`shell`/`shellCmd`, `disconnected`, and the `head`/`headId` of a session started by
[`claude-wt-new`](children.md). An
empty value — `""`, `0`, `false`, `null`, `[]` — is left out rather than sent;
the reader treats a missing key exactly as it treated the empty one. Two
exceptions: a `live` session always carries a numeric `pid` (zero when only an
open window makes it live), and an `agent` record always carries `updated`.
Inside `agent` the same rule applies, and `lastSummary` is left out whenever
`summary` is set, since the reader only falls back to it on an empty `summary`.

An `agent.state` of `active` whose `updated` is more than 30 minutes old is sent
as `idle`, with `updated` and `event` left as they were. The hook marks every
tool call, so a working agent is never silent that long; a record frozen on
`active` means the end of the turn never arrived (an interrupted turn, a killed
process). This applies to records from the hook and from the transcript tail
alike. The dump carries no agent record, but its `shell` flag reads the same
settled state.

`shell` is `true` on a live session whose turn is over while a background
command still runs — the same flag as in [the dump](dumps.md), where its rules
are. `shellCmd` is the start of that command, whitespace collapsed, cut to 80
characters, for the card; empty, and so absent, when the command line could not
be read (always on Windows, where the registry answers but no process list does).

`disconnected` is `true` on a live session whose ssh link is gone while the
agent lives on: the client side slept or lost the network, sshd still moves
the agent's output into TCP, and nobody acknowledges it. The sign is the send
queue of that ssh socket — non-empty, not shrinking between samples, and
stalled, for at least 8 seconds. Stalled means the kernel is retrying: the
retransmission timer fires (`retrnsmt` > 0 in `/proc/net/tcp`, nobody ACKs)
or zero-window probes go out (the ninth field, `icsk_probes_out`: the data
cannot leave at all). The queue alone is not enough: a healthy session that
writes all the time (a status line, a spinner) always has a packet in flight,
but its ACK comes back within a round trip and neither counter moves.
The socket is found through `SSH_CONNECTION` in `/proc/<pid>/environ` and
matched on all four of its fields against `/proc/net/tcp{,6}`, which takes
neither `ss` nor root. The two samples are two neighbouring `--state` calls,
not a sleep inside one: the previous sample lives in `CCFZF_SENDQ_FILE`
(`$XDG_CACHE_HOME/ccfzf/sendq.json`), and one older than 60 seconds is replaced
rather than compared, so a reader polling every few minutes never sees the
flag. Skipped: sessions inside tmux or zellij (their `SSH_CONNECTION` belongs to
a client that may be long gone, while the session is fine), sessions without
`SSH_CONNECTION`, and sessions whose socket is already closed. A session moved
by `reptyr -T` is judged by the connection of the reptyr that holds it, not by
the stale one in the agent's own environment. Linux only; an agent that writes
nothing leaves no trace in the queue. The dump does not carry the flag.

`task` is the Obsidian vault task the session was recorded under:
`{text, done, vault, more?}`. The link is a `- Сессия <name>` sub-item in a
task's block of a vault's `tasks.md` (the `sess2task` skill writes it), and the
vaults are the sections of `CCFZF_VAULTS_CONFIG` (`~/.claude/vaults-config.md`)
that name both `` `vault` `` and `` `tasks` ``. The sub-item belongs to the
nearest line above with a checkbox and a smaller indent, so one under a nested
`- [ ]` belongs to that task. The name is the first word after `Сессия `,
leading junk such as `└` dropped (a leading `.` or `_` stays: child sessions of a head are named `.child`), and is matched exactly against the session's
`title` — a session renamed after it was recorded gets no task. With several
tasks under one name an open one wins over a done one, then the freshest by its
`➕` date; the rest are counted in `more`, present only when non-zero. `text` is
cleaned of Tasks plugin marks (`➕ 📅 ✅ ⏳ 🛫` with their dates, priority marks)
and link markup (`[[a|b]]` → `b`, `[t](u)` → `t`) and cut to 120 characters;
`vault` is the vault directory's name. The files are read whole on every
answer, about 2 ms for two vaults of 70 and 100 KB.

`projectCwd` is the project the session belongs to, for grouping by project type:
the nearest ancestor of `cwd` (or `cwd` itself) among the window tracker's
`projects[].cwd`, matched on whole path segments (`/a/bc` is not under `/a/b`);
failing that, the nearest ancestor bookmark; failing that, `cwd` itself. It is
always set. `projectType` is the `type` of that tracker project, absent when it
has none — so a session in a project's worktree gets the project's type. The
reader has only exact `cwd` matches, hence the field.

What the reader never looked at is not sent at all: `file`, the per-session
`projects`, `gist`, `doing`, `age` and `activityAt` (that one is for the dump).
The answer is compact JSON, without spaces after `,` and `:`. Together this
took the answer at `--limit 300` from 644 KB to 292 KB, and at 500 from 928 KB
to 371 KB — it travels over ssh once a second while the picker is shown.

`projects` is close to what the `projects` mode shows, minus the colouring —
`{path, name, mark, sessions, live, mtime}`, no `age`, because a reader that
formats the age itself would otherwise carry two answers that drift apart — plus
an optional `hotkey` on any row a window tracker has registered a shortcut for,
an optional `icon`, and an optional `type` (`work`, `home` or another group name
from the tracker's project list).

A project with a hotkey but no sessions and no bookmark gets a synthetic row here
that the `projects` mode itself would never show, so the shortcut does not drop
out of the answer exactly when nobody has touched the project in a while. A
marked project nobody has ever opened has no transcripts to date it, so its
`mtime` is `0` — and those are precisely the rows the reader needs the list for.

## `--if-changed <fp>`

Every full answer carries a `fingerprint`: 16 hex characters of a hash over the
answer itself, with sorted keys, minus what changes without meaning anything to
the reader — `generated` at the top and `lastSeen` in each window record. The
exclusions are named one by one rather than listing what goes in, so a field
added later is covered by the fingerprint without anyone remembering to add it.

`ccfzf --state --if-changed <fp>` builds the whole answer as usual and, when its
fingerprint is still `<fp>`, prints only

```json
{"unchanged":true,"fingerprint":"<fp>","generated":1785460168.4}
```

instead of hundreds of kilobytes. Anything else in `<fp>` — stale, mistyped,
from another `--limit` — just gets the full answer with the new fingerprint. The
dump and the transcript memo are written before that fork, so the short answer
changes nothing on disk.

A reader holding a cached answer keeps that answer's `lastSeen`: it is out of the
fingerprint precisely because it ticks every few seconds while nothing else
moves, and nothing should rely on it being fresh.

Compatibility goes both ways. A reader that never sends the key gets the full
answer as before, with one extra top-level field. A version of `ccfzf` older than
the key rejects it like any unknown argument (`--state takes no other mode
flags`, exit 2) and has no `fingerprint` in its answer — so a reader should send
back only a fingerprint it got from the same source, and drop it on any failure.
The python block run directly (the Windows road, no bash wrapper) takes
`--limit <n>` and `--if-changed <fp>` after `--state` in either order and ignores
anything it does not know.

The one file `--state` writes is the sessions dump, and only when that has gone
stale (30 s) — the picker that used to keep it fresh is the one that now calls
`--state`.

## `CCFZF_WINDOWS_FILE`

Everything in the answer is derived here — except one thing, which cannot be:
whether a session has a terminal **window** open. This side sees processes, not
windows, and on a remote setup the windows are not even on this machine.

So `CCFZF_WINDOWS_FILE` is read rather than written. Whoever tracks the windows
drops it next to the dumps:

```json
{
 "host": "the-machine-with-the-screen",
 "pid": 4312,
 "generated": 1785460168,
 "windows": {
  "c5bf2507-7381-4aa9-979d-b66242f39d7f": {"title": "webapp", "desktop": 2, "lastSeen": 1785460166, "minimized": false}
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

Sessions listed there gain a `window` field; `host` and `pid` come out as
`windowHost` and `windowPid`.

`host` lets the reader tell whether those windows are on the screen it is sitting
in front of. `pid` is there because Windows hands the foreground only to the
process that already owns it or caught the last input event, so a reader raising
a window must first grant that right to the tracker by pid.

`snapshots` is saved window layouts the tracker remembers, echoed into the
answer's own `snapshots` field so a reader can offer "restore this layout"
without asking anyone. `projects` is `cwd`/`name` plus an optional `hotkey`,
`icon` and `type` for whatever projects the tracker knows; an entry with none of
the three is dropped. They are joined into the answer's `projects` list by
`cwd`, and a hotkey is the reason a project can show up there with no sessions
and no bookmark at all — an icon or a type alone does not add a row. `type` is
trimmed and lower-cased on read.

A window's `minimized` says the window is folded into the taskbar or the Dock —
something only the tracker can see, and something a reader needs to dim that row
or leave it out of a tiling layout. Only a real `true` counts: a tracker of an
older version writes no such field, and anything else reads as an ordinary
window — a dimmed row for an open window costs more than an undimmed one for a
hidden window.

## Degradation

The file is optional in every direction, field by field. Missing, unparseable,
missing its keys, or older than two minutes — the whole file is treated as absent
and nothing in the answer says otherwise.

A malformed `windows`, `snapshots`, or `projects` entry costs only that entry,
not the list it sits in. A stale file is treated as no file: the tracker rewrites
it at least every half minute, so silence means the machine went away, not that
the layout stopped moving.
