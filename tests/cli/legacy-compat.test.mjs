// Сравнение со старыми скриптами скиллов на одной фикстуре (Review Focus 1):
// JSON и код выхода CLI = JSON и код скрипта. Каталог скриптов — WT_LEGACY_SKILLS
// (снимок закоммиченных скриптов); без него тесты пропускаются.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { legacyWorld, runAsync, runOld, normalize, LEGACY } from './legacy-world.mjs';
import { mockManager } from './helpers.mjs';

const skip = !LEGACY && 'WT_LEGACY_SKILLS не задан';
const SID = 'cccccccc-0000-4000-8000-000000000001';

// Два одинаковых мира: один для скрипта, другой для CLI (команды пишут файлы).
async function both(setup, rel, cmd, args, drop = [], { noJson = false } = {}) {
  const a = legacyWorld({ sessionId: SID, pid: 910001 });
  const b = legacyWorld({ sessionId: SID, pid: 910001 });
  try {
    setup(a); setup(b);
    const old = await runOld(rel, args(a), a.env);
    const neu = await runAsync(cmd, args(b), b.env);
    // Пустой вывод у обоих сравнился бы «равным» — снимок обязан быть.
    if (!noJson) assert.ok(old.json !== null, `старый скрипт без JSON: ${old.stdout}${old.stderr}`);
    assert.equal(neu.code, old.code, `код: ${neu.stdout}${neu.stderr} / ${old.stdout}${old.stderr}`);
    assert.deepEqual(normalize(neu.json, b.home, drop), normalize(old.json, a.home, drop));
    // Без JSON сверяется stderr: иначе пустота у обоих сравнилась бы «равной».
    if (noJson) assert.equal(!neu.stderr, !old.stderr, `stderr: ${neu.stderr} / ${old.stderr}`);
    return { old, neu };
  } finally { a.cleanup(); b.cleanup(); }
}

test('head mark: как head-mark.mjs', { skip }, async () => {
  await both(() => {}, 'head-session/head-mark.mjs', ['head', 'mark'], () => [], ['createdAt']);
  await both((w) => { w.mark(); w.write(`.ccfzf/children/${SID}.json`, { headId: 'T', head: 'top' }); }, 'head-session/head-mark.mjs', ['head', 'mark'], () => []);
  await both((w) => { delete w.env.CLAUDE_PID; }, 'head-session/head-mark.mjs', ['head', 'mark'], () => []);
});

const FIND_OLD = 'session-find/find.mjs';
const kids = (w) => {
  w.agents([w.meAgent, { pid: 4242, cwd: '/p/x', kind: 'interactive', sessionId: X, name: 'kid', status: 'idle' },
    { pid: 1, cwd: '/p/y', kind: 'interactive', sessionId: Y, name: 'kid', status: 'busy' }]);
  w.write('.claude/sessions/4242.json', { pid: 4242, sessionId: X, name: 'kid', nameSource: 'rename', formerNames: [{ name: 'a' }] });
  w.write('.ccfzf/windows/box-a.json', { host: 'box-a', generated: 100, windows: { [X]: { monitor: 2, zone: 3, slot: 1 } } });
};
const X = '11111111-1111-4111-8111-111111111111';
const Y = '22222222-2222-4222-8222-222222222222';

test('session find: как find.mjs', { skip }, async () => {
  await both(kids, FIND_OLD, ['session', 'find'], () => ['--session-id', X]);
  await both(kids, FIND_OLD, ['session', 'find'], () => ['--name', 'kid']);
  await both(kids, FIND_OLD, ['session', 'find'], () => ['--name', 'nobody']);
  await both(kids, FIND_OLD, ['session', 'find'], () => ['--list', '--cwd', '/p/y']);
  // hint без машины агентов в тексте (публичный репозиторий) — ключ сверяется отдельно.
  const { neu } = await both(kids, FIND_OLD, ['session', 'find'], () => ['--session-id', 'cccccccc-0000-4000-8000-00000000dead', '--timeout', '0'], ['hint']);
  assert.equal(typeof neu.json.hint, 'string');
  await both((w) => { kids(w); w.write('.ccfzf/children/cccccccc-0000-4000-8000-00000000dead.json', { headId: SID }); }, FIND_OLD, ['session', 'find'],
    () => ['--session-id', 'cccccccc-0000-4000-8000-00000000dead', '--timeout', '0']);
  await both(kids, FIND_OLD, ['session', 'find'], () => [], [], { noJson: true });
});

