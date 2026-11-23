// --help: группы session и head видны в справке; справка команды из скилла — тоже справка.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCli } from './helpers.mjs';

test('--help называет команды сессий и head', () => {
  const r = runCli(['--help']);
  assert.equal(r.status, 0);
  for (const c of ['window icon <session>', 'window badge <session>', 'window icons', 'session open <session>', 'session unread <session>', 'session seen <session>', 'session find', 'session rename', 'session close', 'session spawn', 'head mark', 'head adopt']) {
    assert.ok(r.stdout.includes(c), c);
  }
  assert.match(r.stdout, /compatible with the skill scripts/);
});

test('session find --help — справка с кодом 0, а не поиск', () => {
  const r = runCli(['session', 'find', '--help']);
  assert.equal(r.status, 0);
  assert.match(r.stdout, /^usage: claude-wt/);
});

test('-h как значение не справка: session find --name -h ищет имя «-h»', async () => {
  const { legacyWorld, run } = await import('./legacy-world.mjs');
  const e = legacyWorld();
  try {
    const r = run(['session', 'find'], ['--name', '-h'], e.env);
    assert.equal(r.code, 2, r.stdout);
    assert.deepEqual(r.json, { found: false, name: '-h' });
    const n = run(['session', 'rename'], ['--session-id', e.me.sessionId, '--to', '-h'], e.env);
    assert.notEqual(n.json, null, 'rename с --to -h отвечает JSON, а не справкой');
  } finally { e.cleanup(); }
});
