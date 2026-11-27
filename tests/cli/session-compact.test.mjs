// session compact: `/compact` в поле ввода idle-сессии по просьбе таймера
// пикера (решения Стаса 27.11, 2a). Механика session type, но без вызывающей
// сессии и без проверки «только дети»; ssh — та же подделка, что в тестах type.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, readFileSync, existsSync, chmodSync } from 'node:fs';
import { join } from 'node:path';
import { runCli, world, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, CHILD1, CHILD2, OTHER } from './fixtures.mjs';

const RULE = '─'.repeat(60);
const screen = (box) => (box === null
  ? ['● Bash(rm -rf build)', ' Do you want to proceed?', ' ❯ 1. Yes', '   2. No', ''].join('\r\n')
  : ['● Done.', '', `${RULE} .child-one ─`, `❯ ${box}`, RULE, '  ⏵⏵ auto mode on', ''].join('\r\n'));
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
fs.appendFileSync(path.join(dir, 'calls.jsonl'), JSON.stringify({ argv: process.argv.slice(2), payload: p, logged }) + '\\n');
const all = JSON.parse(fs.readFileSync(path.join(dir, 'responses.json'), 'utf8'));
const q = all[p.mode] || [];
const r = (Array.isArray(q) ? q.shift() : q) || { stdout: '', stderr: 'no response', status: 1 };
fs.writeFileSync(path.join(dir, 'responses.json'), JSON.stringify(all));
process.stdout.write(r.stdout || ''); process.stderr.write(r.stderr || '');
process.exit(r.status ?? 0);
`;

// Сессия молчит час без двух минут: 58 мин от последнего ответа с кешем.
const IDLE_CACHE = () => now() - 58 * 60 - 10;

function setup({ caller, child = {}, win = {}, hook = null, responses = {}, agent = {}, row = {} } = {}) {
  const t = trackers(now());
  t['box-a'].windows[CHILD1] = { title: '└child-one', app: 'wezterm-gui.exe', pid: 4242, ...win };
  const state = loadState();
  const s1 = state.sessions.find((s) => s.id === CHILD1);
  s1.agent = { state: 'idle', updated: IDLE_CACHE(), cacheAt: IDLE_CACHE(), ...agent };
  Object.assign(s1, row);
  const w = world({ state, trackers: t, children: CHILDREN, heads: HEADS, caller });
  const sessions = join(w.dir, '.claude', 'sessions');
  const hooks = join(w.dir, '.claude', 'claude-wt');
  mkdirSync(sessions, { recursive: true });
  mkdirSync(hooks, { recursive: true });
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
      const r = runCli(['session', 'compact', ...args, '--json'], env);
      const raw = read('.ccfzf/typed.jsonl');
      return { ...r, calls: read('calls.jsonl'), raw, log: raw.filter((e) => e.result !== 'sending'), o: r.stdout ? JSON.parse(r.stdout) : null };
    },
    cleanup: w.cleanup,
  };
}

function withSetup(opts, fn) {
  const s = setup(opts);
  try { return fn(s); } finally { s.cleanup(); }
}

const GOOD = { probe: [ok({ list: LIST, screen: screen('') })], text: [sent('/compact')], enter: [sent('')] };

const refused = (r, reason, code = 1) => {
  assert.equal(r.status, code, r.stderr);
  assert.equal(r.o.ok, false);
  assert.equal(r.o.reason, reason, JSON.stringify(r.o));
  assert.equal(r.o.code, code);
  assert.ok(r.o.error, 'error text for the human');
};

test('без вызывающей сессии: проба, /compact, Enter; журнал с маркером', () => withSetup({ responses: GOOD }, (s) => {
  const r = s.run([CHILD1, '--min-idle', '58']);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.ok, true);
  assert.equal(r.o.result, 'ok');
  assert.equal(r.o.id, CHILD1);
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe', 'text', 'enter']);
  assert.equal(Buffer.from(r.calls[1].payload.text, 'base64').toString('utf8'), '/compact');
  // Намерение — до каждой отправки; enter-намерение — маркер для хука.
  assert.deepEqual(r.raw.map((e) => [e.result, e.step]), [['sending', 'text'], ['sending', 'enter'], ['ok', undefined]]);
  assert.equal(r.calls[1].logged, 1);
  assert.equal(r.calls[2].logged, 2);
  for (const e of r.raw) {
    assert.equal(e.command, 'compact');
    assert.equal(e.id, CHILD1);
    assert.equal(e.name, '.child-one');
    assert.equal(e.host, 'box-a');
    assert.ok(Number.isInteger(e.atSec) && Math.abs(e.atSec - now()) < 30, JSON.stringify(e));
  }
}));

test('чужая сессия и внутри другой сессии — то же самое: проверки «свои» нет', () => {
  withSetup({ caller: OTHER, responses: GOOD }, (s) => {
    const r = s.run([CHILD1]);
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.o.result, 'ok');
  });
});

test('--dry-run: проба, ничего не печатается и не пишется в журнал', () => withSetup({ responses: GOOD }, (s) => {
  const r = s.run([CHILD1, '--dry-run', '--min-idle', '58']);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.ok, true);
  assert.equal(r.o.result, 'dry-run');
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe']);
  assert.equal(r.raw.length, 0);
}));

test('выключенный автокомпакт — disabled, без ssh, в журнале', () => withSetup({ row: { autoCompact: false }, responses: GOOD }, (s) => {
  const r = s.run([CHILD1]);
  refused(r, 'disabled');
  assert.equal(r.calls.length, 0);
  assert.equal(r.log[0].result, 'refused');
  assert.equal(r.log[0].reason, 'disabled');
  assert.equal(r.log[0].command, 'compact');
}));

test('busy, waiting, question, мёртвая — свои причины без ssh', () => {
  for (const [opts, reason] of [
    [{ child: { status: 'busy' } }, 'not-idle'],
    [{ child: { status: 'waiting', waitingFor: 'approve Bash: git push' } }, 'question'],
    [{ hook: { state: 'question' } }, 'question'],
    [{ child: { pid: 999999999 } }, 'not-running'],
  ]) {
    withSetup({ ...opts, responses: GOOD }, (s) => {
      const r = s.run([CHILD1]);
      refused(r, reason);
      assert.equal(r.calls.length, 0);
    });
  }
});

test('--min-idle меряется от cacheAt; нет cacheAt — отказ', () => {
  withSetup({ agent: { cacheAt: now() - 10 * 60, updated: now() - 59 * 60 }, responses: GOOD }, (s) => {
    const r = s.run([CHILD1, '--min-idle', '58']);
    refused(r, 'min-idle');
    assert.match(r.o.error, /cacheAt/);
    assert.equal(r.calls.length, 0);
  });
  // updated свежее (idle-уведомление), cacheAt старый — можно.
  withSetup({ agent: { cacheAt: now() - 58 * 60 - 5, updated: now() - 60 }, responses: GOOD }, (s) => {
    const r = s.run([CHILD1, '--min-idle', '58']);
    assert.equal(r.status, 0, r.stderr);
  });
  withSetup({ agent: { cacheAt: undefined }, responses: GOOD }, (s) => {
    const r = s.run([CHILD1, '--min-idle', '58']);
    refused(r, 'min-idle');
    assert.match(r.o.error, /no cacheAt/);
  });
  // Без --min-idle простой не проверяется вовсе.
  withSetup({ agent: { cacheAt: undefined }, responses: GOOD }, (s) => {
    assert.equal(s.run([CHILD1]).status, 0);
  });
});

test('нет окна, не WezTerm, нет pid', () => {
  withSetup({ row: { window: null }, responses: GOOD }, (s) => refused(s.run([CHILD1]), 'no-window', 2));
  withSetup({ win: { app: 'WindowsTerminal.exe' }, responses: GOOD }, (s) => {
    const r = s.run([CHILD1]);
    refused(r, 'not-wezterm');
    assert.equal(r.calls.length, 0);
  });
  withSetup({ win: { pid: undefined }, responses: GOOD }, (s) => refused(s.run([CHILD1]), 'not-wezterm'));
});

test('непустое поле (даже /compact) — input-busy; диалог — dialog; чужая панель — wrong-window', () => {
  for (const [box, reason] of [['Стас набирает', 'input-busy'], ['/compact', 'input-busy'], [null, 'dialog']]) {
    withSetup({ responses: { ...GOOD, probe: [ok({ list: LIST, screen: screen(box) })] } }, (s) => {
      const r = s.run([CHILD1]);
      refused(r, reason);
      assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe']);
    });
  }
  withSetup({ responses: { ...GOOD, probe: [ok({ list: JSON.stringify([{ pane_id: 0, title: '✳ someone' }]), screen: screen('') })] } }, (s) => {
    refused(s.run([CHILD1]), 'wrong-window');
  });
});

test('ssh не дошёл — ssh; оборвался после отправки — код 3, unknown', () => {
  withSetup({ responses: { probe: [{ stderr: 'ssh: connect to host nb port 22: Connection refused', status: 255 }] } }, (s) => {
    refused(s.run([CHILD1]), 'ssh');
  });
  withSetup({ responses: { ...GOOD, enter: [{ stdout: 'SENT\r\n', stderr: 'Connection to nb closed', status: 255 }] } }, (s) => {
    const r = s.run([CHILD1]);
    assert.equal(r.status, 3, r.stderr);
    assert.equal(r.o.ok, false);
    assert.equal(r.o.reason, 'unknown');
    assert.equal(r.log.at(-1).result, 'unknown');
  });
});

test('текст не встал в поле — not-landed, Enter не нажат', () => withSetup({ responses: { ...GOOD, text: [sent('')] } }, (s) => {
  const r = s.run([CHILD1]);
  refused(r, 'not-landed');
  assert.deepEqual(r.calls.map((c) => c.payload.mode), ['probe', 'text']);
}));

test('не найдена, лишние аргументы, кривой --min-idle', () => withSetup({ responses: GOOD }, (s) => {
  refused(s.run(['cccccccc-0000-4000-8000-000000000009']), 'not-found', 2);
  refused(s.run([CHILD1, CHILD2]), 'usage');
  refused(s.run([]), 'usage');
  refused(s.run([CHILD1, '--min-idle', 'soon']), 'usage');
  refused(s.run([CHILD1, '--machine', 'box-a']), 'usage');
  assert.equal(s.run([CHILD1]).calls.length, 3);
}));

test('справка называет команду', () => {
  const r = runCli(['--help']);
  assert.match(r.stdout, /session compact <session> \[--min-idle <min>\] \[--dry-run\]/);
});
