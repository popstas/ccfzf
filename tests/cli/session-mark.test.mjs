// session unread|seen: отметки у трекеров своей сессии, окно не поднимается.
// Менеджер — мок на случайном порту; живой порт тесты не трогают.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2, OTHER } from './fixtures.mjs';

// Мир с трекером box-a на моке; extraManager — второй мок для box-b.
async function mark(kind, target, reply, { caller = HEAD, state = loadState(), second = null, extra = [] } = {}) {
  const m = await mockManager(reply);
  const m2 = second ? await mockManager(second) : null;
  const t = trackers(now(), { port: m.port });
  if (m2) t['box-b'] = { host: 'box-b', generated: now(), http: { port: m2.port, host: '127.0.0.1' }, windows: {} };
  const w = world({ state, trackers: t, children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync(['session', kind, target, '--json', ...extra], w.env);
    return { ...r, o: r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests, requests2: m2?.requests ?? [] };
  } finally {
    w.cleanup();
    await m.close();
    if (m2) await m2.close();
  }
}

const ok = (body) => () => ({ status: 200, body });

test('unread: POST /claude-wt/session-unread {id}, ответ менеджера в results', async () => {
  const r = await mark('unread', CHILD1, ok({ ok: true, ids: [CHILD1], focusedAt: 99, unreadAt: 200 }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests.length, 1);
  assert.equal(r.requests[0].path, '/claude-wt/session-unread');
  assert.deepEqual(r.requests[0].body, { id: CHILD1 });
  assert.equal(r.o.id, CHILD1);
  assert.deepEqual(r.o.results, [{ host: 'box-a', url: r.o.results[0].url, code: 0, ids: [CHILD1], focusedAt: 99, unreadAt: 200 }]);
  assert.equal(r.o.pending, undefined);
});

test('seen: POST /claude-wt/session-seen', async () => {
  const r = await mark('seen', CHILD1, ok({ ok: true, ids: [CHILD1], focusedAt: 300, unreadAt: 0 }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests[0].path, '/claude-wt/session-seen');
  assert.deepEqual(r.requests[0].body, { id: CHILD1 });
  assert.equal(r.o.results[0].focusedAt, 300);
});

test('requested: true у менеджера — pending: true, код 0', async () => {
  const r = await mark('unread', CHILD1, ok({ ok: true, ids: [CHILD1], focusedAt: 1, unreadAt: 2, requested: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.pending, true);
});

test('старый менеджер ({ok:true} без отметки) — код 0 с предупреждением', async () => {
  const r = await mark('unread', CHILD1, ok({ ok: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stderr, /warning: box-a: manager did not report unreadAt/);
  const s = await mark('seen', CHILD1, ok({ ok: true }));
  assert.equal(s.status, 0, s.stderr);
  assert.match(s.stderr, /only the taskbar button/);
});

test('отказ менеджера — код 1 с причиной', async () => {
  const r = await mark('unread', CHILD1, ok({ ok: false, reason: 'no agent record yet' }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'no agent record yet');
});

test('менеджер не знает сессии — код 2', async () => {
  const r = await mark('seen', CHILD1, ok({ ok: false, reason: `unknown session ${CHILD1}` }));
  assert.equal(r.status, 2);
  assert.match(r.o.error, /unknown session/);
});

test('чужая сессия — отказ, запроса нет', async () => {
  const r = await mark('unread', OTHER, ok({ ok: true, unreadAt: 1 }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not your session/);
  assert.equal(r.requests.length, 0);
});

test('без окна — код 2, запроса нет', async () => {
  const r = await mark('unread', CHILD2, ok({ ok: true, unreadAt: 1 }));
  assert.equal(r.status, 2);
  assert.equal(r.o.error, 'no window');
  assert.equal(r.requests.length, 0);
});

test('без CLAUDE_CODE_SESSION_ID — отказ', async () => {
  const r = await mark('seen', CHILD1, ok({ ok: true }), { caller: null });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /CLAUDE_CODE_SESSION_ID/);
  assert.equal(r.requests.length, 0);
});

test('окна на двух машинах — просьба каждой; отказ одной не отменяет другую', async () => {
  const state = loadState();
  const s = state.sessions.find((x) => x.id === CHILD1);
  s.windows = [{ host: 'box-b', title: '└child-one' }, { host: 'box-a', title: '└child-one' }];
  const r = await mark('unread', CHILD1, ok({ ok: true, unreadAt: 5 }), {
    state,
    second: () => ({ status: 200, body: { ok: false, reason: 'boom' } }),
  });
  assert.equal(r.requests.length, 1, 'box-a спрошен');
  assert.equal(r.requests2.length, 1, 'box-b спрошен');
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'box-b: boom');
  assert.deepEqual(r.o.results.map((x) => [x.host, x.code]), [['box-b', 1], ['box-a', 0]]);
});

test('таймаут — код 3', async () => {
  const m = await mockManager(() => 'hang');
  const w = world({ state: loadState(), trackers: trackers(now(), { port: m.port }), children: CHILDREN, heads: HEADS, caller: HEAD });
  try {
    const r = await runCliAsync(['session', 'seen', CHILD1, '--json'], { ...w.env, CLAUDE_WT_TIMEOUT_MS: '300' });
    assert.equal(r.status, 3, r.stderr);
  } finally {
    w.cleanup();
    await m.close();
  }
});
