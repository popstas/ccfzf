// wait set|clear|show: объявленное ожидание своей сессии в <id>.wait.json.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { runCli, world } from './helpers.mjs';

const ME = 'dddddddd-0000-4000-8000-000000000001';
const KID = 'dddddddd-0000-4000-8000-000000000002';
const STRANGER = 'dddddddd-0000-4000-8000-000000000003';

function env(extra = {}) {
  const sessions = [ME, KID, STRANGER].map((id, i) => ({ id, title: `s${i}`, live: true, cwd: '/w', mtime: 1, kind: 'interactive' }));
  const w = world({ state: { sessions, snapshots: [] }, children: [{ sessionId: KID, headId: ME }], caller: ME });
  const stateDir = join(w.dir, 'claude-wt');
  return { w, stateDir, env: { ...w.env, CLAUDE_WT_STATE_DIR: stateDir, ...extra } };
}
const json = (r) => JSON.parse(r.stdout);

test('set пишет файл своей сессии, show читает, clear снимает', () => {
  const { w, stateDir, env: e } = env();
  try {
    const r = runCli(['wait', 'set', '--kind', 'decision', '--ask', '  схема A\n или B? ', '--clear-by', 'ответ в чате', '--json'], e);
    assert.equal(r.status, 0, r.stderr);
    const o = json(r);
    assert.equal(o.id, ME);
    assert.deepEqual({ ...o.wait, setAt: 0 }, { kind: 'decision', ask: 'схема A или B?', clearBy: 'ответ в чате', setAt: 0 });
    const file = JSON.parse(readFileSync(join(stateDir, `${ME}.wait.json`), 'utf8'));
    assert.equal(file.sessionId, ME);
    assert.equal(file.setBy, ME);
    assert.ok(file.setAt > 0);
    const s = json(runCli(['wait', 'show', '--json'], e));
    assert.equal(s.wait.ask, 'схема A или B?');
    const c = json(runCli(['wait', 'clear', '--json'], e));
    assert.equal(c.cleared, true);
    assert.equal(existsSync(join(stateDir, `${ME}.wait.json`)), false);
    assert.equal(json(runCli(['wait', 'clear', '--json'], e)).cleared, false, 'повтор — не ошибка');
    assert.equal(json(runCli(['wait', 'show', '--json'], e)).wait, null);
  } finally { w.cleanup(); }
});

test('set над ребёнком можно, над чужой — отказ', () => {
  const { w, stateDir, env: e } = env();
  try {
    const r = runCli(['wait', 'set', KID, '--kind', 'review', '--ask', 'глянь PR', '--json'], e);
    assert.equal(r.status, 0, r.stderr);
    assert.ok(existsSync(join(stateDir, `${KID}.wait.json`)));
    const n = runCli(['wait', 'set', STRANGER, '--kind', 'review', '--ask', 'x', '--json'], e);
    assert.equal(n.status, 1);
    assert.match(json(n).error, /not your session/);
    assert.equal(existsSync(join(stateDir, `${STRANGER}.wait.json`)), false);
  } finally { w.cleanup(); }
});

test('отказы: без вида, кривой вид, без --ask, вне Claude Code', () => {
  const { w, env: e } = env();
  try {
    assert.match(json(runCli(['wait', 'set', '--ask', 'x', '--json'], e)).error, /--kind must be one of decision\|review\|external/);
    assert.match(json(runCli(['wait', 'set', '--kind', 'later', '--ask', 'x', '--json'], e)).error, /--kind/);
    assert.match(json(runCli(['wait', 'set', '--kind', 'decision', '--json'], e)).error, /--ask/);
    assert.match(json(runCli(['wait', 'set', '--kind', 'decision', '--ask', 'x'.repeat(501), '--json'], e)).error, /longer than 500/);
    const { CLAUDE_CODE_SESSION_ID, ...noCaller } = e;
    const r = runCli(['wait', 'set', '--kind', 'decision', '--ask', 'x', '--json'], noCaller);
    assert.equal(r.status, 1);
    assert.match(json(r).error, /CLAUDE_CODE_SESSION_ID/);
  } finally { w.cleanup(); }
});

test('без --json — строка для человека', () => {
  const { w, env: e } = env();
  try {
    mkdirSync(join(w.dir, 'claude-wt'), { recursive: true });
    const r = runCli(['wait', 'set', '--kind', 'external', '--ask', 'ждём Сашу'], e);
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.stdout.trim(), 'waiting set for dddddddd: external: ждём Сашу');
    assert.equal(runCli(['wait', 'show'], e).stdout.trim(), 'external: ждём Сашу');
  } finally { w.cleanup(); }
});