const RENAME_OLD = 'session-rename/rename.mjs';
const renameWorld = (w) => {
  kids(w);
  w.write('.claude/settings.json', { hooks: { UserPromptSubmit: [{ hooks: [{ command: 'pending-title-hook.sh' }] }] } });
};

test('session rename: как rename.mjs', { skip }, async () => {
  const R = ['session', 'rename'];
  await both(renameWorld, RENAME_OLD, R, () => ['--session-id', X, '--to', 'new']);
  await both(renameWorld, RENAME_OLD, R, () => ['--session-id', X, '--cancel']);
  await both(renameWorld, RENAME_OLD, R, () => ['--session-id', X, '--to', 'boss']);
  await both(renameWorld, RENAME_OLD, R, () => ['--session-id', X, '--to', 'a\nb']);
  // usage называет команду CLI, а не скрипт — сверяется всё, кроме текста.
  const u = await both(renameWorld, RENAME_OLD, R, () => ['--to', 'x'], ['error']);
  assert.match(u.neu.json.error, /^usage: claude-wt session rename /);
  await both(renameWorld, RENAME_OLD, R, () => ['--session-id', 'cccccccc-0000-4000-8000-00000000dead', '--to', 'x']);
  await both(kids, RENAME_OLD, R, () => ['--session-id', X, '--to', 'new']);
});

const CLOSE_OLD = 'session-close/close.mjs';
const ADOPT_OLD = 'head-session/head-adopt.mjs';
// Ребёнок X в записях; живым в agents — тоже, но без настоящего процесса: сигналы не шлются.
const closeWorld = (record, status = 'idle') => (w) => {
  w.mark();
  w.agents([w.meAgent, { pid: 4242, cwd: '/p/x', kind: 'interactive', sessionId: X, name: 'kid', status }]);
  w.write(`.ccfzf/children/${X}.json`, { sessionId: X, name: 'kid', head: 'boss', headId: SID, ...record });
};

test('session close: отказы как у close.mjs', { skip }, async () => {
  const C = ['session', 'close'];
  await both(closeWorld({ headId: 'O', head: 'other' }), CLOSE_OLD, C, () => ['--session-id', X]);
  await both(closeWorld({ adopted: true }, 'busy'), CLOSE_OLD, C, () => ['--session-id', X]);
  await both(closeWorld({}), CLOSE_OLD, C, () => ['--session-id', X]); // pid 4242 без записи реестра
  await both(closeWorld({}), CLOSE_OLD, C, () => ['--session-id', Y]);
  await both(closeWorld({}), CLOSE_OLD, C, () => ['--session-id', SID]);
  await both(() => {}, CLOSE_OLD, C, () => ['--session-id', X]);
  const u = await both(() => {}, CLOSE_OLD, C, () => [], ['why']);
  assert.match(u.neu.json.why, /^usage: claude-wt session close /);
});

test('head adopt: как head-adopt.mjs', { skip }, async () => {
  const A = ['head', 'adopt'];
  const w0 = (w) => {
    w.mark();
    w.agents([w.meAgent, { pid: 1, cwd: '/p/x', kind: 'interactive', sessionId: X, name: 'x', status: 'idle' },
      { pid: 2, cwd: '/p/y', kind: 'interactive', sessionId: Y, name: 'y', status: 'idle' }]);
  };
  await both(w0, ADOPT_OLD, A, () => ['x', Y.toUpperCase(), 'ghost', SID]);
  await both((w) => { w0(w); w.write(`.ccfzf/children/${X}.json`, { sessionId: X, name: 'x', head: 'a', headId: 'A' }); }, ADOPT_OLD, A, () => ['@x']);
  await both((w) => { w0(w); w.write(`.ccfzf/children/${SID}.json`, { headId: X }); }, ADOPT_OLD, A, () => ['x']);
  await both((w) => { w0(w); w.write(`.ccfzf/children/${X}.json`, { sessionId: X, name: 'x', head: 'boss', headId: SID, adopted: true }); },
    ADOPT_OLD, A, () => ['--release', 'x', 'y', 'ghost']);
  await both((w) => { w0(w); w.write(`.ccfzf/children/${Y}.json`, { sessionId: Y, name: 'y', head: 'boss', headId: SID }); }, ADOPT_OLD, A, () => ['--release', 'y']);
  await both(() => {}, ADOPT_OLD, A, () => ['x']);
  await both((w) => { w0(w); w.env.FAKE_AGENTS_FILE = '/nonexistent/agents.json'; }, ADOPT_OLD, A, () => ['x'], ['why']);
  const u = await both(w0, ADOPT_OLD, A, () => [], ['error']);
  assert.match(u.neu.json.error, /^usage: claude-wt head adopt /);
});

