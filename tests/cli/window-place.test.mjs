// window place <session> --zone M:P: перенос существующего окна своей сессии в зону.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2, OTHER } from './fixtures.mjs';
import { parseZone } from '../../cli/lib/commands/window-place.mjs';

async function place(target, reply, { caller = HEAD, zone = ['--zone', '3:1'], extra = [], state = loadState() } = {}) {
  const m = await mockManager(reply);
  const w = world({ state, trackers: trackers(now(), { port: m.port }), children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync(['window', 'place', target, ...zone, '--json', ...extra], w.env);
    return { ...r, o: r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests };
  } finally {
    w.cleanup();
    await m.close();
  }
}

const ok = (body) => () => ({ status: 200, body });

test('тело: mode zone, id и зона целыми числами', async () => {
  const r = await place(CHILD1, ok({ ok: true, placed: 1, zone: '3:1' }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests.length, 1);
  assert.equal(r.requests[0].path, '/claude-wt/place');
  assert.deepEqual(r.requests[0].body, { mode: 'zone', id: CHILD1, zone: { monitor: 3, position: 1 } });
  assert.equal(r.o.placed, 1);
  assert.equal(r.o.zone, '3:1');
  assert.equal(r.o.host, 'box-a');
});

test('--zone=M:P тоже разбирается', async () => {
  const r = await place(HEAD, ok({ ok: true, placed: 1 }), { zone: ['--zone=1:4'] });
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.requests[0].body.zone, { monitor: 1, position: 4 });
});

test('placed:0 — успех: окно уже в зоне', async () => {
  const r = await place(HEAD, ok({ ok: true, placed: 0, zone: '3:1' }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.placed, 0);
  assert.equal(r.o.warnings, undefined);
});

test('кривой или пропущенный --zone — код 1 до запроса', async () => {
  for (const zone of [[], ['--zone', '3'], ['--zone', '0:1'], ['--zone', '3:x'], ['--zone', '-1:2'], ['--zone', '3:1:2']]) {
    const r = await place(HEAD, ok({ ok: true, placed: 1 }), { zone });
    assert.equal(r.status, 1, `${zone.join(' ')}: ${r.stderr}`);
    assert.equal(r.requests.length, 0, zone.join(' '));
  }
  const r = await place(HEAD, ok({ ok: true, placed: 1 }), { zone: ['--zone', 'a:b'] });
  assert.match(r.o.error, /bad --zone a:b/);
});

test('кривой --zone отвергается и вне Claude Code — раньше проверки вызывающего', async () => {
  const r = await place(HEAD, ok({ ok: true }), { caller: null, zone: ['--zone', 'x'] });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /bad --zone/);
});

test('чужая сессия — код 1, запроса нет', async () => {
  const r = await place(OTHER, ok({ ok: true, placed: 1 }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not your session/);
  assert.equal(r.requests.length, 0);
  const c = await place(HEAD, ok({ ok: true, placed: 1 }), { caller: CHILD1 });
  assert.equal(c.status, 1);
  assert.equal(c.requests.length, 0);
});

test('без CLAUDE_CODE_SESSION_ID — код 1', async () => {
  const r = await place(HEAD, ok({ ok: true, placed: 1 }), { caller: null });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /CLAUDE_CODE_SESSION_ID/);
  assert.equal(r.requests.length, 0);
});

test('у сессии нет окна — код 2 без запроса', async () => {
  const r = await place(CHILD2, ok({ ok: true, placed: 1 }));
  assert.equal(r.status, 2);
  assert.equal(r.o.error, 'no window');
  assert.equal(r.requests.length, 0);
});

test('менеджер ответил no window — код 2', async () => {
  const r = await place(HEAD, ok({ ok: false, reason: 'no window' }));
  assert.equal(r.status, 2);
  assert.equal(r.o.error, 'no window');
});

test('чужая зона — код 1 с причиной менеджера', async () => {
  const reason = 'zone 3:9 is not in the FancyZones layout of monitor 3 (zones 1..4)';
  const r = await place(HEAD, ok({ ok: false, reason }), { zone: ['--zone', '3:9'] });
  assert.equal(r.status, 1);
  assert.equal(r.o.error, reason);
});

test('старый менеджер (bad payload) — код 1 с подсказкой', async () => {
  const r = await place(HEAD, ok({ ok: false, reason: 'bad payload' }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /does not know mode zone/);
});

test('throttled — код 1', async () => {
  const r = await place(HEAD, () => ({ status: 429, body: { ok: false, reason: 'throttled', error: 'throttled' } }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'throttled');
});

test('таймаут — код 3', async () => {
  const m = await mockManager(() => 'hang');
  const w = world({ state: loadState(), trackers: trackers(now(), { port: m.port }), children: CHILDREN, heads: HEADS, caller: HEAD });
  try {
    const r = await runCliAsync(['window', 'place', HEAD, '--zone', '3:1', '--json'], { ...w.env, CLAUDE_WT_TIMEOUT_MS: '300' });
    assert.equal(r.status, 3, r.stderr);
  } finally {
    w.cleanup();
    await m.close();
  }
});

test('--machine не машины окна — код 1 без запроса', async () => {
  const r = await place(HEAD, ok({ ok: true, placed: 1 }), { extra: ['--machine', 'box-m'] });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not the window's machine/);
  assert.equal(r.requests.length, 0);
});

test('parseZone', () => {
  assert.deepEqual(parseZone('3:1'), { zone: { monitor: 3, position: 1 } });
  assert.deepEqual(parseZone(' 12 : 4 '), { zone: { monitor: 12, position: 4 } });
  for (const bad of [undefined, true, '', '3', '0:1', '1:0', '1.5:2', '3:1:2']) assert.ok(parseZone(bad).error, String(bad));
});
