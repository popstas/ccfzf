// --help: группы session и head видны в справке; справка команды из скилла — тоже справка.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCli } from './helpers.mjs';

test('--help называет команды сессий и head', () => {
  const r = runCli(['--help']);
  assert.equal(r.status, 0);
  for (const c of ['session open <session>', 'session find', 'session rename', 'session close', 'session spawn', 'head mark', 'head adopt']) {
    assert.ok(r.stdout.includes(c), c);
  }
  assert.match(r.stdout, /compatible with the skill scripts/);
});

test('session find --help — справка с кодом 0, а не поиск', () => {
  const r = runCli(['session', 'find', '--help']);
  assert.equal(r.status, 0);
  assert.match(r.stdout, /^usage: claude-wt/);
});