const SPAWN_OLD = 'session-spawn/spawn.mjs';
const CHILD = 'cccccccc-0000-4000-8000-0000000000c1';
const spawnWorld = (w) => {
  w.mark();
  w.tracker('box-a', { projects: ['/p/demo'], httpHost: 'box-a.test' });
  w.write('task.md', 'задание');
  w.write('mcp.json', { mcpServers: {} });
  w.write(`.ccfzf/children/${SID}.json`, { headId: 'P' });
  w.write('.ccfzf/heads/P.json', { sessionId: 'P', cwd: '/p/demo' });
  w.write(`.claude/sessions/${w.me.pid}.json`, { pid: w.me.pid, sessionId: SID, name: 'boss', cwd: '/p/side' });
};

test('session spawn --dry-run: как spawn.mjs', { skip }, async () => {
  const S = ['session', 'spawn'];
  const base = (w) => ['--task', 'Wide 2/3', '--prompt-file', `${w.home}/task.md`, '--cwd', '/p/demo', '--session-id', CHILD, '--dry-run'];
  await both(spawnWorld, SPAWN_OLD, S, base);
  await both(spawnWorld, SPAWN_OLD, S, (w) => [...base(w), '--mcp-config', `${w.home}/mcp.json`, '--dev-channels', 'server:a,server:b', '--zone', '2:1', '--terminal', 'wt']);
  await both(spawnWorld, SPAWN_OLD, S, (w) => [...base(w), '--url', 'http://box-a:9722/']);
  await both(spawnWorld, SPAWN_OLD, S, (w) => [...base(w), '--name', 'exact']);
  await both(spawnWorld, SPAWN_OLD, S, (w) => [...base(w), '--permission-mode', 'bypassPermissions']);
  await both(spawnWorld, SPAWN_OLD, S, (w) => [...base(w), '--machine', 'ghost']);
  await both(spawnWorld, SPAWN_OLD, S, (w) => [...base(w), '--zone', '0:1']);
  await both(spawnWorld, SPAWN_OLD, S, (w) => [...base(w), '--fork', 'yes']);
  await both((w) => { spawnWorld(w); w.write(`.ccfzf/heads/${SID}.json`, ''); }, SPAWN_OLD, S, base);
});

test('session spawn после запроса: как spawn.mjs (200, 403, таймаут, обрыв)', { skip }, async () => {
  const S = ['session', 'spawn'];
  const replies = {
    ok: (_p, body) => ({ status: 200, body: { ok: true, sessionId: body.sessionId, name: body.name } }),
    refused: () => ({ status: 403, body: { ok: false, status: 403, reason: 'head window not found' } }),
    text500: () => ({ status: 500, raw: 'boom' }),
    hang: () => 'hang',
    destroy: () => 'destroy',
  };
  for (const [what, reply] of Object.entries(replies)) {
    const m = await mockManager(reply);
    try {
      const args = (w) => ['--task', 't', '--prompt-file', `${w.home}/task.md`, '--cwd', '/p/demo', '--session-id', CHILD, '--url', m.url, '--timeout', '1'];
      const { neu } = await both(spawnWorld, SPAWN_OLD, S, args);
      assert.ok(neu.json, what);
    } finally { await m.close(); }
  }
});
