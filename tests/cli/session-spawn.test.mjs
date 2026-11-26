import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { chmodSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { legacyWorld, run, runAsync } from './legacy-world.mjs';

// claude-wt session spawn: открыть дочернюю сессию в окне claude-wt (POST /claude-wt/session-new).
// Вывод и коды — как у spawn.mjs скилла session-spawn: 0 — открыта (или dry-run), 1 — отказ, 3 — исход неизвестен.
const SPAWN = ['session', 'spawn'];
let e;
let promptFile;

beforeEach(() => {
  e = legacyWorld();
  e.mark();
  e.tracker('box-a', { projects: ['/p/demo'], httpHost: 'box-a.test' });
  e.write('task.md', 'задание');
  promptFile = join(e.home, 'task.md');
});
afterEach(() => e.cleanup());

const dry = (...extra) => run(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--dry-run', ...extra], e.env);
const asSide = () => {
  e.write(`.claude/sessions/${e.me.pid}.json`, { pid: e.me.pid, sessionId: e.me.sessionId, name: 'boss', cwd: '/p/side' });
};

test('headCwd: cwd head из реестра', () => {
  const r = dry();
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.headCwd, e.me.cwd);
});

test('profileCwd: cwd head в projects', () => {
  const r = dry();
  assert.equal(r.json.body.profileCwd, '/p/demo');
});

test('profileCwd: по цепочке headId', () => {
  asSide();
  e.write(`.ccfzf/children/${e.me.sessionId}.json`, { sessionId: e.me.sessionId, headId: 'P', head: 'top' });
  e.write('.ccfzf/heads/P.json', { sessionId: 'P', cwd: '/p/demo' });
  const r = dry();
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.headCwd, '/p/side');
  assert.equal(r.json.body.profileCwd, '/p/demo');
});

test('profileCwd: никого в projects', () => {
  asSide();
  const r = dry();
  assert.equal(r.code, 0, r.stdout);
  assert.ok(!('profileCwd' in r.json.body));
});

test('profileCwd: цикл в записях', () => {
  asSide();
  e.write(`.ccfzf/children/${e.me.sessionId}.json`, { headId: 'P' });
  e.write('.ccfzf/children/P.json', { headId: e.me.sessionId, cwd: '/p/other' });
  const r = run(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--dry-run'], e.env, { timeout: 5000 });
  assert.equal(r.timedOut, false);
  assert.equal(r.code, 0, r.stdout);
  assert.ok(!('profileCwd' in r.json.body));
});

test('--url: трекер по хосту', () => {
  assert.equal(dry('--url', 'http://box-a.test:9722').json.body.profileCwd, '/p/demo');
  const other = dry('--url', 'http://other.test:1');
  assert.equal(other.code, 0, other.stdout);
  assert.ok(!('profileCwd' in other.json.body));
});

test('403: причина менеджера в error, why про headCwd', async () => {
  const srv = http.createServer((req, res) => {
    req.resume();
    req.on('end', () => {
      res.writeHead(403, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ ok: false, status: 403, reason: 'head window not found' }));
    });
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  try {
    const url = `http://127.0.0.1:${srv.address().port}`;
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', url], e.env);
    assert.equal(r.code, 1, r.stdout);
    assert.equal(r.json.error, 'head window not found');
    assert.match(r.json.why, /headCwd/);
    assert.deepEqual(readdirSync(join(e.home, '.ccfzf/prompts')), []);
  } finally {
    srv.close();
  }
});

test('spawn из head, который сам ребёнок', () => {
  e.write(`.ccfzf/children/${e.me.sessionId}.json`, { sessionId: e.me.sessionId, head: 'top', headId: 'T' });
  const r = dry();
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.headId, e.me.sessionId);
});

test('--url без каталога трекеров', () => {
  rmSync(join(e.home, '.ccfzf/windows'), { recursive: true });
  const r = dry('--url', 'http://box-a.test:9722');
  assert.equal(r.code, 0, r.stdout);
  assert.ok(!('profileCwd' in r.json.body));
});

