# `--state`, and the one file that comes the other way

`ccfzf --state` prints the whole answer as JSON on stdout, for a reader on
another machine: `generated`, `sessions`, `projects`, `windowHost`, `windowPid`
and `snapshots`.

The sessions are the same set as in [the dump](dumps.md). Each record carries
`id`, `cwd`, `title`, `mtime`, `live` and `kind` always, and beyond them only
what is set: `pid`, `tty`, `tmux`, `zellij`, `parent`, `frozen`, `prompts`,
`todo`, `comment`, `entrypoint`, `spec`/`plan`, `agent`, `window`/`windows`,
`shell`/`shellCmd`, and the `head`/`headId` of a session started by
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

What the reader never looked at is not sent at all: `file`, the per-session
`projects`, `gist`, `doing`, `age` and `activityAt` (that one is for the dump).
The answer is compact JSON, without spaces after `,` and `:`. Together this
took the answer at `--limit 300` from 644 KB to 292 KB, and at 500 from 928 KB
to 371 KB — it travels over ssh once a second while the picker is shown.

`projects` is close to what the `projects` mode shows, minus the colouring —
`{path, name, mark, sessions, live, mtime}`, no `age`, because a reader that
formats the age itself would otherwise carry two answers that drift apart — plus
an optional `hotkey` on any row a window tracker has registered a shortcut for.

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
without asking anyone. `projects` is `cwd`/`name`/`hotkey` triples for whatever
shortcuts the tracker has registered; joined into the answer's `projects` list by
`cwd`, and the reason a project can show up there with no sessions and no
bookmark at all.

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
