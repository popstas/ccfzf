// session type: печать в поле ввода дочерней сессии. ssh — подделка: пишет
// вызовы в calls.jsonl и отвечает по режиму скрипта (probe/text/enter).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, readFileSync, existsSync, chmodSync } from 'node:fs';
import { join } from 'node:path';
import { runCli, world, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, GRAND, OTHER } from './fixtures.mjs';
import { adoptedLink } from '../../cli/lib/commands/session-type.mjs';
import {
  checkText, readiness, normTitle, plainScreen, titleMatches, pickPane, inputBox, boxHasText, boxIsText,
  parseOut, payload, encodeScript, sshCommand, stdinFor, BOOT, SCRIPT, sshNotConnected,
} from '../../cli/lib/type.mjs';

const RULE = '─'.repeat(60);
const screen = (box) => (box === null
  ? ['● Bash(rm -rf build)', ' Do you want to proceed?', ' ❯ 1. Yes', '   2. No', ''].join('\r\n')
  : ['● Done.', '', `${RULE} .child-one ─`, `❯\u00a0${box}`, RULE, '  ⏵⏵ auto mode on', ''].join('\r\n'));
const LIST = JSON.stringify([{ window_id: 0, tab_id: 0, pane_id: 0, title: '✳ child-one' }]);
const ok = (o) => ({ stdout: `${JSON.stringify({ ok: true, ...o })}\r\n` });
const sent = (box) => ({ stdout: `SENT\r\n${JSON.stringify({ ok: true, sent: true, screen: screen(box) })}\r\n` });

const FAKE_SSH = `#!/usr/bin/env node
const fs = require('fs'); const path = require('path');
const dir = process.env.FAKE_SSH_DIR;
const input = fs.readFileSync(0, 'utf8');
const nl = input.indexOf('\\n');
const p = JSON.parse(input.slice(nl + 1));
const journal = path.join(dir, '.ccfzf', 'typed.jsonl');
const logged = fs.existsSync(journal) ? fs.readFileSync(journal, 'utf8').trim().split('\\n').length : 0;
fs.appendFileSync(path.join(dir, 'calls.jsonl'), JSON.stringify({ argv: process.argv.slice(2), script: input.slice(0, nl), payload: p, logged }) + '\\n');
const all = JSON.parse(fs.readFileSync(path.join(dir, 'responses.json'), 'utf8'));
const q = all[p.mode] || [];
const r = (Array.isArray(q) ? q.shift() : q) || { stdout: '', stderr: 'no response', status: 1 };
fs.writeFileSync(path.join(dir, 'responses.json'), JSON.stringify(all));
if (r.write) fs.writeFileSync(path.join(dir, r.write[0]), r.write[1]);
process.stdout.write(r.stdout || ''); process.stderr.write(r.stderr || '');
process.exit(r.status ?? 0);
`;

