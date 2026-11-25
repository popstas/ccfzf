import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { run } from './legacy-world.mjs';
import { legacyWorld as makeEnv, runAsync, liveProcess } from './legacy-world.mjs';

// claude-wt session close: закрыть своего ребёнка (SIGTERM, ждать выхода). Вывод и коды — как у close.mjs: 0/1.
// runAsync: занятый цикл событий не пожнёт убитый sleep, и close увидит зомби живым.

const CLOSE = ['session', 'close'];
let e;
let proc;
beforeEach(() => { e = makeEnv(); e.mark(); });
afterEach(() => { proc?.kill(); proc = undefined; e.cleanup(); });

// Мой живой ребёнок: настоящий процесс `sleep`, записанный сессией Claude.
function liveChild(record = {}, status = 'idle') {
  proc = liveProcess();
  const sid = randomUUID();
  e.write(`.claude/sessions/${proc.pid}.json`, { pid: proc.pid, sessionId: sid, name: 'kid', procStart: proc.procStart });
  e.agents([e.meAgent, { pid: proc.pid, cwd: '/p/x', kind: 'interactive', sessionId: sid, name: 'kid', status }]);
  e.write(`.ccfzf/children/${sid}.json`, { sessionId: sid, name: 'kid', head: 'boss', headId: e.me.sessionId, cwd: '/p/x', createdAt: 1, ...record });
  return sid;
}

test('close из head, который сам ребёнок', async () => {
  e.write(`.ccfzf/children/${e.me.sessionId}.json`, { sessionId: e.me.sessionId, head: 'top', headId: 'T' });
  const sid = liveChild();
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '5'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.closed, true);
});

test('привязанный: closed и adopted:true', async () => {
  const sid = liveChild({ adopted: true });
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '5'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.closed, true);
  assert.equal(r.json.adopted, true);
});

test('старая запись spawn: adopted:false', async () => {
  const sid = liveChild();
  assert.deepEqual(readdirSync(join(e.home, '.ccfzf/prompts')), []);
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '5'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.closed, true);
  assert.equal(r.json.adopted, false);
});

test('busy привязанный: отказ с adopted', async () => {
  const sid = liveChild({ adopted: true }, 'busy');
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '5'], e.env);
  assert.equal(r.code, 1, r.stdout);
  assert.equal(r.json.closed, false);
  assert.equal(r.json.adopted, true);
  process.kill(proc.pid, 0); // still alive: throws if it is gone
});

test('close удаляет копии промпта и файлы канала', async () => {
  const sid = liveChild();
  for (const ext of ['md', 'task.md', 'mcp.json', 'channels', 'fork']) e.write(`.ccfzf/prompts/${sid}.${ext}`, 'x');
  e.write('.ccfzf/prompts/other.md', 'x');
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '5'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.deepEqual(readdirSync(join(e.home, '.ccfzf/prompts')), ['other.md']);
});

// Отметка закрытия: без неё свежая отметка хука держала закрытого ребёнка
// живым в `ccfzf --state` ещё до HOOK_LIVE_TTL (2 мин) после выхода.
test('close кладёт <id>.closed.json рядом с состоянием хуков', async () => {
  const sid = liveChild();
  const before = Math.floor(Date.now() / 1000);
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '5'], e.env);
  assert.equal(r.code, 0, r.stdout);
  const mark = e.read(`.claude/claude-wt/${sid}.closed.json`);
  assert.equal(mark.sessionId, sid);
  assert.equal(mark.by, e.me.sessionId);
  assert.ok(mark.closedAt >= before, JSON.stringify(mark));
});

test('отказ: отметки закрытия нет', async () => {
  const sid = liveChild({ head: 'other', headId: 'O' });
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '1'], e.env);
  assert.equal(r.code, 1, r.stdout);
  assert.equal(e.exists(`.claude/claude-wt/${sid}.closed.json`), false);
});

// --- отказы: в CLI проверки те же, что в close.mjs ---

test('чужой ребёнок: not your child, процесс жив', async () => {
  const sid = liveChild({ head: 'other', headId: 'O' });
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '1'], e.env);
  assert.equal(r.code, 1, r.stdout);
  assert.deepEqual(r.json, { ok: false, sessionId: sid, name: 'kid', closed: false, why: 'not your child (head: other)', adopted: false });
  process.kill(proc.pid, 0);
});

test('не ребёнок ничей: закрывает пользователь', async () => {
  const sid = liveChild();
  e.write(`.ccfzf/children/${sid}.json`, '');
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '1'], e.env);
  assert.equal(r.code, 1);
  assert.match(r.json.why, /not a child of any head/);
});

test('busy без --force — отказ; с --force — закрыт', async () => {
  const sid = liveChild({}, 'busy');
  let r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '1'], e.env);
  assert.equal(r.code, 1);
  assert.match(r.json.why, /child is busy/);
  r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '5', '--force'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.signal, 'SIGTERM');
  assert.equal(r.json.why, 'exited on SIGTERM');
});

test('pid не совпадает с реестром — сигнала нет', async () => {
  const sid = liveChild();
  e.write(`.claude/sessions/${proc.pid}.json`, { pid: proc.pid, sessionId: sid, name: 'kid', procStart: '1' });
  const r = await runAsync(CLOSE, ['--session-id', sid, '--wait', '1'], e.env);
  assert.equal(r.code, 1);
  assert.match(r.json.why, new RegExp(`pid ${proc.pid} does not match the session registry`));
  process.kill(proc.pid, 0);
});

test('без метки head; метка мёртвой сессии; сам себя; не запущена; usage', () => {
  const ghost = '22222222-2222-4222-8222-222222222222';
  let r = run(CLOSE, ['--session-id', e.me.sessionId], e.env);
  assert.deepEqual(r.json, { ok: false, sessionId: e.me.sessionId, closed: false, why: 'a head does not close itself' });
  r = run(CLOSE, ['--session-id', ghost], e.env);
  assert.equal(r.code, 1);
  assert.equal(r.json.why, 'session is not running: nothing to close');
  assert.ok(!('adopted' in r.json), 'до чтения записи adopted нет');
  r = run(CLOSE, ['--session-id', 'nope'], e.env);
  assert.equal(r.code, 1);
  assert.match(r.json.why, /^usage: claude-wt session close --session-id <uuid>/);
  e.write(`.claude/sessions/${e.me.pid}.json`, { pid: e.me.pid, sessionId: 'someone-else', name: 'boss' });
  r = run(CLOSE, ['--session-id', ghost], e.env);
  assert.equal(r.json.detail, 'head mark of a session that is not alive');
  e.write(`.ccfzf/heads/${e.me.sessionId}.json`, '');
  r = run(CLOSE, ['--session-id', ghost], e.env);
  assert.equal(r.code, 1);
  assert.deepEqual(r.json, { ok: false, sessionId: ghost, closed: false, why: 'session-close только из head-сессии: вызови /head-session', detail: 'no head mark' });
});
