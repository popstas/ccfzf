#!/usr/bin/env node
// claude-wt — one tool for an agent to read and arrange its Claude Code session windows.
// Точка входа: разбор argv, диспетчер команд, код выхода. Сами команды — cli/lib/commands/.
import { EXIT, emit } from './lib/out.mjs';

const USAGE = `usage: claude-wt <group> <action> [args] [--json] [--url URL] [--machine HOST]

Commands:
  tree [--json]                          sessions, windows, heads and children, snapshots; marks your own
  window focus <session>                 raise the existing window of your session (never opens one)
  window layout <head>                   lay out the windows of your head's group
  snapshot list [--json]                 snapshots of trackers that have an http manager
  snapshot restore <id|last> [--sessions a,b]
                                         restore a snapshot of your own sessions

<session> is a sessionId, a unique prefix of it (6+ chars) or a name.
Only your own sessions can be acted on: this session and its descendants.

Options:
  --json            one JSON line on stdout
  --url URL         send to this manager instead of the window's tracker
  --machine HOST    use the tracker of this machine
  -h, --help        this help

Exit codes:
  0  done (or accepted, when "pending": true)
  1  refused, the reason is on stderr ("error" with --json)
  2  not found: session, window or machine
  3  outcome unknown (timeout, or connection lost after sending); retry only focus/layout
`;

// Флаги со значением и без; позиционные — всё остальное по порядку.
const VALUE_FLAGS = new Set(['--url', '--machine', '--sessions']);

function parseArgs(argv) {
  const pos = [];
  const opts = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') opts.json = true;
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
  'window focus': cmd('window-focus'),
  'window layout': cmd('window-layout'),
  'snapshot list': cmd('snapshot', 'list'),
  'snapshot restore': cmd('snapshot', 'restore'),
};

async function main(argv) {
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
  const key = COMMANDS[pos[0]] ? pos[0] : `${pos[0]} ${pos[1] ?? ''}`.trim();
  const load = COMMANDS[key];
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