test('--url по имени машины из трекера', () => {
  const r = dry('--url', 'http://box-a:9722');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.profileCwd, '/p/demo');
});

test('name: знак ветки и коротко, без имени head впереди', () => {
  const r = run(SPAWN, ['--task', 'Wide 2/3', '--prompt-file', promptFile, '--dry-run'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.name, '.wide-2-3');
  assert.ok(r.json.body.head, 'head по-прежнему в теле');
});

test('name: пустой slug - отказ', () => {
  const r = run(SPAWN, ['--task', '---', '--prompt-file', promptFile, '--dry-run'], e.env);
  assert.notEqual(r.code, 0);
});

test('name: --name берётся как есть, без знака', () => {
  const r = run(SPAWN, ['--name', 'smi-test', '--prompt-file', promptFile, '--dry-run'], e.env);
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.name, 'smi-test');
});

// --- --session-id, --mcp-config, --dev-channels (бот-делегат регистрирует ребёнка заранее) ---

const SID = '11111111-2222-4333-8444-555555555555';

// Мок менеджера на порту 0: запоминает тела, отвечает данным статусом.
async function mockManager(status = 200) {
  const bodies = [];
  const srv = http.createServer((req, res) => {
    let b = '';
    req.on('data', (d) => (b += d));
    req.on('end', () => {
      const body = JSON.parse(b || '{}');
      bodies.push(body);
      const ok = status === 200;
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(ok ? { ok: true, sessionId: body.sessionId, name: body.name } : { ok: false, reason: 'nope' }));
    });
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  return { bodies, url: `http://127.0.0.1:${srv.address().port}`, close: () => srv.close() };
}

const mcpFile = () => {
  e.write('mcp.json', { mcpServers: { 'demo-bot': { command: 'node', args: ['x.ts'] } } });
  return join(e.home, 'mcp.json');
};
const prompts = () => readdirSync(join(e.home, '.ccfzf/prompts')).sort();
const mode = (rel) => statSync(join(e.home, rel)).mode & 0o777;

test('session-id flag is used', async () => {
  const m = await mockManager();
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID], e.env);
    assert.equal(r.code, 0, r.stdout);
    assert.equal(m.bodies[0].sessionId, SID);
    assert.equal(m.bodies[0].promptFile, join(e.home, `.ccfzf/prompts/${SID}.md`));
    assert.equal(r.json.sessionId, SID);
  } finally { m.close(); }
});

test('bad session-id fails', () => {
  for (const bad of [['--session-id', 'not-a-uuid'], ['--session-id']]) {
    const r = dry(...bad);
    assert.equal(r.code, 1, r.stdout);
    assert.match(r.json.error, /session-id/);
  }
});

test('dry-run prints sessionId, mcpConfig, devChannels', () => {
  const r = dry('--session-id', SID, '--mcp-config', mcpFile(), '--dev-channels', 'server:demo-bot');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.sessionId, SID);
  assert.equal(r.json.mcpConfig, join(e.home, `.ccfzf/prompts/${SID}.mcp.json`));
  assert.deepEqual(r.json.devChannels, ['server:demo-bot']);
  assert.deepEqual(prompts(), [], 'dry-run ничего не пишет');
});

test('mcp-config and dev-channels written next to prompt', async () => {
  const m = await mockManager();
  try {
    const src = mcpFile();
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID,
      '--mcp-config', src, '--dev-channels', 'server:demo-bot'], e.env);
    assert.equal(r.code, 0, r.stdout);
    assert.deepEqual(prompts(), [`${SID}.channels`, `${SID}.mcp.json`, `${SID}.md`, `${SID}.task.md`]);
    assert.equal(mode(`.ccfzf/prompts/${SID}.mcp.json`), 0o600);
    assert.equal(mode(`.ccfzf/prompts/${SID}.channels`), 0o600);
    assert.equal(readFileSync(join(e.home, `.ccfzf/prompts/${SID}.channels`), 'utf8'), 'server:demo-bot\n');
    assert.deepEqual(e.read(`.ccfzf/prompts/${SID}.mcp.json`), JSON.parse(readFileSync(src, 'utf8')));
    assert.ok(!('mcpConfig' in m.bodies[0]) && !('devChannels' in m.bodies[0]), 'в теле session-new лишних полей нет');
  } finally { m.close(); }
});

