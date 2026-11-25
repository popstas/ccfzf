#!/usr/bin/env node
// claude-wt — one tool for an agent to read and arrange its Claude Code session windows.
// Точка входа: разбор argv, диспетчер команд, код выхода. Сами команды — cli/lib/commands/.
import { EXIT, emit } from './lib/out.mjs';
import { runLegacy, emitLegacy } from './lib/legacy.mjs';

const USAGE = `usage: claude-wt <group> <action> [args] [--json] [--url URL] [--machine HOST]

Commands:
  tree [--json]                          sessions, windows, heads and children, snapshots; marks your own
  waiting [--tree] [--json]              live sessions waiting for something (declared, permission, question, reply, PR) and how to clear it
  wait set --kind decision|review|external --ask "..." [--clear-by "..."] [<session>]
                                         declare what your session waits for; cleared by the next human prompt or your head's message
  wait clear [<session>]                 drop the declared wait
  wait show [<session>]                  the declared wait, if any
  window focus <session>                 raise the existing window of your session (never opens one)
  window layout <head>                   lay out the windows of your head's group
  window place <session> --zone M:P      move your session's existing window into FancyZones zone P of monitor M
  window icon <session> <name>|--clear   set your session's window icon from the icons folder of its machine
  window badge <session> <name>|--clear  set the badge on your session's taskbar button (beats project and head badges)
  window taskbar <session> hide|show|auto  hide or show your session's taskbar button (show beats the picker's auto-hiding)
  window icons [--machine HOST]          names you can use with window icon/badge (.ico in the icons folder)
  snapshot list [--json]                 snapshots of trackers that have an http manager
  snapshot restore <id|last> [--sessions a,b]
                                         restore a snapshot of your own sessions
  session open <session>                 open a window for your session that has none (never a second one)
  session unread <session>               mark your session unseen for the picker (no window is raised)
  session seen <session>                 mark your session seen: clears unread, puts the taskbar light out
  session type <child> <text> [--enter]  type into the input box of your child session, as if typed by hand
                                         (only children opened by session spawn, never adopted ones; WezTerm
                                         over ssh; refused unless the child is idle with an empty input box:
                                         never into a permission dialog). Logged to ~/.ccfzf/typed.jsonl
  session type <child> --check           show the child's input box, type nothing

Session and head commands (moved from the skill scripts; arguments, JSON and exit
codes are compatible with the skill scripts: one JSON line on stdout, always):
  session find --session-id <id> [--timeout s] [--interval s] | --name <n> | --list [--cwd c]
                                         a live session, its current name and window place (0 / 2 not found)
  session rename --session-id <id> --to <name> | --cancel [--settings f]
                                         queue a new name; it applies on the target's next prompt
  session close --session-id <id> [--force] [--kill] [--wait s]
                                         close a child of this head (SIGTERM, wait)
  session spawn --task <slug> | --name <n> --prompt-file <f> [--cwd d] [--dry-run] [--fork] ...
                                         open a child session; 3 = outcome unknown, never resend
  head mark                              mark this session as a head
  head adopt [--release] <name|id>...    take live sessions in as children (or let them go)

<session> is a sessionId, a unique prefix of it (6+ chars) or a name; wait set/clear/show default to this session.
Only your own sessions can be acted on: this session and its descendants.

Options:
  --json            one JSON line on stdout
  --url URL         send to this manager instead of the window's tracker
  --machine HOST    use the tracker of this machine
  --clear           window icon/badge: drop what was set, back to the automatic one
  --tree            waiting: group by head -> children
  --enter           session type: press Enter after the text (sends it)
  --check           session type: only read the child's input box
  --                the rest are positional (a text starting with "-")
  -h, --help        this help

Exit codes:
  0  done (or accepted, when "pending": true)
  1  refused, the reason is on stderr ("error" with --json)
  2  not found: session, window or machine
  3  outcome unknown (timeout, or connection lost after sending); retry only focus/layout/place
     session unread/seen and window icon/badge/taskbar, never session open or session spawn (a second window).
     session type: never resend blindly, the text could double. Run session type <child> --check first:
     an empty input box or exactly your text in it — the same command again is safe (a text already
     in the box is not typed twice, --enter only presses Enter); anything else — leave it to the human
`;

// Флаги со значением и без; позиционные — всё остальное по порядку.
const VALUE_FLAGS = new Set(['--url', '--machine', '--sessions', '--zone', '--kind', '--ask', '--clear-by']);

