// window taskbar hide|show|auto: кнопка окна своей сессии на панели задач.
// Менеджер — мок на случайном порту.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCliAsync, world, mockManager, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2 } from './fixtures.mjs';

async function run(args, reply, { caller = HEAD, state = loadState() } = {}) {
  const m = await mockManager(reply);
  const t = trackers(now(), { port: m.port });
  const w = world({ state, trackers: t, children: CHILDREN, heads: HEADS, caller });
  try {
    const r = await runCliAsync(args, w.env);
    const json = args.includes('--json');
    return { ...r, o: json && r.stdout ? JSON.parse(r.stdout) : null, requests: m.requests };
  } finally {
    w.cleanup();
    await m.close();
  }
}

const ok = (body) => () => ({ status: 200, body });

test('hide и show шлют режим телом запроса', async () => {
  for (const [mode, text] of [['hide', 'hidden'], ['show', 'shown']]) {
    const r = await run(['window', 'taskbar', CHILD1, mode], ok({ ok: true, id: CHILD1, taskbar: mode, applied: true }));
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.requests[0].path, '/claude-wt/window-taskbar');
    assert.deepEqual(r.requests[0].body, { id: CHILD1, taskbar: mode });
    assert.equal(r.stdout.trim(), `taskbar ${text} for └child-one on box-a`);
  }
});

test('auto шлёт явный null', async () => {
  const r = await run(['window', 'taskbar', CHILD1, 'auto'], ok({ ok: true, id: CHILD1, taskbar: null, applied: true }));
  assert.equal(r.status, 0, r.stderr);
  assert.ok('taskbar' in r.requests[0].body, 'ключ есть, менеджер отвергает его отсутствие');
  assert.deepEqual(r.requests[0].body, { id: CHILD1, taskbar: null });
  assert.equal(r.stdout.trim(), 'taskbar auto for └child-one on box-a');
});

test('applied: false — код 0, причина в тексте', async () => {
  const r = await run(['window', 'taskbar', CHILD1, 'hide'], ok({ ok: true, id: CHILD1, taskbar: 'hide', applied: false, reason: 'no window' }));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /saved taskbar hide for └child-one, not applied on box-a: no window/);
});

test('плохой режим или его отсутствие — код 1 до запроса', async () => {
  for (const args of [['window', 'taskbar', CHILD1, 'nope'], ['window', 'taskbar', CHILD1]]) {
    const r = await run([...args, '--json'], ok({ ok: true, applied: true }));
    assert.equal(r.status, 1, args.join(' '));
    assert.equal(r.o.error, 'need hide, show or auto');
    assert.equal(r.requests.length, 0);
  }
});

test('без окна — код 2, запроса нет', async () => {
  const r = await run(['window', 'taskbar', CHILD2, 'hide', '--json'], ok({ ok: true, applied: true }));
  assert.equal(r.status, 2);
  assert.equal(r.o.error, 'no window');
  assert.equal(r.requests.length, 0);
});

test('404 без reason — текст про старый менеджер', async () => {
  const r = await run(['window', 'taskbar', CHILD1, 'hide', '--json'], () => ({ status: 404, body: {} }));
  assert.notEqual(r.status, 0);
  assert.equal(r.o.error, 'manager has no /claude-wt/window-taskbar (old manager?)');
});