test('several dev-channels: one line each', async () => {
  const m = await mockManager();
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID,
      '--dev-channels', 'server:a1, server:b-2'], e.env);
    assert.equal(r.code, 0, r.stdout);
    assert.equal(readFileSync(join(e.home, `.ccfzf/prompts/${SID}.channels`), 'utf8'), 'server:a1\nserver:b-2\n');
  } finally { m.close(); }
});

test('bad dev-channel fails before request', async () => {
  const m = await mockManager();
  try {
    for (const bad of ['server:x; rm -rf ~', 'plugin:telegram', 'server:', 'server:-x', `server:${'a'.repeat(42)}`, '']) {
      const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--dev-channels', bad], e.env);
      assert.equal(r.code, 1, `${bad}: ${r.stdout}`);
      assert.match(r.json.error, /dev-channels/);
    }
    assert.equal(m.bodies.length, 0);
    assert.deepEqual(prompts(), []);
  } finally { m.close(); }
});

test('bad mcp-config fails before request', async () => {
  const m = await mockManager();
  try {
    e.write('broken.json', '{nope');
    for (const bad of [join(e.home, 'missing.json'), join(e.home, 'broken.json')]) {
      const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--mcp-config', bad], e.env);
      assert.equal(r.code, 1, r.stdout);
      assert.match(r.json.error, /mcp-config/);
    }
    assert.equal(m.bodies.length, 0);
    assert.deepEqual(prompts(), []);
  } finally { m.close(); }
});

test('side files removed on refusal', async () => {
  const m = await mockManager(403);
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID,
      '--mcp-config', mcpFile(), '--dev-channels', 'server:demo-bot'], e.env);
    assert.equal(r.code, 1, r.stdout);
    assert.equal(m.bodies.length, 1);
    assert.deepEqual(prompts(), []);
  } finally { m.close(); }
});

test('side files removed when the manager is unreachable', async () => {
  const m = await mockManager();
  m.close();
  await new Promise((r) => setTimeout(r, 50));
  const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID,
    '--mcp-config', mcpFile(), '--dev-channels', 'server:demo-bot'], e.env);
  assert.equal(r.code, 1, r.stdout);
  assert.deepEqual(prompts(), []);
});

test('no new flags: no side files, body unchanged', async () => {
  const m = await mockManager();
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url], e.env);
    assert.equal(r.code, 0, r.stdout);
    const sid = m.bodies[0].sessionId;
    assert.deepEqual(prompts(), [`${sid}.md`, `${sid}.task.md`]);
    assert.deepEqual(Object.keys(m.bodies[0]).sort(),
      ['cwd', 'head', 'headCwd', 'headId', 'name', 'permissionMode', 'promptFile', 'sessionId']);
  } finally { m.close(); }
});

// --- --fork: ребёнок стартует копией разговора head (Стас 2026-11-21) ---

// claude-wt-new в подставном PATH раньше настоящего: с поддержкой форка и модели или без.
const wtNew = (fork = true, model = true) => {
  const lines = [fork && 'f=$side_dir/$sid.fork', model && 'f=$side_dir/$sid.model'].filter(Boolean).map((l) => `${l}\n`).join('');
  e.write('bin/claude-wt-new', `#!/bin/sh\n${lines}exit 0\n`);
  chmodSync(join(e.home, 'bin/claude-wt-new'), 0o755);
};

