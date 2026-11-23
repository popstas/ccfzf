// window icon|badge|icons: явная иконка и значок окна своей сессии из папки
// иконок машины окна. Менеджер — мок на случайном порту.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2, OTHER } from './fixtures.mjs';

async function run(args, reply, { caller = HEAD, state = loadState(), second = null } = {}) {
  const m = await mockManager(reply);
  const m2 = second ? await mockManager(second) : null;
  const t = trackers(now(), { port: m.port });
  if (m2) t['box-b'] = { host: 'box-b', generated: now(), http: { port: m2.port, host: '127.0.0.1' }, windows: {} };
  const w = world({ state, trackers: t, children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync(args, w.env);
    const json = args.includes('--json');
    return { ...r, o: json && r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests, requests2: m2?.requests ?? [] };
  } finally {
    w.cleanup();
    await m.close();
    if (m2) await m2.close();
  }
}

const ok = (body) => () => ({ status: 200, body });
const TG = 'C:\\images\\ico\\telegram.ico';

test('icon: POST /claude-wt/window-icon {id, icon}', async () => {
  const r = await run(['window', 'icon', CHILD1, 'telegram', '--json'], ok({ ok: true, id: CHILD1, icon: TG, applied: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests[0].path, '/claude-wt/window-icon');
  assert.deepEqual(r.requests[0].body, { id: CHILD1, icon: 'telegram' });
  assert.deepEqual(r.o.results, [{ host: 'box-a', url: r.o.results[0].url, code: 0, icon: TG, applied: true }]);
});

test('icon: текст для человека называет имя, сессию и машину', async () => {
  const r = await run(['window', 'icon', CHILD1, 'telegram'], ok({ ok: true, id: CHILD1, icon: TG, applied: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout.trim(), 'set icon telegram for └child-one on box-a');
});

test('badge --clear шлёт null', async () => {
  const r = await run(['window', 'badge', CHILD1, '--clear', '--json'], ok({ ok: true, id: CHILD1, badge: null, applied: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests[0].path, '/claude-wt/window-badge');
  assert.deepEqual(r.requests[0].body, { id: CHILD1, badge: null });
  assert.equal(r.o.results[0].badge, null);
});

test('applied: false — код 0, причина в тексте', async () => {
  const r = await run(['window', 'badge', CHILD1, 'telegram'], ok({ ok: true, id: CHILD1, badge: TG, applied: false, reason: 'no overlay support' }));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /saved badge telegram for └child-one, not applied on box-a: no overlay support/);
});

test('отказ менеджера (unknown icon) — код 1, причина в error', async () => {
  const r = await run(['window', 'icon', CHILD1, 'nope', '--json'], ok({ ok: false, reason: 'unknown icon nope; see claude-wt window icons' }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'unknown icon nope; see claude-wt window icons');
});

test('чужая сессия — отказ до запроса', async () => {
  const r = await run(['window', 'icon', OTHER, 'telegram', '--json'], ok({ ok: true, applied: true }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not your session/);
  assert.equal(r.requests.length, 0);
});

test('без окна — код 2, а с --machine заданное сохраняется там', async () => {
  const r = await run(['window', 'icon', CHILD2, 'telegram', '--json'], ok({ ok: true, applied: false, reason: 'no window' }));
  assert.equal(r.status, 2);
  assert.equal(r.o.error, 'no window');
  assert.equal(r.requests.length, 0);
  const m = await run(['window', 'icon', CHILD2, 'telegram', '--machine', 'box-a', '--json'], ok({ ok: true, icon: TG, applied: false, reason: 'no window' }));
  assert.equal(m.status, 0, m.stderr);
  assert.equal(m.requests.length, 1);
  assert.equal(m.o.results[0].reason, 'no window');
});

test('окна на двух машинах — запрос на обе, худший код', async () => {
  const state = loadState();
  const s = state.sessions.find((x) => x.id === CHILD1);
  s.windows = [{ host: 'box-b', title: '└child-one' }, { host: 'box-a', title: '└child-one' }];
  const r = await run(['window', 'badge', CHILD1, 'telegram', '--json'], ok({ ok: true, badge: TG, applied: true }), {
    state,
    second: () => ({ status: 200, body: { ok: false, reason: 'unknown icon telegram; see claude-wt window icons' } }),
  });
  assert.equal(r.requests.length, 1, 'box-a спрошен');
  assert.equal(r.requests2.length, 1, 'box-b спрошен');
  assert.equal(r.status, 1);
  assert.deepEqual(r.o.results.map((x) => [x.host, x.code]), [['box-b', 1], ['box-a', 0]]);
  assert.match(r.o.error, /^box-b: unknown icon/);
});

test('нет имени и нет --clear — отказ; оба сразу — тоже', async () => {
  for (const args of [['window', 'icon', CHILD1], ['window', 'icon', CHILD1, 'telegram', '--clear']]) {
    const r = await run([...args, '--json'], ok({ ok: true, applied: true }));
    assert.equal(r.status, 1, args.join(' '));
    assert.equal(r.o.error, 'need <name> or --clear');
    assert.equal(r.requests.length, 0);
  }
});

test('window icons — имена построчно и --json', async () => {
  const reply = ok({ ok: true, dir: 'C:\\images\\ico', names: ['planfix', 'telegram'] });
  const r = await run(['window', 'icons'], reply);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout, 'planfix\ntelegram\n');
  assert.equal(r.requests[0].path, '/claude-wt/window-icons');
  const j = await run(['window', 'icons', '--json'], reply);
  assert.deepEqual({ host: j.o.host, dir: j.o.dir, names: j.o.names }, { host: 'box-a', dir: 'C:\\images\\ico', names: ['planfix', 'telegram'] });
});

test('window icons --machine — вызывающая сессия не нужна', async () => {
  const r = await run(['window', 'icons', '--machine', 'box-a', '--json'], ok({ ok: true, dir: 'D:\\ico', names: [] }), { caller: null });
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.o.names, []);
});

test('window icons — отказ менеджера (нет папки) — код 1', async () => {
  const r = await run(['window', 'icons', '--json'], ok({ ok: false, reason: 'icons dir not configured (claudeWt.windowIcons.dir)' }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /icons dir not configured/);
});
