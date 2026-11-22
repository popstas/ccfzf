import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { legacyWorld as makeEnv, run } from './legacy-world.mjs';

// claude-wt head adopt: усыновить живые сессии, которые head не открывал. Вывод и коды — как у head-adopt.mjs.
const ADOPT = ['head', 'adopt'];
const X = '11111111-1111-4111-8111-111111111111';
const Y = '22222222-2222-4222-8222-222222222222';
const Z = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'; // hex-буквы: на них проверяется регистр
let e;

const agent = (sessionId, name, cwd = '/p/x') => ({ pid: 1, cwd, kind: 'interactive', sessionId, name, status: 'idle' });
const adopt = (...a) => run(ADOPT, a, e.env, { timeout: 5000 });
const rec = (id) => e.read(`.ccfzf/children/${id}.json`);

beforeEach(() => {
  e = makeEnv();
  e.mark();
  e.agents([e.meAgent, agent(X, 'x')]);
});
afterEach(() => e.cleanup());

test('adopt по имени', () => {
  const r = adopt('x');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.results[0].adopted, true);
  const c = rec(X);
  assert.equal(c.adopted, true);
  assert.equal(c.head, 'boss');
  assert.equal(c.headId, e.me.sessionId);
  assert.equal(c.cwd, '/p/x');
  assert.equal(c.name, 'x');
  assert.ok(Number.isInteger(c.createdAt) && c.createdAt > 1e9 && c.createdAt < 1e12);
});

test('adopt по sessionId', () => {
  const r = adopt(X);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(rec(X).headId, e.me.sessionId);
});

test('перепривязка от другого head', () => {
  e.write(`.ccfzf/children/${X}.json`, { sessionId: X, name: 'x', head: 'a', headId: 'A', cwd: '/p/x', createdAt: 1 });
  const r = adopt('x');
  assert.equal(r.code, 0, r.stdout);
  const c = rec(X);
  assert.equal(c.headId, e.me.sessionId);
  assert.equal(c.prevHeadId, 'A');
  assert.equal(c.prevHead, 'a');
});

test('already: запись spawn не меняется', () => {
  e.write(`.ccfzf/children/${X}.json`, { sessionId: X, name: 'x', head: 'boss', headId: e.me.sessionId, cwd: '/p/x', createdAt: 5 });
  const before = readFileSync(join(e.home, `.ccfzf/children/${X}.json`), 'utf8');
  const r = adopt('x');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.results[0].already, true);
  assert.equal(readFileSync(join(e.home, `.ccfzf/children/${X}.json`), 'utf8'), before);
});

test('отказ: сам себя', () => {
  const r = adopt(e.me.sessionId);
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.results[0].why, /self/);
  assert.ok(!e.exists(`.ccfzf/children/${e.me.sessionId}.json`));
});

test('отказ: предок', () => {
  e.write(`.ccfzf/children/${e.me.sessionId}.json`, { headId: 'P' });
  e.write('.ccfzf/children/P.json', { headId: X });
  const r = adopt('x');
  assert.equal(r.code, 1, r.stdout);
  assert.equal(r.json.results[0].refused, true);
  assert.match(r.json.results[0].why, /ancestor/);
  assert.ok(!e.exists(`.ccfzf/children/${X}.json`));
});

test('adopt: цикл в записях выше head', () => {
  e.write(`.ccfzf/children/${e.me.sessionId}.json`, { headId: 'P' });
  e.write('.ccfzf/children/P.json', { headId: e.me.sessionId });
  const r = adopt('x');
  assert.equal(r.timedOut, false);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.results[0].adopted, true);
});

test('отказ: не живая, остальные дальше', () => {
  const r = adopt('ghost', 'x');
  assert.equal(r.code, 1, r.stdout);
  assert.equal(r.json.results[0].refused, true);
  assert.equal(r.json.results[1].adopted, true);
});

test('отказ: имя у двух сессий', () => {
  e.agents([e.meAgent, agent(X, 'x'), agent(Y, 'x')]);
  const r = adopt('x');
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.results[0].why, /ambiguous/);
});

test('без метки head', () => {
  e.write(`.ccfzf/heads/${e.me.sessionId}.json`, '');
  const r = adopt('x');
  assert.equal(r.code, 1, r.stdout);
  assert.deepEqual(readdirSync(join(e.home, '.ccfzf/children')), []);
});

test('--release своего', () => {
  adopt('x');
  const r = adopt('--release', 'x');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.results[0].released, true);
  assert.ok(!e.exists(`.ccfzf/children/${X}.json`));
});

test('--release чужого', () => {
  e.write(`.ccfzf/children/${X}.json`, { sessionId: X, name: 'x', head: 'a', headId: 'A', adopted: true });
  const r = adopt('--release', 'x');
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.results[0].why, /not your child/);
  assert.ok(e.exists(`.ccfzf/children/${X}.json`));
});

test('--release ребёнка от spawn', () => {
  e.write(`.ccfzf/children/${X}.json`, { sessionId: X, name: 'x', head: 'boss', headId: e.me.sessionId });
  const r = adopt('--release', 'x');
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.results[0].why, /only adopted/);
  assert.ok(e.exists(`.ccfzf/children/${X}.json`));
});

test('--release по имени, сессия уже не живая', () => {
  adopt('x');
  e.agents([e.meAgent]);
  const r = adopt('--release', 'x');
  assert.equal(r.code, 0, r.stdout);
  assert.ok(!e.exists(`.ccfzf/children/${X}.json`));
});

test('нет .tmp после записи', () => {
  adopt('x');
  assert.deepEqual(readdirSync(join(e.home, '.ccfzf/children')), [`${X}.json`]);
});

test('ведущий @ у имени срезается', () => {
  const r = adopt('@x');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.results[0].adopted, true);
  assert.ok(e.exists(`.ccfzf/children/${X}.json`));
});

test('sessionId без учёта регистра', () => {
  e.agents([e.meAgent, agent(Z, 'z')]);
  const r = adopt(Z.toUpperCase());
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.results[0].sessionId, Z);
  assert.ok(e.exists(`.ccfzf/children/${Z}.json`));
});

test('--release по sessionId без учёта регистра', () => {
  e.agents([e.meAgent, agent(Z, 'z')]);
  adopt('z');
  const r = adopt('--release', Z.toUpperCase());
  assert.equal(r.code, 0, r.stdout);
  assert.ok(!e.exists(`.ccfzf/children/${Z}.json`));
});

test('нет каталога children: --release отвечает JSON', () => {
  rmSync(join(e.home, '.ccfzf/children'), { recursive: true });
  const r = adopt('--release', 'ghost');
  assert.equal(r.code, 1, r.stderr);
  assert.equal(r.json.results[0].refused, true);
  assert.match(r.json.results[0].why, /no record/);
});

test('нет каталога sessions: отказ JSON', () => {
  rmSync(join(e.home, '.claude/sessions'), { recursive: true });
  const r = adopt('x');
  assert.equal(r.code, 1, r.stderr);
  assert.equal(r.json.ok, false);
  assert.match(r.json.error, /head-adopt только из head-сессии/);
});

test('claude agents упал: отказ JSON', () => {
  e.env.FAKE_AGENTS_FILE = join(e.home, 'missing.json');
  const r = adopt('x');
  assert.equal(r.code, 1, r.stderr);
  assert.equal(r.json.ok, false);
  assert.match(r.json.error, /claude agents/);
});