test('fork: same body, fork file with the head id, own intro', async () => {
  wtNew();
  const m = await mockManager();
  try {
    const plain = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID], e.env);
    assert.equal(plain.code, 0, plain.stdout);
    rmSync(join(e.home, '.ccfzf/prompts'), { recursive: true, force: true });
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID, '--fork'], e.env);
    assert.equal(r.code, 0, r.stdout);
    assert.deepEqual(m.bodies[1], m.bodies[0], 'тело session-new от --fork не меняется');
    assert.deepEqual(prompts(), [`${SID}.fork`, `${SID}.md`, `${SID}.task.md`]);
    assert.equal(mode(`.ccfzf/prompts/${SID}.fork`), 0o600);
    assert.equal(readFileSync(join(e.home, `.ccfzf/prompts/${SID}.fork`), 'utf8'), `${e.me.sessionId}\n`);
    assert.equal(r.json.fork, true);
    assert.equal(r.json.forkFile, join(e.home, `.ccfzf/prompts/${SID}.fork`));
    const intro = readFileSync(join(e.home, `.ccfzf/prompts/${SID}.md`), 'utf8');
    assert.match(intro.split('\n')[0], /^Ты НЕ head/, 'роль - первой строкой');
    assert.match(intro, /не вызывай head-mark, session-spawn/);
    assert.match(intro, /SendMessage на "boss" с одной строкой "готов, cwd/);
  } finally { m.close(); }
});

test('fork: dry-run shows it and writes nothing', () => {
  wtNew();
  const r = dry('--session-id', SID, '--fork');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.fork, true);
  assert.match(r.json.intro, /^Ты НЕ head/);
  assert.match(r.json.intro, /приравниваются к командам пользователя/);
  assert.deepEqual(prompts(), [], 'dry-run ничего не пишет');
  const plain = dry('--session-id', SID);
  assert.deepEqual(plain.json.body, r.json.body);
  assert.ok(!('fork' in plain.json) && !('forkFile' in plain.json));
  assert.match(plain.json.intro, /^Ты дочерняя сессия head-сессии/);
});

test('fork takes no value', () => {
  const r = dry('--fork', 'yes');
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.error, /--fork takes no value/);
});

test('fork file removed on refusal', async () => {
  wtNew();
  const m = await mockManager(403);
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID, '--fork'], e.env);
    assert.equal(r.code, 1, r.stdout);
    assert.deepEqual(prompts(), []);
  } finally { m.close(); }
});

test('fork: an older claude-wt-new is refused before any write or request', async () => {
  wtNew(false);
  const m = await mockManager();
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID, '--fork'], e.env);
    assert.equal(r.code, 1, r.stdout);
    assert.match(r.json.error, /не умеет форк/);
    assert.equal(m.bodies.length, 0);
    assert.deepEqual(prompts(), []);
    const d = dry('--fork');
    assert.equal(d.code, 1, 'dry-run тоже отказывает');
    wtNew();
    const plainOld = dry();
    assert.equal(plainOld.code, 0, 'без --fork проверки нет');
  } finally { m.close(); }
});

test('fork: no claude-wt-new in PATH is refused', () => {
  const r = run(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--dry-run', '--fork'], { ...e.env, PATH: join(e.home, 'bin') + ':/usr/bin:/bin' });
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.error, /не найден в PATH/);
});

// --- --model: модель ребёнка (Стас 26.11: coord открывается с sonnet) ---

