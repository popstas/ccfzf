// window focus: только поднять существующее окно своей сессии.
// Менеджер — мок на случайном порту; живой порт тесты не трогают.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { managerFor, post, answer } from '../../cli/lib/manager.mjs';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2, OTHER } from './fixtures.mjs';

// Мир с трекером box-a, указывающим на мок, и вызов CLI.
async function focus(target, reply, { caller = HEAD, tracker, extra = [], env = {} } = {}) {
  const m = await mockManager(reply);
  const t = trackers(now(), { port: m.port });
  if (tracker) Object.assign(t['box-a'], tracker);
  const w = world({ state: loadState(), trackers: t, children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync(['window', 'focus', target, '--json', ...extra], { ...w.env, ...env });
    return { ...r, o: r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests };
  } finally {
    w.cleanup();
    await m.close();
  }
}

const ok = (body) => () => ({ status: 200, body });

test('тело запроса несёт raiseOnly:true', async () => {
  const r = await focus(CHILD1, ok({ ok: true, action: 'focus', foreground: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests.length, 1);
  assert.equal(r.requests[0].method, 'POST');
  assert.equal(r.requests[0].path, '/claude-wt/focus');
  assert.deepEqual(r.requests[0].body, { id: CHILD1, raiseOnly: true });
  assert.equal(r.o.foreground, true);
  assert.equal(r.o.id, CHILD1);
  assert.equal(r.o.host, 'box-a');
});

test('сессия по имени', async () => {
  const r = await focus('└child-one', ok({ ok: true, action: 'focus', foreground: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests[0].body.id, CHILD1);
});

test('чужая сессия — отказ, запроса нет', async () => {
  const r = await focus(OTHER, ok({ ok: true, foreground: true }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not your session/);
  assert.equal(r.requests.length, 0);
  // Исполнитель не трогает окно своего head.
  const c = await focus(HEAD, ok({ ok: true, foreground: true }), { caller: CHILD1 });
  assert.equal(c.status, 1);
  assert.equal(c.requests.length, 0);
});

test('без CLAUDE_CODE_SESSION_ID — отказ, запроса нет', async () => {
  const r = await focus(CHILD1, ok({ ok: true, foreground: true }), { caller: null });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /CLAUDE_CODE_SESSION_ID/);
  assert.equal(r.requests.length, 0);
});

test('без окна — код 2, запроса нет', async () => {
  const r = await focus(CHILD2, ok({ ok: true, foreground: true }));
  assert.equal(r.status, 2);
  assert.equal(r.o.error, 'no window');
  assert.equal(r.requests.length, 0, 'старый менеджер открыл бы окно — не зовём');
});

test('сессии нет — код 2', async () => {
  const r = await focus('no-such-session', ok({ ok: true }));
  assert.equal(r.status, 2);
  assert.match(r.o.error, /not found/);
});

test('foreground:false — код 1', async () => {
  const r = await focus(CHILD1, ok({ ok: true, action: 'focus', foreground: false }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'window did not come to front');
  assert.equal(r.o.foreground, false);
});

test('старый менеджер без foreground — код 0 и предупреждение', async () => {
  const r = await focus(CHILD1, ok({ ok: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.foreground, null);
  assert.match(r.stderr, /manager did not report foreground/);
});

test('менеджер открыл окно вместо подъёма — отказ, не успех', async () => {
  const r = await focus(CHILD1, ok({ ok: true, action: 'restore' }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /restore/);
});

test('ok:false от менеджера — код 1 с его reason', async () => {
  const r = await focus(CHILD1, ok({ ok: false, reason: 'no window' }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'no window');
});

test('не-2xx: тело с reason и пустое', async () => {
  const t = await focus(CHILD1, () => ({ status: 429, body: { ok: false, reason: 'throttled', error: 'throttled' } }));
  assert.equal(t.status, 1);
  assert.equal(t.o.error, 'throttled');
  const e = await focus(CHILD1, () => ({ status: 500, body: { error: 'boom' } }));
  assert.equal(e.status, 1);
  assert.equal(e.o.error, 'boom');
});

test('не-2xx без тела — HTTP <status>', async () => {
  for (const raw of ['', '{}']) {
    const r = await focus(CHILD1, () => ({ status: 502, raw }));
    assert.equal(r.status, 1, JSON.stringify(raw));
    assert.equal(r.o.error, 'HTTP 502');
  }
});

test('2xx без ok:true — не успех', async () => {
  const html = await focus(CHILD1, () => ({ status: 200, raw: '<html>proxy</html>' }));
  assert.equal(html.status, 1);
  assert.match(html.o.error, /unexpected answer from manager \(HTTP 200\)/);
  const empty = await focus(CHILD1, () => ({ status: 200, raw: '{}' }));
  assert.equal(empty.status, 1, 'тело без ok — не ответ менеджера');
});

test('обрыв после отправки — код 3, исход неизвестен', async () => {
  const r = await focus(CHILD1, () => 'destroy');
  assert.equal(r.requests.length, 1, 'запрос дошёл');
  assert.equal(r.status, 3);
  assert.match(r.o.error, /outcome unknown/);
});

test('протухший трекер — отказ с именем файла', async () => {
  const r = await focus(CHILD1, ok({ ok: true, foreground: true }), { tracker: { generated: now() - 3600 } });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /tracker stale: .*box-a\.json/);
  assert.equal(r.requests.length, 0);
});

test('таймаут — код 3', async () => {
  const r = await focus(CHILD1, () => 'hang', { env: { CLAUDE_WT_TIMEOUT_MS: '300' } });
  assert.equal(r.status, 3);
  assert.equal(r.o.error, 'timeout');
  assert.equal(r.requests.length, 1);
});

test('--url перебивает трекер, даже протухший', async () => {
  const m = await mockManager(ok({ ok: true, action: 'focus', foreground: true }));
  try {
    const r = await focus(CHILD1, ok({}), { tracker: { generated: 0 }, extra: ['--url', `${m.url}/`] });
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.requests.length, 0, 'трекер не спрашивали');
    assert.equal(m.requests.length, 1);
  } finally {
    await m.close();
  }
});

test('managerFor: нет трекера — 2, нет http — 1, --machine', () => {
  const t = [
    { file: 'box-a.json', host: 'box-a', http: { host: 'a.lan', port: 1 }, fresh: true },
    { file: 'box-m.json', host: 'box-m', http: null, fresh: true },
  ];
  assert.deepEqual(managerFor({ host: 'box-a', trackers: t }), { url: 'http://a.lan:1', host: 'box-a', source: 'box-a.json' });
  assert.equal(managerFor({ host: 'box-z', trackers: t }).code, 2);
  const m = managerFor({ host: 'box-m', trackers: t });
  assert.equal(m.code, 1);
  assert.equal(m.error, 'no http manager for box-m');
  assert.equal(managerFor({ host: 'box-m', machine: 'box-a', trackers: t }).url, 'http://a.lan:1');
  assert.equal(managerFor({ host: null, trackers: t }).code, 2);
});

test('post: отказ соединения — не таймаут', async () => {
  // Свободный порт: занять и сразу отпустить.
  const m = await mockManager(() => ({ status: 200, body: { ok: true } }));
  await m.close();
  const r = await post(m.url, '/x', {}, { timeoutMs: 2000 });
  assert.ok(r.error && !r.timeout && !r.lost, JSON.stringify(r));
  assert.match(r.error, /ECONNREFUSED/);
  assert.equal(answer(r).code, 1);
  // Порт, который fetch не пускает вовсе, — запрос не ушёл.
  assert.equal(answer(await post('http://127.0.0.1:1', '/x', {}, { timeoutMs: 2000 })).code, 1);
});
