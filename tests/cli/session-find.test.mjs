// claude-wt session find: живая сессия по sessionId или имени, её имя и место окна.
// Вывод и коды — как у find.mjs скилла session-find: 0 найдено, 2 нет, 1 ошибка.
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { legacyWorld, run, runAsync } from './legacy-world.mjs';

const FIND = ['session', 'find'];
const X = '11111111-1111-4111-8111-111111111111';
const Y = '22222222-2222-4222-8222-222222222222';
const agent = (sessionId, name, { cwd = '/p/x', pid = 4242, status = 'idle' } = {}) => ({ pid, cwd, kind: 'interactive', sessionId, name, status });
let e;
beforeEach(() => { e = legacyWorld(); });
afterEach(() => e.cleanup());

test('--session-id найден: имя, реестр, место окна', () => {
  e.agents([e.meAgent, agent(X, 'kid')]);
  e.write('.claude/sessions/4242.json', { pid: 4242, sessionId: X, name: 'kid', nameSource: 'rename', formerNames: [{ name: 'old-kid', at: 1 }] });
  e.write('.ccfzf/windows/box-a.json', { host: 'box-a', generated: 100, windows: { [X]: { monitor: 2, zone: 3, slot: 1 } } });
  e.write('.ccfzf/windows/box-b.json', { host: 'box-b', generated: 50, windows: { [X]: { monitor: 9 } } });
  const r = run(FIND, ['--session-id', X], e.env);
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.deepEqual(r.json, {
    found: true, sessionId: X, name: 'kid', status: 'idle', kind: 'interactive', cwd: '/p/x', pid: 4242,
    nameSource: 'rename', formerNames: ['old-kid'],
    windowHost: 'box-a', monitor: 2, zone: 3, slot: 1, duplicateName: false,
  });
});

test('место окна: старый файл без monitor/zone/slot — null; файла нет — всё null', () => {
  e.agents([e.meAgent, agent(X, 'kid')]);
  e.write('.ccfzf/windows/box-a.json', { generated: 100, windows: { [X]: { title: 'w', zone: 'x' } } });
  let r = run(FIND, ['--session-id', X], e.env);
  assert.equal(r.code, 0);
  assert.deepEqual([r.json.windowHost, r.json.monitor, r.json.zone, r.json.slot], ['box-a', null, null, null], 'host — из имени файла');
  assert.ok(!('nameSource' in r.json) && !('formerNames' in r.json), 'нет записи реестра — нет и полей');
  e.write('.ccfzf/windows/box-a.json', { host: 'box-a', generated: 100, windows: {} });
  r = run(FIND, ['--session-id', X], e.env);
  assert.deepEqual([r.json.windowHost, r.json.monitor, r.json.zone, r.json.slot], [null, null, null, null]);
});

test('--timeout 0, не найден, записи ребёнка нет: код 2 и подсказка', () => {
  const r = run(FIND, ['--session-id', X, '--timeout', '0'], e.env);
  assert.equal(r.code, 2, r.stdout + r.stderr);
  assert.deepEqual(Object.keys(r.json), ['found', 'sessionId', 'waitedSec', 'childRecord', 'hint']);
  assert.equal(r.json.found, false);
  assert.equal(r.json.waitedSec, 0);
  assert.equal(r.json.childRecord, null);
  assert.match(r.json.hint, /^no launch record in ~\/\.ccfzf\/children/);
});

test('не найден, запись ребёнка есть: childRecord и подсказка про claude-wt-new', () => {
  const rec = { sessionId: X, name: '.kid', head: 'boss', headId: e.me.sessionId, createdAt: 5 };
  e.write(`.ccfzf/children/${X}.json`, rec);
  const r = run(FIND, ['--session-id', X, '--timeout', '0'], e.env);
  assert.equal(r.code, 2);
  assert.deepEqual(r.json.childRecord, rec);
  assert.match(r.json.hint, /^claude-wt-new recorded the launch/);
});

test('ждёт появления сессии до --timeout', async () => {
  const p = runAsync(FIND, ['--session-id', X, '--timeout', '5', '--interval', '0.2'], e.env);
  await new Promise((r) => setTimeout(r, 600));
  e.agents([e.meAgent, agent(X, 'late')]);
  const r = await p;
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.equal(r.json.name, 'late');
});

test('--name: одна — объект; тёзки — массив с duplicateName; нет — код 2', () => {
  e.agents([e.meAgent, agent(X, 'kid'), agent(Y, 'twin', { pid: 1 }), agent('33333333-3333-4333-8333-333333333333', 'twin', { pid: 2 })]);
  let r = run(FIND, ['--name', 'kid'], e.env);
  assert.equal(r.code, 0);
  assert.equal(r.json.sessionId, X);
  assert.equal(r.json.duplicateName, false);
  r = run(FIND, ['--name', 'twin'], e.env);
  assert.equal(r.code, 0);
  assert.ok(Array.isArray(r.json));
  assert.equal(r.json.length, 2);
  assert.ok(r.json.every((h) => h.duplicateName === true));
  r = run(FIND, ['--name', 'ghost'], e.env);
  assert.equal(r.code, 2);
  assert.deepEqual(r.json, { found: false, name: 'ghost' });
});

test('--list и --list --cwd', () => {
  e.agents([e.meAgent, agent(X, 'kid', { cwd: '/p/x' }), agent(Y, 'other', { cwd: '/p/y' })]);
  let r = run(FIND, ['--list'], e.env);
  assert.equal(r.code, 0);
  assert.deepEqual(r.json.map((s) => s.name), ['boss', 'kid', 'other']);
  assert.deepEqual(Object.keys(r.json[1]), ['name', 'sessionId', 'status', 'kind', 'cwd']);
  r = run(FIND, ['--list', '--cwd', '/p/y'], e.env);
  assert.deepEqual(r.json, [{ name: 'other', sessionId: Y, status: 'idle', kind: 'interactive', cwd: '/p/y' }]);
});

test('без аргументов: usage в stderr, stdout пуст, код 1', () => {
  const r = run(FIND, [], e.env);
  assert.equal(r.code, 1);
  assert.equal(r.stdout, '');
  assert.match(r.stderr, /usage: .*--session-id <uuid>/);
});

test('claude agents упал: сообщение в stderr, код 1', () => {
  e.env.FAKE_AGENTS_FILE = join(e.home, 'missing.json');
  const r = run(FIND, ['--list'], e.env);
  assert.equal(r.code, 1);
  assert.equal(r.stdout, '');
  assert.notEqual(r.stderr, '');
});