test('model: same body, model file 600, in the output', async () => {
  wtNew();
  const m = await mockManager();
  try {
    const plain = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID], e.env);
    assert.equal(plain.code, 0, plain.stdout);
    rmSync(join(e.home, '.ccfzf/prompts'), { recursive: true, force: true });
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID, '--model', 'sonnet'], e.env);
    assert.equal(r.code, 0, r.stdout);
    assert.deepEqual(m.bodies[1], m.bodies[0], 'тело session-new от --model не меняется');
    assert.ok(!('model' in m.bodies[1]));
    assert.deepEqual(prompts(), [`${SID}.md`, `${SID}.model`, `${SID}.task.md`]);
    assert.equal(mode(`.ccfzf/prompts/${SID}.model`), 0o600);
    assert.equal(readFileSync(join(e.home, `.ccfzf/prompts/${SID}.model`), 'utf8'), 'sonnet\n');
    assert.equal(r.json.model, 'sonnet');
    assert.equal(r.json.modelFile, join(e.home, `.ccfzf/prompts/${SID}.model`));
  } finally { m.close(); }
});

test('model: good names pass, dry-run shows them and writes nothing', () => {
  wtNew();
  for (const name of ['sonnet', 'opus', 'haiku', 'claude-sonnet-5-5', 'opus[1m]', 'claude-opus-5-5[1m]', 'claude-3.5-x', `a${'b'.repeat(60)}`]) {
    const r = dry('--session-id', SID, '--model', name);
    assert.equal(r.code, 0, `${name}: ${r.stdout}`);
    assert.equal(r.json.model, name);
    assert.equal(r.json.modelFile, join(e.home, `.ccfzf/prompts/${SID}.model`));
    assert.ok(!('model' in r.json.body), 'в теле session-new модели нет');
  }
  assert.deepEqual(prompts(), [], 'dry-run ничего не пишет');
  const plain = dry('--session-id', SID);
  assert.ok(!('model' in plain.json) && !('modelFile' in plain.json));
});

test('model: bad names fail before any write or request', async () => {
  wtNew();
  const m = await mockManager();
  try {
    const bad = [['--model'], ['--model', ''], ['--model', 'Sonnet'], ['--model', '-sonnet'], ['--model', '.x'],
      ['--model', 'sonnet; rm -rf ~'], ['--model', 'son net'], ['--model', 'a/b'], ['--model', '$(id)'],
      ['--model', 'сонет'], ['--model', 'a\nb'], ['--model', `a${'b'.repeat(61)}`]];
    for (const extra of bad) {
      const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, ...extra], e.env);
      assert.equal(r.code, 1, `${JSON.stringify(extra)}: ${r.stdout}`);
      assert.match(r.json.error, /--model/);
    }
    assert.equal(m.bodies.length, 0);
    assert.deepEqual(prompts(), []);
  } finally { m.close(); }
});

test('model file removed on refusal and when the manager is unreachable', async () => {
  wtNew();
  const m = await mockManager(403);
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID, '--model', 'sonnet'], e.env);
    assert.equal(r.code, 1, r.stdout);
    assert.deepEqual(prompts(), []);
  } finally { m.close(); }
  const gone = await mockManager();
  gone.close();
  await new Promise((r) => setTimeout(r, 50));
  const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', gone.url, '--session-id', SID, '--model', 'sonnet'], e.env);
  assert.equal(r.code, 1, r.stdout);
  assert.deepEqual(prompts(), []);
});

test('model: an older claude-wt-new is refused before any write or request', async () => {
  wtNew(true, false);
  const m = await mockManager();
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID, '--model', 'sonnet'], e.env);
    assert.equal(r.code, 1, r.stdout);
    assert.match(r.json.error, /--model/);
    assert.match(r.json.error, /claude-wt-new/);
    assert.equal(m.bodies.length, 0);
    assert.deepEqual(prompts(), []);
    assert.equal(dry('--model', 'sonnet').code, 1, 'dry-run тоже отказывает');
    assert.equal(dry('--fork').code, 0, 'форк от проверки модели не зависит');
    assert.equal(dry().code, 0, 'без --model проверки нет');
  } finally { m.close(); }
});

test('model: no claude-wt-new in PATH is refused', () => {
  const r = run(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--dry-run', '--model', 'sonnet'], { ...e.env, PATH: join(e.home, 'bin') + ':/usr/bin:/bin' });
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.error, /--model/);
  assert.match(r.json.error, /PATH/);
});

