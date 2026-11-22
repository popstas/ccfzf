// snapshot list / restore: снимки трекеров с http, восстановление только своих сессий.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2, OTHER } from './fixtures.mjs';

const OWN_SNAP = '2026-01-01T10-00-00'; // HEAD + CHILD1, box-a, created 200
const MIXED_SNAP = '2026-01-01T11-00-00'; // HEAD + OTHER, box-a, created 300
const MAC_SNAP = '2026-01-01T12-00-00'; // box-m без http, created 400

async function cli(args, { reply = () => ({ status: 200, body: { ok: true } }), caller = HEAD, state = loadState() } = {}) {
  const m = await mockManager(reply);
  const w = world({ state, trackers: trackers(now(), { port: m.port }), children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync([...args, '--json'], w.env);
    return { ...r, o: r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests };
  } finally {
    w.cleanup();
    await m.close();
  }
}

test('list без снимков мака', async () => {
  const r = await cli(['snapshot', 'list']);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.o.snapshots.map((x) => x.id), [MIXED_SNAP, OWN_SNAP], 'свежие сверху, мака нет');
  assert.equal(r.o.snapshots[1].own, true);
  assert.equal(r.o.snapshots[0].own, false);
  assert.deepEqual(r.o.snapshots[1].sessions, [HEAD, CHILD1]);
});

test('list работает и без вызывающей сессии', async () => {
  const r = await cli(['snapshot', 'list'], { caller: null });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.snapshots.length, 2);
});

test('last — свежий свой', async () => {
  const r = await cli(['snapshot', 'restore', 'last']);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests.length, 1);
  assert.equal(r.requests[0].path, '/claude-wt/snapshot-restore');
  assert.deepEqual(r.requests[0].body, { id: OWN_SNAP, sessionIds: [HEAD, CHILD1] }, 'не MIXED, хоть он свежее');
});

test('успех — pending и код 0', async () => {
  const r = await cli(['snapshot', 'restore', OWN_SNAP]);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.pending, true);
  assert.equal(r.o.id, OWN_SNAP);
  const h = await (async () => {
    const m = await mockManager(() => ({ status: 200, body: { ok: true } }));
    const w = world({ state: loadState(), trackers: trackers(now(), { port: m.port }), children: CHILDREN, heads: HEADS, caller: HEAD });
    try { return await runCliAsync(['snapshot', 'restore', OWN_SNAP], w.env); } finally { w.cleanup(); await m.close(); }
  })();
  assert.match(h.stdout, /accepted, outcome unknown — see tracker log/);
});

test('чужая сессия в снимке — отказ', async () => {
  const r = await cli(['snapshot', 'restore', MIXED_SNAP]);
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not yours/);
  assert.match(r.o.error, new RegExp(OTHER));
  assert.deepEqual(r.o.foreign, [OTHER]);
  assert.equal(r.requests.length, 0);
});

test('--sessions — только названные свои из снимка', async () => {
  const r = await cli(['snapshot', 'restore', MIXED_SNAP, '--sessions', 'demo-head']);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.requests[0].body, { id: MIXED_SNAP, sessionIds: [HEAD] });
});

test('--sessions вне снимка — отказ', async () => {
  const r = await cli(['snapshot', 'restore', OWN_SNAP, '--sessions', `${HEAD},${CHILD2}`]);
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not in snapshot/);
  assert.equal(r.requests.length, 0);
});

test('--sessions с чужой — отказ', async () => {
  const r = await cli(['snapshot', 'restore', MIXED_SNAP, '--sessions', `${HEAD},${OTHER}`]);
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not your session/);
  assert.equal(r.requests.length, 0);
});

test('снимок мака или неизвестный — код 2', async () => {
  for (const id of [MAC_SNAP, 'no-such-snapshot']) {
    const r = await cli(['snapshot', 'restore', id]);
    assert.equal(r.status, 2, id);
    assert.match(r.o.error, /snapshot not found/);
  }
});

test('своих снимков нет — last отказывает кодом 2', async () => {
  const r = await cli(['snapshot', 'restore', 'last'], { caller: CHILD1 });
  assert.equal(r.status, 2);
  assert.match(r.o.error, /no snapshot of your own/);
});

test('без вызывающей сессии restore отказывает', async () => {
  const r = await cli(['snapshot', 'restore', OWN_SNAP], { caller: null });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /CLAUDE_CODE_SESSION_ID/);
  assert.equal(r.requests.length, 0);
});

test('throttled restore — код 1', async () => {
  const r = await cli(['snapshot', 'restore', OWN_SNAP], { reply: () => ({ status: 429, body: { ok: false, reason: 'throttled' } }) });
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'throttled');
});
