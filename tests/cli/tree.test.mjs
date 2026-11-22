// tree: вся картина одним вызовом, «свои» помечены.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCli, world, now } from './helpers.mjs';
import { loadState, trackers, CHILDREN, HEADS, HEAD, CHILD1, CHILD2, GRAND, OTHER, CLOSED } from './fixtures.mjs';

const tree = (caller) => {
  const w = world({ state: loadState(), trackers: trackers(now()), children: CHILDREN, heads: HEADS, caller });
  try {
    const r = runCli(['tree', '--json'], w.env);
    return { ...r, o: r.stdout ? JSON.parse(r.stdout) : null };
  } finally {
    w.cleanup();
  }
};

const byId = (o) => Object.fromEntries(o.sessions.map((s) => [s.id, s]));

test('без CLAUDE_CODE_SESSION_ID tree работает, own везде false', () => {
  const r = tree(undefined);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.caller, null);
  assert.equal(r.o.sessions.length, 6);
  assert.ok(r.o.sessions.every((s) => s.own === false));
  assert.ok(r.o.snapshots.every((s) => s.own === false));
});

test('tree помечает своих и head', () => {
  const r = tree(HEAD);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.caller, HEAD);
  const s = byId(r.o);
  for (const id of [HEAD, CHILD1, CHILD2, GRAND]) assert.equal(s[id].own, true, id);
  for (const id of [OTHER, CLOSED]) assert.equal(s[id].own, false, id);
  assert.equal(s[HEAD].head, true, 'есть отметка head');
  assert.equal(s[CHILD1].head, true, 'у ребёнка свой ребёнок — тоже head');
  assert.equal(s[CHILD2].head, false);
  assert.equal(s[HEAD].parent, null);
  assert.equal(s[CHILD1].parent, HEAD);
  assert.equal(s[GRAND].parent, CHILD1, 'родитель — по записи children, даже если в state его нет');
  assert.deepEqual(s[CHILD1].window, { host: 'box-a', title: '└child-one' });
  assert.equal(s[CHILD2].window, null);
  assert.deepEqual(Object.keys(s[HEAD]).sort(), ['cwd', 'head', 'id', 'live', 'own', 'parent', 'title', 'window']);
});

test('снимок свой только если все сессии свои', () => {
  const r = tree(HEAD);
  const snaps = Object.fromEntries(r.o.snapshots.map((x) => [x.id, x]));
  assert.equal(snaps['2026-01-01T10-00-00'].own, true);
  assert.equal(snaps['2026-01-01T11-00-00'].own, false, 'в нём чужая сессия');
  assert.deepEqual(snaps['2026-01-01T10-00-00'].sessions, [HEAD, CHILD1]);
  assert.equal(snaps['2026-01-01T10-00-00'].host, 'box-a');
  assert.equal(snaps['2026-01-01T10-00-00'].created, 200);
  // Исполнителю снимок head не свой.
  const c = tree(CHILD1);
  assert.ok(c.o.snapshots.every((x) => x.own === false));
});

test('tree без --json — короткая сводка для человека', () => {
  const w = world({ state: loadState(), trackers: trackers(now()), children: CHILDREN, heads: HEADS, caller: HEAD });
  try {
    const r = runCli(['tree'], w.env);
    assert.equal(r.status, 0, r.stderr);
    assert.match(r.stdout, /demo-head/);
    assert.match(r.stdout, /└child-one/);
    assert.doesNotMatch(r.stdout, /^\{/, 'не JSON');
  } finally {
    w.cleanup();
  }
});

test('ccfzf --state упал — отказ с текстом stderr', () => {
  const w = world({ caller: HEAD });
  try {
    const r = runCli(['tree', '--json'], { ...w.env, CCFZF_BIN: '/nonexistent/ccfzf' });
    assert.equal(r.status, 1);
    assert.match(JSON.parse(r.stdout).error, /ccfzf --state/);
  } finally {
    w.cleanup();
  }
});
