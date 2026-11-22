// claude-wt head mark: метка head ~/.ccfzf/heads/<sessionId>.json; вывод — как у head-mark.mjs.
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { legacyWorld, run } from './legacy-world.mjs';

const MARK = ['head', 'mark'];
let e;
beforeEach(() => { e = legacyWorld(); });
afterEach(() => e.cleanup());

test('ребёнок становится head, parent в выводе', () => {
  e.write(`.ccfzf/children/${e.me.sessionId}.json`, { sessionId: e.me.sessionId, head: 'top', headId: 'T' });
  const r = run(MARK, [], e.env);
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.deepEqual(r.json.parent, { head: 'top', headId: 'T' });
  assert.ok(e.exists(`.ccfzf/heads/${e.me.sessionId}.json`));
});

test('head без родителя: parent null', () => {
  const r = run(MARK, [], e.env);
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.equal(r.json.parent, null);
});

test('вывод целиком: ключи старого скрипта, одна строка JSON', () => {
  const r = run(MARK, [], e.env);
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.equal(r.stdout.trim().split('\n').length, 1);
  const file = join(e.home, `.ccfzf/heads/${e.me.sessionId}.json`);
  assert.ok(Number.isInteger(r.json.createdAt));
  assert.deepEqual(r.json, { ok: true, marked: true, already: false, file, sessionId: e.me.sessionId, name: 'boss', cwd: '/p/demo', createdAt: r.json.createdAt, parent: null });
  assert.deepEqual(e.read(`.ccfzf/heads/${e.me.sessionId}.json`), { sessionId: e.me.sessionId, name: 'boss', cwd: '/p/demo', createdAt: r.json.createdAt });
  assert.deepEqual(readdirSync(join(e.home, '.ccfzf/heads')), [`${e.me.sessionId}.json`], 'без .tmp');
});

test('повтор: already и прежний createdAt', () => {
  e.mark();
  const r = run(MARK, [], e.env);
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.equal(r.json.already, true);
  assert.equal(r.json.createdAt, 1);
});

test('вне сессии Claude Code: отказ JSON, код 1', () => {
  delete e.env.CLAUDE_PID;
  const r = run(MARK, [], e.env);
  assert.equal(r.code, 1);
  assert.equal(r.json.ok, false);
  assert.match(r.json.error, /CLAUDE_CODE_SESSION_ID \/ CLAUDE_PID missing/);
});

test('нет имени в реестре: отказ', () => {
  e.write(`.claude/sessions/${e.me.pid}.json`, { pid: e.me.pid, sessionId: e.me.sessionId });
  const r = run(MARK, [], e.env);
  assert.equal(r.code, 1);
  assert.match(r.json.error, /no registry name/);
  assert.ok(!e.exists(`.ccfzf/heads/${e.me.sessionId}.json`));
});