function setup({ caller = HEAD, child = {}, win = {}, hook = null, responses = {}, children = CHILDREN } = {}) {
  const t = trackers(now());
  t['box-a'].windows[CHILD1] = { title: '└child-one', app: 'wezterm-gui.exe', pid: 4242, ...win };
  const w = world({ state: loadState(), trackers: t, children, heads: HEADS, caller });
  const sessions = join(w.dir, '.claude', 'sessions');
  const hooks = join(w.dir, '.claude', 'claude-wt');
  mkdirSync(sessions, { recursive: true });
  mkdirSync(hooks, { recursive: true });
  // pid — живой процесс теста: readiness проверяет, что ребёнок жив.
  writeFileSync(join(sessions, '1.json'), JSON.stringify({ pid: process.pid, sessionId: HEAD, name: 'demo-head', status: 'busy' }));
  writeFileSync(join(sessions, '2.json'), JSON.stringify({ pid: process.pid, sessionId: CHILD1, name: '.child-one', status: 'idle', ...child }));
  if (hook) writeFileSync(join(hooks, `${CHILD1}.state.json`), JSON.stringify(hook));
  const fake = join(w.dir, 'fake-ssh');
  writeFileSync(fake, FAKE_SSH);
  chmodSync(fake, 0o755);
  writeFileSync(join(w.dir, 'responses.json'), JSON.stringify(responses));
  const env = { ...w.env, CLAUDE_WT_SSH: fake, FAKE_SSH_DIR: w.dir };
  const read = (f) => (existsSync(join(w.dir, f)) ? readFileSync(join(w.dir, f), 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []);
  return {
    dir: w.dir,
    run: (args) => {
      const r = runCli(['session', 'type', ...args], env);
      const raw = read('.ccfzf/typed.jsonl');
      return { ...r, calls: read('calls.jsonl'), raw, log: raw.filter((e) => e.result !== 'sending'), o: args.includes('--json') && r.stdout ? JSON.parse(r.stdout) : null };
    },
    cleanup: w.cleanup,
  };
}

function withSetup(opts, fn) {
  const s = setup(opts);
  try { return fn(s); } finally { s.cleanup(); }
}

const GOOD = { probe: [ok({ list: LIST, screen: screen('') })], text: [sent('hello child')], enter: [sent('')] };

// --- чистые функции ---

test('checkText: пусто, длина, управляющие символы; \\n и \\t можно', () => {
  assert.match(checkText(''), /missing/);
  assert.match(checkText('   '), /missing/);
  assert.match(checkText('x'.repeat(16001)), /too long/);
  assert.match(checkText('a\u001b[201~b'), /U\+001B/);
  assert.match(checkText('a\rb'), /U\+000D/);
  assert.match(checkText('a\u007f'), /U\+007F/);
  assert.match(checkText('a\u009b'), /U\+009B/);
  assert.equal(checkText('строка 1\n\tстрока 2'), null);
});

test('readiness: только idle; waiting, busy, question, мёртвый pid — отказ', () => {
  const live = { isAlive: () => true };
  assert.deepEqual(readiness({ status: 'idle', pid: 1 }, null, live), { ok: true });
  assert.match(readiness(null, null, live).reason, /not running/);
  assert.match(readiness({ status: 'idle', pid: 7 }, null, { isAlive: () => false }).reason, /pid 7 is gone/);
  assert.match(readiness({ status: 'waiting', waitingFor: 'approve Bash: rm -rf x', pid: 1 }, null, live).reason, /dialog: approve Bash: rm -rf x/);
  assert.match(readiness({ status: 'busy', pid: 1 }, null, live).reason, /busy, not idle: a permission dialog may open/);
  assert.match(readiness({ status: 'idle', pid: 1 }, { state: 'question' }, live).reason, /question/);
  assert.deepEqual(readiness({ status: 'idle', pid: 1 }, { state: 'review' }, live), { ok: true });
});

test('заголовок панели: глиф и └ снимаются, точка в имени остаётся', () => {
  assert.equal(normTitle('✳ .waiting'), '.waiting');
  assert.equal(normTitle('◐ .session-type'), '.session-type');
  assert.equal(normTitle('└child-one'), 'child-one');
  assert.ok(titleMatches('✳ child-one', ['.child-one', '└child-one']));
  assert.ok(!titleMatches('✳ child-two', ['.child-one', '└child-one']));
  assert.ok(!titleMatches('', ['']));
});

test('заголовок панели внутри zellij: приставка «<сессия> | » снимается до глифа', () => {
  // Живой заголовок 28.11 на nb: автокомпакт отказал `wrong-window` сессии
  // bike-choice-head, потому что сверял «popstas | ✳ bike-choice-head» с именем.
  assert.equal(normTitle('popstas | ✳ bike-choice-head'), 'bike-choice-head');
  assert.ok(titleMatches('popstas | ✳ bike-choice-head', ['bike-choice-head']));
  assert.deepEqual(
    pickPane(JSON.stringify([{ pane_id: 0, title: 'popstas | ✳ bike-choice-head' }]), ['bike-choice-head']),
    { pane: 0, title: 'popstas | ✳ bike-choice-head' },
  );
  // Приставка — одно слово: заголовок чужого окна с « | » внутри остаётся целым.
  assert.equal(normTitle('Some App | thing'), 'Some App | thing');
  // Другая панель zellij в фокусе — другой заголовок, и отказ остаётся.
  assert.ok(!titleMatches('popstas | ✳ other-session', ['bike-choice-head']));
});

test('pickPane: одна панель с заголовком ребёнка, иначе отказ', () => {
  assert.deepEqual(pickPane(LIST, ['└child-one']), { pane: 0, title: '✳ child-one' });
  assert.match(pickPane('[]', ['x']).error, /no panes/);
  assert.match(pickPane(JSON.stringify([{ pane_id: 0, title: 'a' }, { pane_id: 1, title: 'b' }]), ['a']).error, /2 panes/);
  assert.match(pickPane(LIST, ['someone-else']).error, /wrong window/);
  assert.match(pickPane('nope', ['x']).error, /bad JSON/);
});

test('inputBox: пустое поле, текст, многострочное, диалог вместо поля', () => {
  assert.equal(inputBox(screen('')), '');
  assert.equal(inputBox(screen('hello')), 'hello');
  const multi = ['out', RULE, '❯\u00a0first line', '  second line', RULE, 'status'].join('\n');
  assert.equal(inputBox(multi), 'first line\n  second line');
  assert.equal(inputBox(screen(null)), null);
  assert.equal(inputBox(''), null);
  // Линии без ❯ между ними (рамка вывода) — не поле, ищется выше.
  const framed = ['x', RULE, '❯ typed', RULE, 'mid', RULE, 'not a prompt', RULE].join('\n');
  assert.equal(inputBox(framed), 'typed');
});

test('бледная подсказка Claude Code в поле — не текст (get-text --escapes)', () => {
  const E = '\u001b';
  // Снято живьём 25.11: подсказка следующего промпта в пустом поле, SGR 0;2.
  const ghost = [
    `${E}[38;5;244m${RULE}`,
    `${E}[39m❯\u00a0${E}(B${E}[0;2mпроверка 2: печать с Enter${E}(B${E}[0m${E}[38;5;246m     \r`,
    `${E}[38;5;244m${RULE}`,
    `${E}[39m  ${E}[38;5;246m⏸ manual mode on · PR ${E}]8;id=u-1;https://x/45${E}\\#45${E}]8;;${E}\\\r`,
  ].join('\n');
  assert.equal(inputBox(ghost), '');
  const typed = ghost.replace(`${E}[0;2mпроверка 2: печать с Enter`, `${E}[0mнабрано руками`);
  assert.equal(inputBox(typed), 'набрано руками');
  // 38;2;r;g;b — цвет, а не «бледный»; 22 снимает бледный.
  assert.equal(plainScreen(`${E}[38;2;10;20;30mцвет${E}[2mтень${E}[22mснова`), 'цветснова');
  assert.equal(plainScreen(`a${E}[1;2mb${E}[mc`), 'ac');
  assert.ok(SCRIPT.includes("'get-text', '--escapes'"));
});

test('boxHasText и boxIsText', () => {
  assert.ok(boxHasText('hello child', 'hello child'));
  assert.ok(boxHasText('a long text that wr\n  aps here', 'a long text that wraps here'));
  assert.ok(boxHasText('[Pasted text #1 +12 lines]', 'many\nlines'));
  assert.ok(!boxHasText('', 'hello'));
  assert.ok(!boxHasText(null, 'hello'));
  assert.ok(boxIsText('hello  child', 'hello child'));
  assert.ok(!boxIsText('[Pasted text #1 +12 lines]', 'many\nlines'));
  assert.ok(!boxIsText('hello child and more', 'hello child'));
});

test('скрипт: каждый вызов wezterm cli несёт --no-auto-start', () => {
  const calls = SCRIPT.match(/@\('cli'[^)]*\)/g) ?? [];
  assert.deepEqual(calls, ["@('cli', '--no-auto-start')"]);
  // Процесс wezterm запускается в одном месте — в Wez, и только с этими аргументами.
  assert.equal((SCRIPT.match(/ProcessStartInfo/g) ?? []).length, 1);
  assert.ok(!/Start-Process|&\s*\$exe|&\s*['"][^'"]*wezterm/i.test(SCRIPT));
  assert.equal(Buffer.from(encodeScript(), 'base64').toString('utf16le'), BOOT);
});

test('командная строка ssh короткая: скрипт едет в stdin', () => {
  // Шелл OpenSSH на Windows — cmd.exe, предел 8191 символ.
  assert.ok(sshCommand().length < 2000, `${sshCommand().length}`);
  const input = stdinFor('{"mode":"probe"}');
  const nl = input.indexOf('\n');
  assert.equal(Buffer.from(input.slice(0, nl), 'base64').toString('utf8'), SCRIPT);
  assert.equal(input.slice(nl + 1), '{"mode":"probe"}');
  assert.match(SCRIPT, /\$global:cwtPayload \| ConvertFrom-Json/);
});

test('payload: текст base64 UTF-8, probe без панели', () => {
  assert.deepEqual(JSON.parse(payload('probe', { pid: 5 })), { mode: 'probe', pid: 5 });
  const p = JSON.parse(payload('text', { pid: 5, pane: 0, text: 'привет\n"q"' }));
  assert.equal(Buffer.from(p.text, 'base64').toString('utf8'), 'привет\n"q"');
  assert.equal(p.pane, 0);
  assert.ok(p.settleMs > 0);
  assert.equal(JSON.parse(payload('enter', { pid: 5, pane: 0 })).text, undefined);
});

test('parseOut и sshNotConnected', () => {
  assert.deepEqual(parseOut('SENT\r\n{"ok":true}\r\n'), { sent: true, result: { ok: true } });
  assert.deepEqual(parseOut('#< CLIXML\n'), { sent: false, result: null });
  assert.ok(sshNotConnected(255, 'ssh: connect to host nb port 22: Connection refused'));
  assert.ok(!sshNotConnected(255, 'Connection to nb closed by remote host.'));
  assert.ok(!sshNotConnected(1, 'Connection refused'));
});

// --- команда ---

test('печать без Enter: проба и текст, журнал с текстом', () => withSetup({ responses: GOOD }, (s) => {
  const r = s.run([CHILD1, 'hello child', '--json']);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe', 'text']);
  assert.equal(r.calls[0].payload.pid, 4242);
  assert.equal(Buffer.from(r.calls[1].payload.text, 'base64').toString('utf8'), 'hello child');
  // ssh на адрес менеджера из трекера; скрипт — -EncodedCommand.
  assert.ok(r.calls[0].argv.includes('127.0.0.1'));
  assert.equal(r.calls[0].argv.at(-1), sshCommand());
  assert.equal(Buffer.from(r.calls[0].script, 'base64').toString('utf8'), SCRIPT);
  // Намерение записано до отправки текста, исход — после.
  assert.equal(r.calls[0].logged, 0);
  assert.equal(r.calls[1].logged, 1);
  assert.deepEqual(r.raw.map((e) => [e.result, e.step]), [['sending', 'text'], ['ok', undefined]]);
  assert.equal(r.raw[0].text, 'hello child');
  assert.equal(r.o.result, 'ok');
  assert.equal(r.o.entered, false);
  assert.equal(r.log.length, 1);
  const e = r.log[0];
  assert.equal(e.text, 'hello child');
  assert.equal(e.enter, false);
  assert.equal(e.result, 'ok');
  assert.equal(e.headId, HEAD);
  assert.equal(e.headName, 'demo-head');
  assert.equal(e.childId, CHILD1);
  assert.equal(e.childName, '.child-one');
  assert.equal(e.host, 'box-a');
  assert.match(e.at, /^\d{4}-\d\d-\d\dT/);
}));

test('--enter: проба, текст, Enter', () => withSetup({ responses: GOOD }, (s) => {
  const r = s.run([CHILD1, 'hello child', '--enter']);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe', 'text', 'enter']);
  assert.match(r.stdout, /typed into \.child-one and sent/);
  assert.equal(r.log[0].entered, true);
  assert.equal(r.log[0].enter, true);
}));

test('многострочный текст и текст с ведущим тире после --', () => withSetup({ responses: { ...GOOD, text: [sent('[Pasted text #1 +2 lines]')] } }, (s) => {
  const r = s.run([CHILD1, '--', '-1 строка\nвторая', '--enter']);
  // --enter после -- — уже текст? Нет: всё после -- позиционное, третьего не ждём.
  assert.equal(r.status, 1);
  assert.match(r.stderr, /usage: session type/);
  const r2 = s.run(['--enter', CHILD1, '--', '-1 строка\nвторая']);
  assert.equal(r2.status, 0, r2.stderr);
  assert.equal(Buffer.from(r2.calls.at(-2).payload.text, 'base64').toString('utf8'), '-1 строка\nвторая');
}));

test('в себя и в чужую — отказ без ssh, в журнале', () => withSetup({ responses: GOOD }, (s) => {
  const self = s.run([HEAD, 'hi']);
  assert.equal(self.status, 1);
  assert.match(self.stderr, /only child sessions/);
  const other = s.run([OTHER, 'hi']);
  assert.equal(other.status, 1);
  assert.match(other.stderr, /not your session/);
  assert.equal(other.calls.length, 0);
  assert.deepEqual(other.log.map((e) => e.result), ['refused', 'refused']);
  assert.equal(other.log[1].text, 'hi');
}));

test('усыновлённый ребёнок или потомок усыновлённого — отказ без ssh', () => {
  const adopted = CHILDREN.map((c) => (c.sessionId === CHILD1 ? { ...c, adopted: true } : c));
  withSetup({ children: adopted, responses: GOOD }, (s) => {
    const r = s.run([CHILD1, 'hi']);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /adopted \(head adopt\), not opened by session spawn/);
    assert.equal(r.calls.length, 0);
    assert.equal(r.log[0].result, 'refused');
  });
  assert.equal(adoptedLink(adopted, GRAND, HEAD), CHILD1);
  assert.equal(adoptedLink(adopted, CHILD1, HEAD), CHILD1);
  assert.equal(adoptedLink(CHILDREN, GRAND, HEAD), null);
  // Звено выше вызывающей не считается: от него вызывающая не зависит.
  assert.equal(adoptedLink(adopted, GRAND, CHILD1), null);
});

test('busy, waiting, question — отказ без ssh', () => {
  for (const [opts, re] of [
    [{ child: { status: 'busy' } }, /busy, not idle/],
    [{ child: { status: 'waiting', waitingFor: 'approve Bash: git push' } }, /waiting on a dialog: approve Bash: git push/],
    [{ hook: { state: 'question' } }, /question/],
  ]) {
    withSetup({ ...opts, responses: GOOD }, (s) => {
      const r = s.run([CHILD1, 'hi', '--enter']);
      assert.equal(r.status, 1);
      assert.match(r.stderr, re);
      assert.equal(r.calls.length, 0);
      assert.equal(r.log[0].result, 'refused');
      assert.match(r.log[0].reason, re);
    });
  }
});

test('управляющий символ — отказ до ssh', () => withSetup({ responses: GOOD }, (s) => {
  const r = s.run([CHILD1, 'a\u001b[201~b']);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /control character/);
  assert.equal(r.calls.length, 0);
}));

