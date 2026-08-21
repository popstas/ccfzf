# `--state`, and the one file that comes the other way

`ccfzf --state` prints the whole answer as JSON on stdout, for a reader on
another machine: `generated`, `sessions`, `projects`, `windowHost`, `windowPid`
and `snapshots`.

The sessions are the same set as in [the dump](dumps.md), plus `file`,
`projects`, `gist`, `doing`, `age`, `frozen`, `pid`, `tty`, `tmux`, `agent` and
`window`. The dump is not a subset by accident — the two have different readers.

`projects` is close to what the `projects` mode shows, minus the colouring —
`{path, name, mark, sessions, live, mtime}`, no `age`, because a reader that
formats the age itself would otherwise carry two answers that drift apart — plus
an optional `hotkey` on any row a window tracker has registered a shortcut for.

A project with a hotkey but no sessions and no bookmark gets a synthetic row here
that the `projects` mode itself would never show, so the shortcut does not drop
out of the answer exactly when nobody has touched the project in a while. A
marked project nobody has ever opened has no transcripts to date it, so its
`mtime` is `0` — and those are precisely the rows the reader needs the list for.

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