test('model and fork together: both files', async () => {
  wtNew();
  const m = await mockManager();
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID, '--fork', '--model', 'opus[1m]'], e.env);
    assert.equal(r.code, 0, r.stdout);
    assert.deepEqual(prompts(), [`${SID}.fork`, `${SID}.md`, `${SID}.model`, `${SID}.task.md`]);
    assert.equal(readFileSync(join(e.home, `.ccfzf/prompts/${SID}.model`), 'utf8'), 'opus[1m]\n');
  } finally { m.close(); }
});

// --- права и исход неизвестен (Review Focus 5) ---

test('таймаут менеджера: код 3, sessionId и запрет повтора, копии остаются', async () => {
  const srv = http.createServer(() => {}); // запрос принят, ответа нет
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  try {
    const url = `http://127.0.0.1:${srv.address().port}`;
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', url, '--session-id', SID, '--timeout', '1'], e.env);
    assert.equal(r.code, 3, r.stdout);
    assert.equal(r.json.ok, 'unknown');
    assert.equal(r.json.sessionId, SID);
    assert.equal(r.json.error, 'TimeoutError');
    assert.match(r.json.hint, /do NOT resend/);
    assert.equal(r.json.taskFile, join(e.home, `.ccfzf/prompts/${SID}.task.md`));
    assert.deepEqual(prompts(), [`${SID}.md`, `${SID}.task.md`], 'окно ещё может открыться — копии нужны ребёнку');
  } finally { srv.closeAllConnections(); srv.close(); }
});

test('bypassPermissions детям нельзя: ни унаследованным, ни явным', () => {
  let r = dry('--permission-mode', 'bypassPermissions');
  assert.equal(r.code, 1);
  assert.match(r.json.error, /bypassPermissions/);
  assert.match(r.json.why, /не принимается/);
  e.env.SPAWN_TEST_HEAD_MODE = 'bypassPermissions';
  r = dry();
  assert.equal(r.code, 1);
  assert.match(r.json.why, /--permission-mode auto/);
  r = dry('--permission-mode', 'auto');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.permissionMode, 'auto');
});

test('режим head из его транскрипта, без подсказки теста', () => {
  delete e.env.SPAWN_TEST_HEAD_MODE;
  e.write(`.claude/projects/-p-demo/${e.me.sessionId}.jsonl`, '{"type":"user","permissionMode":"default"}\n{"type":"user","permissionMode":"acceptEdits"}\n');
  const r = dry();
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.body.permissionMode, 'acceptEdits');
});

test('только из head: без метки — отказ', () => {
  e.write(`.ccfzf/heads/${e.me.sessionId}.json`, '');
  const r = dry();
  assert.equal(r.code, 1);
  assert.deepEqual(r.json, { ok: false, error: 'session-spawn только из head-сессии: вызови /head-session', why: 'no head mark', sessionId: e.me.sessionId });
});

test('нет свежего трекера с http; --machine выбирает трекер', () => {
  e.tracker('box-b', { projects: [], httpHost: 'box-b.test' });
  let r = dry('--machine', 'box-b');
  assert.equal(r.code, 0, r.stdout);
  assert.equal(r.json.url, 'http://box-b.test:9722/claude-wt/session-new');
  assert.equal(r.json.urlSource, '~/.ccfzf/windows/box-b.json');
  r = dry('--machine', 'ghost');
  assert.equal(r.code, 1);
  assert.deepEqual(r.json, { ok: false, error: 'no fresh tracker with http in ~/.ccfzf/windows (pass --machine or --url)', machine: 'ghost' });
});