test('не WezTerm или нет pid — отказ', () => {
  withSetup({ win: { app: 'WindowsTerminal.exe' }, responses: GOOD }, (s) => {
    const r = s.run([CHILD1, 'hi']);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /unsupported terminal: WindowsTerminal\.exe/);
    assert.equal(r.calls.length, 0);
  });
  withSetup({ win: { pid: undefined }, responses: GOOD }, (s) => {
    const r = s.run([CHILD1, 'hi']);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /no pid/);
  });
});

test('непустое поле или диалог на экране — отказ после пробы', () => {
  withSetup({ responses: { ...GOOD, probe: [ok({ list: LIST, screen: screen('Стас набирает') })] } }, (s) => {
    const r = s.run([CHILD1, 'hi']);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /input box is not empty: "Стас набирает"/);
    assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe']);
  });
  withSetup({ responses: { ...GOOD, probe: [ok({ list: LIST, screen: screen(null) })] } }, (s) => {
    const r = s.run([CHILD1, 'hi']);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /no input box on screen/);
  });
});

test('чужое окно по заголовку панели — отказ', () => withSetup({
  responses: { ...GOOD, probe: [ok({ list: JSON.stringify([{ pane_id: 0, title: '✳ someone-else' }]), screen: screen('') })] },
}, (s) => {
  const r = s.run([CHILD1, 'hi']);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /wrong window/);
}));

