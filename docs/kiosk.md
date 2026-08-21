# Kiosk mode

```sh
ccfzf --kiosk          # or just press ctrl-t
```

Normally `ccfzf` replaces itself with whatever you picked and is gone. In kiosk
mode it stays: the command runs as a child, and when it exits you are back in the
session list of the same project with the cursor on the row you came out of.

So a session you resume, quit, and want back is two keystrokes away, and `ctrl-d`
into a shell followed by `exit` returns to the list rather than to your prompt.

`esc` goes back to the project list, `esc` again quits. Not compatible with
`--print`, which exists precisely to hand a command back to the shell.

## New sessions

Start a new session and the cursor lands on the session that was actually
created, not on `[+] new session`. New sessions are started with
`claude -n <basename>` so the terminal title and the ccfzf row match the project
folder immediately.

The index is rebuilt on the way back, so titles, ages and running markers are
current — that costs about as much as one fzf redraw.

## The terminal title

While a picker is on screen it names the terminal `ccfzf project select` /
`ccfzf session select`.

In kiosk mode you come back to the list from a session that has renamed the
window after itself, and a window still wearing that name was indistinguishable
from the live session; the picker now takes the title back, and whatever you
launch next sets its own.

## The interactive shell

Picked commands run in an interactive shell (`$SHELL -ic 'cd <dir> && <cmd>'`),
so your rc file is read and the `cd` fires its `chpwd` hooks for the project
directory.

Without that, a command started from ccfzf would inherit the environment of the
shell you pressed the key in — a per-directory variable would still name the
project you came from. The cost is one rc load per launch; `--print` needs none
of this, because there the `cd` happens in your own shell.
