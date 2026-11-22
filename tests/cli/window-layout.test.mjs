// window layout <head>: раскладка своей группы head одним запросом group.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, GRAND, OTHER } from './fixtures.mjs';

async function layout(target, reply, { caller = HEAD, state = loadState() } = {}) {
  const m = await mockManager(reply);
  const w = world({ state, trackers: trackers(now(), { port: m.port }), children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync(['window', 'layout', target, '--json'], w.env);
    return { ...r, o: r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests };
  } finally {
    w.cleanup();
    await m.close();
  }
}

const placed = (n) => () => ({ status: 200, body: { ok: true, placed: n } });

test('тело group с selected=head', async () => {
  const r = await layout(HEAD, placed(3));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests.length, 1);
  assert.equal(r.requests[0].path, '/claude-wt/place');
  assert.deepEqual(r.requests[0].body, { mode: 'group', groups: [[HEAD, CHILD1, GRAND]], selected: HEAD });
  assert.equal(r.o.placed, 3);
  assert.deepEqual(r.o.group, [HEAD, CHILD1, GRAND]);
});

test('placed:0 — успех: группа уже разложена', async () => {
  const r = await layout(HEAD, placed(0));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.placed, 0);
  assert.equal(r.o.warnings, undefined);
});

test('дети без окна не входят', async () => {
  const r = await layout(HEAD, placed(3));
  assert.ok(!r.requests[0].body.groups[0].includes('aaaaaaaa-0000-4000-8000-000000000003'));
});

test('окна на другой машине не входят', async () => {
  const st = loadState();
  st.sessions.find((s) => s.id === GRAND).window.host = 'box-b';
  const r = await layout(HEAD, placed(2), { state: st });
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.requests[0].body.groups, [[HEAD, CHILD1]]);
});

test('чужой head — отказ', async () => {
  const r = await layout(OTHER, placed(2));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not your session/);
  assert.equal(r.requests.length, 0);
  // Исполнитель не раскладывает группу своего head.
  const c = await layout(HEAD, placed(2), { caller: CHILD1 });
  assert.equal(c.status, 1);
  assert.equal(c.requests.length, 0);
});

test('свой потомок как head — его подгруппа', async () => {
  const r = await layout(CHILD1, placed(2));
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.requests[0].body, { mode: 'group', groups: [[CHILD1, GRAND]], selected: CHILD1 });
});

test('одно окно — nothing to lay out без запроса', async () => {
  const r = await layout(GRAND, placed(1));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'nothing to lay out');
  assert.equal(r.requests.length, 0);
});

test('у head нет окна — код 2 без запроса', async () => {
  const st = loadState();
  st.sessions.find((s) => s.id === HEAD).window = null;
  const r = await layout(HEAD, placed(2), { state: st });
  assert.equal(r.status, 2);
  assert.match(r.o.error, /no window/);
  assert.equal(r.requests.length, 0);
});

test('throttled — код 1', async () => {
  const r = await layout(HEAD, () => ({ status: 429, body: { ok: false, reason: 'throttled', error: 'throttled' } }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'throttled');
});

test('ok:false раскладки — код 1 с reason', async () => {
  const r = await layout(HEAD, () => ({ status: 200, body: { ok: false, reason: 'no windows matched' } }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'no windows matched');
});