test('текст уже в поле: без --enter ничего, с --enter — только Enter', () => withSetup({
  responses: { probe: [ok({ list: LIST, screen: screen('hello child') }), ok({ list: LIST, screen: screen('hello child') })], enter: [sent('')] },
}, (s) => {
  const r = s.run([CHILD1, 'hello child']);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /already in the input box/);
  const r2 = s.run([CHILD1, 'hello child', '--enter']);
  assert.equal(r2.status, 0, r2.stderr);
  assert.deepEqual(r2.calls.map((c) => c.payload.mode), ['probe', 'probe', 'enter']);
  assert.equal(r2.log[1].already, true);
  assert.equal(r2.log[1].typed, false);
}));

test('обрыв после SENT — код 3, в журнале unknown и совет --check', () => withSetup({
  responses: { ...GOOD, text: [{ stdout: 'SENT\r\n', stderr: 'Connection to nb closed by remote host.', status: 255 }] },
}, (s) => {
  const r = s.run([CHILD1, 'hi', '--enter']);
  assert.equal(r.status, 3);
  assert.match(r.stderr, /--check before anything else/);
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe', 'text']);
  assert.equal(r.log[0].result, 'unknown');
  assert.equal(r.log[0].step, 'text');
}));

test('ssh не соединился на тексте — отказ 1; обрыв без SENT — 3', () => {
  withSetup({ responses: { ...GOOD, text: [{ stderr: 'ssh: connect to host nb port 22: Connection refused', status: 255 }] } }, (s) => {
    const r = s.run([CHILD1, 'hi']);
    assert.equal(r.status, 1);
    assert.equal(r.log[0].result, 'refused');
  });
  withSetup({ responses: { ...GOOD, text: [{ stderr: 'Connection reset by peer', status: 255 }] } }, (s) => {
    const r = s.run([CHILD1, 'hi']);
    assert.equal(r.status, 3);
    assert.equal(r.log[0].result, 'unknown');
  });
});

