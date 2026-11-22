// <session> → id: точный id, префикс от 6 символов, имя живой, title закрытой.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveSession } from '../../cli/lib/resolve.mjs';
import { loadState, HEAD, CHILD1, OTHER, CLOSED } from './fixtures.mjs';

const state = loadState();
const agents = [
  { sessionId: HEAD, name: 'demo-head', status: 'idle' },
  { sessionId: CHILD1, name: 'renamed-child', status: 'busy' },
  { sessionId: OTHER, name: 'someone-else', status: 'idle' },
];

test('полный id', () => {
  assert.deepEqual(resolveSession(CHILD1, { state, agents }), { id: CHILD1 });
});

test('префикс id', () => {
  const st = { ...state, sessions: [...state.sessions, { id: 'eeeeeeee-1234-4000-8000-000000000009', title: 'x' }] };
  assert.deepEqual(resolveSession('eeeeee', { state: st, agents }), { id: 'eeeeeeee-1234-4000-8000-000000000009' });
  const r = resolveSession('aaaaaaaa', { state, agents });
  assert.equal(r.error, 'ambiguous', 'общий префикс у четырёх');
  assert.equal(r.candidates.length, 4);
});

test('короткий префикс (<6) не принимается', () => {
  assert.deepEqual(resolveSession('bbbbb', { state, agents }), { error: 'not found' });
});

test('имя живой сессии', () => {
  assert.deepEqual(resolveSession('renamed-child', { state, agents }), { id: CHILD1 });
});

test('title закрытой сессии', () => {
  assert.deepEqual(resolveSession('old-closed', { state, agents }), { id: CLOSED });
});

test('агенты читаются лениво: по id claude agents не зовётся', () => {
  let calls = 0;
  const lazy = () => { calls++; return agents; };
  assert.deepEqual(resolveSession(HEAD, { state, agents: lazy }), { id: HEAD });
  assert.equal(calls, 0);
  assert.deepEqual(resolveSession('renamed-child', { state, agents: lazy }), { id: CHILD1 });
  assert.equal(calls, 1);
});

test('два тёзки — ambiguous со списком', () => {
  const twins = [
    ...agents,
    { sessionId: 'cccccccc-0000-4000-8000-000000000001', name: 'demo-head', status: 'idle' },
  ];
  const r = resolveSession('demo-head', { state, agents: twins });
  assert.equal(r.error, 'ambiguous');
  assert.deepEqual(r.candidates.map((c) => c.id).sort(), [HEAD, 'cccccccc-0000-4000-8000-000000000001'].sort());
  assert.ok(r.candidates.every((c) => 'title' in c));
  // Тёзки среди закрытых — тоже отказ, а не первая попавшаяся.
  const st = { ...state, sessions: [...state.sessions, { id: 'dddddddd-0000-4000-8000-000000000001', title: 'old-closed', live: false }] };
  const c = resolveSession('old-closed', { state: st, agents });
  assert.equal(c.error, 'ambiguous');
  assert.equal(c.candidates.length, 2);
});

test('не найдено', () => {
  assert.deepEqual(resolveSession('no-such-thing', { state, agents }), { error: 'not found' });
  assert.deepEqual(resolveSession('', { state, agents }), { error: 'not found' });
});
