// claude-wt session rename: поставить в очередь новое имя живой сессии; применяет его
// pending-title-hook.sh на следующем промпте цели. Вывод и коды — как у rename.mjs: 0/1.
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { legacyWorld, run } from './legacy-world.mjs';

const RENAME = ['session', 'rename'];
const X = '11111111-1111-4111-8111-111111111111';
const HOOKED = { hooks: { UserPromptSubmit: [{ hooks: [{ type: 'command', command: '~/.claude/skills/session-rename/pending-title-hook.sh' }] }] } };
let e;
const queueDir = () => join(e.home, '.claude/hooks/state/session-rename');
beforeEach(() => {
  e = legacyWorld();
  e.agents([e.meAgent, { pid: 4242, cwd: '/p/x', kind: 'interactive', sessionId: X, name: 'kid', status: 'idle' }]);
  e.write('.claude/settings.json', HOOKED);
});
afterEach(() => e.cleanup());

test('--to: имя в очереди, ответ с next', () => {
  const r = run(RENAME, ['--session-id', X, '--to', '  new-kid '], e.env);
  assert.equal(r.code, 0, r.stdout + r.stderr);
  assert.deepEqual(r.json, {
    ok: true, queued: true, sessionId: X, from: 'kid', to: 'new-kid', hookRegistered: true,
    next: `SendMessage to "kid" (any short message), then session-find --session-id ${X}`,
  });
  assert.equal(readFileSync(join(queueDir(), X), 'utf8'), 'new-kid\n');
  assert.equal(statSync(join(queueDir(), X)).mode & 0o777, 0o600);
  assert.equal(statSync(queueDir()).mode & 0o777, 0o700);
});

test('SESSION_RENAME_DIR перебивает каталог очереди', () => {
  e.env.SESSION_RENAME_DIR = join(e.home, 'q');
  const r = run(RENAME, ['--session-id', X, '--to', 'n'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(readFileSync(join(e.home, 'q', X), 'utf8'), 'n\n');
});

test('--cancel убирает очередь', () => {
  run(RENAME, ['--session-id', X, '--to', 'n'], e.env);
  const r = run(RENAME, ['--session-id', X, '--cancel'], e.env);
  assert.equal(r.code, 0);
  assert.deepEqual(r.json, { ok: true, cancelled: true, sessionId: X });
  assert.ok(!existsSync(join(queueDir(), X)));
});

test('многострочное и пустое имя — отказ', () => {
  for (const to of [['--to', 'a\nb'], ['--to', '   '], []]) {
    const r = run(RENAME, ['--session-id', X, ...to], e.env);
    assert.equal(r.code, 1, JSON.stringify(to));
    assert.deepEqual(r.json, { ok: false, error: '--to <new name> is required, one line' });
  }
  assert.ok(!existsSync(join(queueDir(), X)));
});

test('без --session-id — usage в JSON', () => {
  const r = run(RENAME, ['--to', 'n'], e.env);
  assert.equal(r.code, 1);
  assert.match(r.json.error, /^usage: .*--session-id <uuid> --to <new name> \| --cancel/);
});

test('сессия не живая; имя занято', () => {
  let r = run(RENAME, ['--session-id', '22222222-2222-4222-8222-222222222222', '--to', 'n'], e.env);
  assert.equal(r.code, 1);
  assert.deepEqual(r.json, { ok: false, error: 'session is not live', sessionId: '22222222-2222-4222-8222-222222222222' });
  r = run(RENAME, ['--session-id', X, '--to', 'boss'], e.env);
  assert.equal(r.code, 1);
  assert.deepEqual(r.json, { ok: false, error: 'name is taken by another live session', name: 'boss', takenBy: e.me.sessionId });
  r = run(RENAME, ['--session-id', X, '--to', 'kid'], e.env);
  assert.equal(r.code, 0, 'своё же имя — не конфликт');
});

test('хук не подключён — ничего в очереди; --settings находит его в другом файле', () => {
  e.write('.claude/settings.json', {});
  let r = run(RENAME, ['--session-id', X, '--to', 'n'], e.env);
  assert.equal(r.code, 1);
  assert.equal(r.json.hookRegistered, false);
  assert.match(r.json.error, /not registered/);
  assert.ok(!existsSync(join(queueDir(), X)));
  e.write('other-settings.json', HOOKED);
  r = run(RENAME, ['--session-id', X, '--to', 'n', '--settings', join(e.home, 'other-settings.json')], e.env);
  assert.equal(r.code, 0, r.stdout);
  e.write('.claude/settings.local.json', HOOKED);
  r = run(RENAME, ['--session-id', X, '--to', 'n2'], e.env);
  assert.equal(r.code, 0, 'settings.local.json тоже читается');
});