test('отказ скрипта (нет сокета) — 1 с причиной', () => withSetup({
  responses: { probe: [{ stdout: '{"ok":false,"step":"socket","reason":"no wezterm socket for pid 4242"}\r\n' }] },
}, (s) => {
  const r = s.run([CHILD1, 'hi']);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /no wezterm socket for pid 4242/);
}));

test('Enter не шлётся, если ребёнок стал busy после текста', () => withSetup({
  responses: {
    ...GOOD,
    text: [{ ...sent('hi'), write: ['.claude/sessions/2.json', JSON.stringify({ pid: process.pid, sessionId: CHILD1, name: '.child-one', status: 'busy' })] }],
  },
}, (s) => {
  const r = s.run([CHILD1, 'hi', '--enter']);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /busy.*Enter not sent, the text stays in the input box/);
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe', 'text']);
  assert.equal(r.log[0].typed, true);
  assert.equal(r.log[0].step, 'enter');
}));

test('--check: поле ввода, без журнала', () => withSetup({ responses: GOOD }, (s) => {
  const r0 = s.run(['--check', CHILD1]);
  assert.equal(r0.status, 0, r0.stderr);
  assert.match(r0.stdout, /input is empty/);
  assert.deepEqual(r0.calls.map((c) => c.payload.mode), ['probe']);
  assert.equal(r0.log.length, 0, '--check не пишет в журнал');
}));

