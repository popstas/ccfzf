# The dumps

Every run writes down what it saw, so whatever else you script around Claude
Code can read it without paying for its own scan. Two files, both replaced on
every launch (and again on the way back from a kiosk command, where the data has
changed underneath).

`ccfzf --dump` rewrites the same files and exits — for callers that need a fresh
dump without opening the picker.

## `CCFZF_SESSIONS_FILE`

The newest sessions across **all** projects (`--limit`, 100 by default), newest
first, plus every live session and every session with a window open, so the file
always holds whoever a window on screen might belong to.

The reader is a window tracker on another machine, and the fields are the ones
it needs — nothing else:

```json
{
 "generated": 1785460168.138,
 "total": 860,
 "shown": 104,
 "sessions": [
  {
   "id": "c5bf2507-7381-4aa9-979d-b66242f39d7f",
   "title": "Add a session picker",
   "cwd": "/home/you/projects/js/webapp",
   "live": true,
   "mtime": 1785460166.26,
   "kind": "interactive",
   "parent": "",
   "activityAt": 1785460166
  }
 ]
}
```

`total` is how many sessions exist, `shown` how many made it into the file.
`activityAt` is when this session's hook last wrote, in epoch seconds, or 0 if it
never did — the reader ranks same-titled candidates by it, and computing it here
saves it a network `stat` per candidate. `kind` is `interactive` or `background`,
and `parent` names the session a background agent was forked from.

## `CCFZF_PROJECTS_FILE`

The project list, in the order the first picker shows it:

```json
{
 "generated": 1785460168.138,
 "projects": [
  {"path": "/home/you/projects/js/webapp", "name": "webapp", "mark": true,
   "sessions": 14, "live": 1, "mtime": 1785460166.26, "age": "12m"}
 ]
}
```

## Cost and atomicity

Both files are written through a temporary file and renamed into place, so a
reader never sees half a list.

The dump runs as a detached child and nothing on screen waits for it — reading
`--limit` file tails costs more than the picker itself: ~0.12 s cold, ~0.08 s
once the facts memo is warm, at the default of 100. Set either variable to an
empty string to turn that half off; set both and nothing is spawned at all.

## The facts memo

`CCFZF_FACTS_FILE` caches what the last run learned about each transcript — its
title, first prompt and size — keyed by path, so the next `--state` or `--dump`
does not reread every transcript's tail just to get `title` back.

`--dump` never needs the first prompt, so its record carries no `gist`/`gistDone`
keys at all — not "looked and found nothing" but "did not look" — and a later
`--state`, even when the transcript's `mtime` still matches, sees the missing
keys and goes looking anyway rather than trusting a half-empty record.

A record is recomputed once its transcript's `mtime` moves. The cached `gist` is
separately dropped whenever the transcript's `size` has shrunk since it was last
measured — the signature of a transcript replaced outright (restored from a
backup, compacted) rather than appended to, which an `mtime` bump alone would not
catch. A stable `gist` otherwise survives any number of appends unchanged.

The stored `gist` is capped at 200 characters, matching the field it feeds in
`--state`. The file carries a version number; a version it does not recognise is
read as an empty memo, so a format change costs one cold run rather than a wrong
one.