function parseArgs(argv) {
  const pos = [];
  const opts = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--') { pos.push(...argv.slice(i + 1)); break; }
    if (a === '--json') opts.json = true;
    else if (a === '--enter') opts.enter = true;
    else if (a === '--check') opts.check = true;
    else if (a === '--clear') opts.clear = true;
    else if (a === '--tree') opts.tree = true;
    else if (a === '-h' || a === '--help') opts.help = true;
    else if (VALUE_FLAGS.has(a)) {
      const v = argv[i + 1];
      if (v === undefined || v.startsWith('--')) return { error: `${a} needs a value` };
      opts[a.slice(2)] = v;
      i++;
    } else if (a.startsWith('--') && a.includes('=') && VALUE_FLAGS.has(a.slice(0, a.indexOf('=')))) {
      opts[a.slice(2, a.indexOf('='))] = a.slice(a.indexOf('=') + 1);
    } else if (a.startsWith('-') && a !== '-') return { error: `unknown option: ${a}` };
    else pos.push(a);
  }
  return { pos, opts };
}

// "<group> <action>" → модуль команды; грузится лениво, чтобы справка не тянула остальное.
const cmd = (file, name = 'default') => async () => (await import(`./lib/commands/${file}.mjs`))[name];
const COMMANDS = {
  tree: cmd('tree'),
  waiting: cmd('waiting'),
  'wait set': cmd('wait', 'set'),
  'wait clear': cmd('wait', 'clear'),
  'wait show': cmd('wait', 'show'),
  'window focus': cmd('window-focus'),
  'window layout': cmd('window-layout'),
  'window place': cmd('window-place'),
  'window icon': cmd('window-icon', 'icon'),
  'window badge': cmd('window-icon', 'badge'),
  'window taskbar': cmd('window-taskbar', 'taskbar'),
  'window icons': cmd('window-icons'),
  'snapshot list': cmd('snapshot', 'list'),
  'snapshot restore': cmd('snapshot', 'restore'),
  'session open': cmd('session-open'),
  'session unread': cmd('session-mark', 'unread'),
  'session seen': cmd('session-mark', 'seen'),
  'session type': cmd('session-type'),
};

// Команды, переехавшие из скриптов скиллов: argv им — как скрипту, мимо общего
// разбора; вывод — JSON скрипта всегда (cli/lib/legacy.mjs).
const LEGACY = {
  'head mark': cmd('head-mark'),
  'session find': cmd('session-find'),
  'session rename': cmd('session-rename'),
  'session close': cmd('session-close'),
  'head adopt': cmd('head-adopt'),
  'session spawn': cmd('session-spawn'),
};

async function legacy(argv) {
  const key = `${argv[0]} ${argv[1]}`;
  // Справка — только первым словом после команды: дальше `-h` может быть значением (`--to -h`).
  if (argv[2] === '-h' || argv[2] === '--help') {
    process.stdout.write(USAGE);
    return EXIT.OK;
  }
  const run = await LEGACY[key]();
  return emitLegacy(await runLegacy(run, argv.slice(2), process.env));
}

async function main(argv) {
  if (argv.length >= 2 && Object.hasOwn(LEGACY, `${argv[0]} ${argv[1]}`)) return legacy(argv);
  const parsed = parseArgs(argv);
  if (parsed.error) {
    process.stderr.write(`claude-wt: ${parsed.error}\n${USAGE}`);
    return EXIT.REFUSED;
  }
  const { pos, opts } = parsed;
  if (opts.help || pos.length === 0 || (pos.length === 1 && pos[0] === 'help')) {
    process.stdout.write(USAGE);
    return EXIT.OK;
  }
  const has = (k) => Object.hasOwn(COMMANDS, k);
  const key = has(pos[0]) ? pos[0] : `${pos[0]} ${pos[1] ?? ''}`.trim();
  const load = has(key) ? COMMANDS[key] : null;
  if (!load) {
    process.stderr.write(`claude-wt: unknown command: ${pos.join(' ')}\n${USAGE}`);
    return EXIT.REFUSED;
  }
  const rest = pos.slice(key.split(' ').length);
  const run = await load();
  let result;
  try {
    result = await run(rest, opts, process.env);
  } catch (e) {
    result = { code: EXIT.REFUSED, error: e.message };
  }
  return emit(result, { json: opts.json });
}

main(process.argv.slice(2)).then(
  (code) => { process.exitCode = code; },
  (e) => { process.stderr.write(`claude-wt: ${e.stack || e.message}\n`); process.exitCode = EXIT.REFUSED; },
);
