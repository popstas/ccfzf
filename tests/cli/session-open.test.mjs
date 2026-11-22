// session open: открыть окно своей сессии, когда окна нет (решение Стаса 2026-11-22 — без спроса).
// Окно есть — отказ без запроса: второе окно той же сессии хуже любого отказа.
// Менеджер — мок на случайном порту; живой порт тесты не трогают.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readTrackers } from '../../cli/lib/sources.mjs';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2, OTHER, CLOSED } from './fixtures.mjs';

// В фикстуре CHILD2 живая и без окна; открывать можно только закрытую свою сессию,
// поэтому по умолчанию она здесь закрыта (live:false), а liveChild2 оставляет её живой.
async function open(target, reply, { caller = HEAD, extra = [], env = {}, edit, liveChild2 = false } = {}) {
  const m = await mockManager(reply);
  const t = trackers(now(), { port: m.port });
  if (edit) edit(t);
  const state = loadState();
  if (!liveChild2) state.sessions.find((x) => x.id === CHILD2).live = false;
  const w = world({ state, trackers: t, children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync(['session', 'open', target, '--json', ...extra], { ...w.env, ...env });
    return { ...r, o: r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests };
  } finally {
    w.cleanup();
    await m.close();
  }
}

const ok = (body) => () => ({ status: 200, body });

test('своя без окна: тело {id, action:terminal, cwd}, ответ action — код 0', async () => {
  const r = await open(CHILD2, ok({ ok: true, action: 'resume' }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.requests.length, 1);
  assert.equal(r.requests[0].path, '/claude-wt/session-open');
  // Без action менеджер ничего не делает и отвечает {ok:true} — молчаливый успех.
  assert.deepEqual(r.requests[0].body, { id: CHILD2, action: 'terminal', cwd: '/work/demo' });
  assert.equal(r.o.action, 'resume');
  assert.equal(r.o.pending, false);
  assert.equal(r.o.host, 'box-a');
});

test('pending — та же сессия уже открывается: код 0, pending', async () => {
  const r = await open(CHILD2, ok({ ok: true, action: 'pending' }));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.action, 'pending');
  assert.equal(r.o.pending, true);
});

test('чужая — 1 без запроса; с окном — 1 без запроса', async () => {
  let r = await open(OTHER, ok({ ok: true, action: 'resume' }));
  assert.equal(r.status, 1);
  assert.match(r.o.error, /not your session/);
  assert.equal(r.requests.length, 0);
  r = await open(CHILD1, ok({ ok: true, action: 'resume' }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'window exists, use window focus');
  assert.equal(r.requests.length, 0);
  r = await open(CLOSED, ok({ ok: true }));
  assert.equal(r.status, 1, 'закрытая чужая — тоже чужая');
  assert.equal(r.requests.length, 0);
});

test('без CLAUDE_CODE_SESSION_ID — отказ, запроса нет', async () => {
  const r = await open(CHILD2, ok({ ok: true, action: 'resume' }), { caller: null });
  assert.equal(r.status, 1);
  assert.equal(r.requests.length, 0);
});

test('таймаут: код 3, «do not retry», один запрос', async () => {
  const r = await open(CHILD2, () => 'hang', { env: { CLAUDE_WT_TIMEOUT_MS: '300' } });
  assert.equal(r.status, 3, r.stderr);
  assert.equal(r.o.error, 'outcome unknown — do not retry; check with tree in 30 s');
  assert.equal(r.requests.length, 1);
  const d = await open(CHILD2, () => 'destroy');
  assert.equal(d.status, 3, 'обрыв после отправки — тоже неизвестно');
  assert.match(d.o.error, /do not retry/);
});

test('отказ менеджера: 500 {error} и {ok:false, reason} — код 1 с причиной', async () => {
  let r = await open(CHILD2, () => ({ status: 500, body: { error: 'не удалось открыть' } }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'не удалось открыть');
  r = await open(CHILD2, ok({ ok: false, reason: 'nope' }));
  assert.equal(r.status, 1);
  assert.equal(r.o.error, 'nope');
  r = await open(CHILD2, ok({ action: 'resume' }));
  assert.equal(r.status, 1, 'без ok:true — не успех');
});

test('машина без openSession — 1 без запроса, и с --machine тоже', async () => {
  let r = await open(CHILD2, ok({ ok: true, action: 'resume' }), { edit: (t) => { t['box-a'].openSession = false; } });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /openSession/);
  assert.equal(r.requests.length, 0);
  r = await open(CHILD2, ok({ ok: true, action: 'resume' }), {
    extra: ['--machine', 'box-m'],
    edit: (t) => { t['box-m'].http = { port: 1, host: '127.0.0.1' }; },
  });
  assert.equal(r.status, 1);
  assert.match(r.o.error, /box-m.*openSession|openSession.*box-m/);
  assert.equal(r.requests.length, 0);
});

test('--url на машину без openSession — отказ; на неизвестный адрес — идёт', async () => {
  const m = await mockManager(ok({ ok: true, action: 'resume' }));
  try {
    const r = await open(CHILD2, ok({ ok: true }), { extra: ['--url', 'http://box-m.lan:1'], edit: (t) => { t['box-m'].http = { port: 1, host: 'box-m.lan' }; } });
    assert.equal(r.status, 1);
    assert.match(r.o.error, /openSession/);
    const u = await open(CHILD2, ok({ ok: true }), { extra: ['--url', m.url] });
    assert.equal(u.status, 0, u.stderr);
    assert.equal(m.requests.length, 1);
  } finally { await m.close(); }
});

test('readTrackers: openSession как в ccfzf — нет поля или мусор = true, false = false', () => {
  const w = world({ trackers: { a: { host: 'a', generated: 1 }, b: { host: 'b', generated: 1, openSession: false }, c: { host: 'c', generated: 1, openSession: 'no' } } });
  try {
    const t = Object.fromEntries(readTrackers(w.windowsDir, 1).map((x) => [x.host, x.openSession]));
    assert.deepEqual(t, { a: true, b: false, c: true });
  } finally { w.cleanup(); }
});

test('две свежие машины: окно открывается там, где окно вызывающего, а не у свежайшего трекера', async () => {
  const other = await mockManager(ok({ ok: true, action: 'resume' }));
  try {
    const edit = (t) => {
      t['box-a'].generated = now() - 60;
      t['box-c'] = { host: 'box-c', generated: now(), http: { port: other.port, host: '127.0.0.1' }, windows: {} };
    };
    // head стоит на box-a — его ребёнок открывается рядом.
    const r = await open(CHILD2, ok({ ok: true, action: 'resume' }), { edit });
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.o.host, 'box-a');
    assert.equal(r.requests.length, 1);
    assert.equal(other.requests.length, 0);
    // Вызывающий — ребёнок без окна: берётся окно его предка (head на box-a).
    const c = await open(CHILD2, ok({ ok: true, action: 'resume' }), { edit, caller: CHILD2 });
    assert.equal(c.status, 0, c.stderr);
    assert.equal(c.o.host, 'box-a');
    assert.equal(other.requests.length, 0);
  } finally { await other.close(); }
});

test('живая без окна (только что открыта или окно отвалилось): код 1, запроса нет — второй claude на ту же сессию нельзя', async () => {
  const r = await open(CHILD2, ok({ ok: true, action: 'resume' }), { liveChild2: true });
  assert.equal(r.status, 1, r.stderr);
  assert.equal(r.o.error, "session is running without a window — wait for its window (just spawned) or use the picker's Reopen (disconnected)");
  assert.equal(r.requests.length, 0);
});

test('только что открытый ребёнок: в --state его ещё нет, claude agents знает — код 1, запроса нет', async () => {
  const NEW = 'aaaaaaaa-0000-4000-8000-000000000009';
  const m = await mockManager(ok({ ok: true, action: 'resume' }));
  const w = world({
    state: loadState(), trackers: trackers(now(), { port: m.port }), heads: HEADS, caller: HEAD,
    children: [...CHILDREN, { sessionId: NEW, headId: HEAD, createdAt: 40 }],
    agents: [{ sessionId: NEW, name: '.new-kid', status: 'busy' }],
  });
  try {
    const r = await runCliAsync(['session', 'open', NEW, '--json'], w.env);
    assert.equal(r.status, 1, r.stderr);
    assert.match(JSON.parse(r.stdout).error, /^session is running without a window/);
    assert.equal(m.requests.length, 0);
  } finally { w.cleanup(); await m.close(); }
});