test('журнал не пишется — ничего не печатается', () => withSetup({ responses: GOOD }, (s) => {
  writeFileSync(join(s.dir, '.ccfzf'), 'not a directory');
  const r = s.run([CHILD1, 'hi', '--enter']);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /not writable.*nothing typed/);
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe']);
}));

test('SENT, а потом отказ скрипта (get-text завис) — код 3, не отказ', () => withSetup({
  responses: { ...GOOD, enter: [{ stdout: 'SENT\r\n{"ok":false,"step":"error","reason":"wezterm cli get-text timed out"}\r\n' }] },
}, (s) => {
  const r = s.run([CHILD1, 'hi', '--enter']);
  assert.equal(r.status, 3);
  assert.match(r.stderr, /sent, but wezterm cli get-text timed out/);
  assert.equal(r.log.at(-1).result, 'unknown');
  assert.equal(r.log.at(-1).step, 'enter');
  assert.deepEqual(r.raw.map((e) => e.result), ['sending', 'sending', 'unknown']);
}));

test('--check с текстом или с --enter — ошибка вызова', () => withSetup({ responses: GOOD }, (s) => {
  assert.equal(s.run([CHILD1, 'x', '--check']).status, 1);
  assert.equal(s.run([CHILD1, '--check', '--enter']).status, 1);
}));