test('кривой --url — отказ до записи и запроса', () => {
  const r = run(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', 'nonsense'], e.env);
  assert.equal(r.code, 1, r.stdout);
  assert.match(r.json.error, /bad --url/);
  assert.deepEqual(prompts(), []);
});

test('dry-run целиком: тело, вступление, taskFile', () => {
  const r = dry('--session-id', SID);
  assert.equal(r.code, 0, r.stdout);
  assert.deepEqual(Object.keys(r.json), ['dryRun', 'url', 'urlSource', 'nameRequested', 'sessionId', 'body', 'intro', 'taskFile', 'taskBytes']);
  assert.equal(r.json.url, 'http://box-a.test:9722/claude-wt/session-new');
  assert.equal(r.json.nameRequested, '.t');
  assert.equal(r.json.taskBytes, Buffer.byteLength('задание'));
  assert.match(r.json.intro, new RegExp(`^Ты дочерняя сессия head-сессии "boss" \\(sessionId ${e.me.sessionId}\\)`));
  assert.match(r.json.intro, /--timeout 0, поле name/);
  assert.match(r.json.intro, /приравниваются к командам пользователя/);
  assert.match(r.json.intro, /PR, мерж и деплой/);
});

// --- ответ менеджера целиком: эти ключи читают бот-делегат и SKILL.md по имени ---

test('успех: ответ целиком — sessionId, name, head, headId, url, promptFile, taskFile, next', async () => {
  const m = await mockManager();
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID], e.env);
    assert.equal(r.code, 0, r.stdout);
    assert.deepEqual(r.json, {
      ok: true, sessionId: SID, name: '.t', head: 'boss', headId: e.me.sessionId,
      url: `${m.url}/claude-wt/session-new`,
      promptFile: join(e.home, `.ccfzf/prompts/${SID}.md`), taskFile: join(e.home, `.ccfzf/prompts/${SID}.task.md`),
      next: 'session-find --session-id, wait for the child\'s "готов" message, then SendMessage the taskFile text to its from, notify_when_idle: true',
    });
  } finally { m.close(); }
});

test('отказ 403: ответ целиком', async () => {
  const m = await mockManager(403);
  try {
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', m.url, '--session-id', SID], e.env);
    assert.equal(r.code, 1);
    assert.deepEqual(Object.keys(r.json), ['ok', 'status', 'error', 'why', 'url', 'sessionId', 'name']);
    assert.equal(r.json.status, 403);
    assert.equal(r.json.error, 'nope');
  } finally { m.close(); }
});

test('200 с оборванным телом: исход неизвестен — код 3, копии остаются', async () => {
  const srv = http.createServer((req, res) => {
    req.resume();
    req.on('end', () => {
      res.writeHead(200, { 'content-type': 'application/json', 'content-length': '200' });
      res.write('{"ok":tr');
      setTimeout(() => req.socket.destroy(), 50);
    });
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  try {
    const url = `http://127.0.0.1:${srv.address().port}`;
    const r = await runAsync(SPAWN, ['--task', 't', '--prompt-file', promptFile, '--url', url, '--session-id', SID], e.env);
    assert.equal(r.code, 3, r.stdout);
    assert.equal(r.json.ok, 'unknown');
    assert.equal(r.json.sessionId, SID);
    assert.match(r.json.hint, /do NOT resend/);
    assert.deepEqual(prompts(), [`${SID}.md`, `${SID}.task.md`]);
  } finally { srv.close(); }
});

test('вступление ребёнку зовёт CLI: claude-wt session find, а не путь скрипта скилла', () => {
  wtNew();
  for (const extra of [[], ['--fork']]) {
    const r = dry('--session-id', SID, ...extra);
    assert.equal(r.code, 0, r.stdout);
    assert.ok(r.json.intro.includes(`claude-wt session find --session-id ${e.me.sessionId} --timeout 0, поле name`), r.json.intro);
    assert.ok(!r.json.intro.includes('.mjs'), 'ни find.mjs, ни spawn.mjs');
  }
  assert.match(dry('--session-id', SID, '--fork').json.intro, /и вызов claude-wt session spawn, которым head открыл тебя/);
});
