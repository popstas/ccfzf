// waiting: кто из живых сессий чего ждёт — разрешения, ответа на вопрос, ответа в чате, мержа PR.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, chmodSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { runCli, world, now } from './helpers.mjs';
import { asksHuman, promptKind } from '../../cli/lib/commands/waiting.mjs';

const ID = (n) => `cccccccc-0000-4000-8000-${String(n).padStart(12, '0')}`;
const T = now();

const sess = (n, title, agent, extra = {}) => ({ id: ID(n), title, live: true, cwd: '/w', mtime: T, kind: 'interactive', ...(agent ? { agent: { updated: T - 60, ...agent } } : {}), ...extra });

const PR_OPEN = 'https://github.com/o/r/pull/1';
const PR_MERGED = 'https://github.com/o/r/pull/2';

const SESSIONS = [
  sess(1, 'perm', { state: 'question', event: 'attention', message: 'Claude needs your permission to use Bash', updated: T - 120 }),
  sess(2, 'ask', { state: 'active', event: 'tool-start', question: 'Which option?', updated: T - 30 }),
  sess(3, 'decide', { state: 'idle', event: 'compact', summary: 'Готово. Жду твоих решений по вопросам из сводки.', updated: T - 86400 * 2 }),
  sess(4, 'done', { state: 'review', event: 'stop', summary: 'Вопросов к тебе за этот шаг не появилось.' }),
  sess(5, 'pr-open', { state: 'idle', event: 'attention', message: 'Claude is waiting for your input', summary: 'PR открыт.', pr_url: PR_OPEN, updated: T - 3600 * 5 }),
  sess(6, 'pr-merged', { state: 'idle', summary: 'PR смержен.', pr_url: PR_MERGED }),
  sess(7, 'working', { state: 'active', event: 'tool-done', pr_url: PR_OPEN }),
  sess(8, 'closed', { state: 'question', message: 'x' }, { live: false }),
  sess(9, 'noagent', null),
  sess(10, 'mailfail', { state: 'question', event: 'attention', message: '.agent-mail failed', updated: T - 90 }),
];

// gh-заглушка: состояние по номеру PR, каждый вызов пишется в лог.
function ghStub(w, body) {
  const p = join(w.dir, 'bin', 'gh');
  writeFileSync(p, `#!/bin/sh\necho "$3" >> '${join(w.dir, 'gh.log')}'\n${body}\n`);
  chmodSync(p, 0o755);
  return p;
}
const GH_OK = 'case "$3" in *pull/1) echo \'{"state":"OPEN"}\';; *pull/2) echo \'{"state":"MERGED"}\';; *) exit 1;; esac';

function run(args, { sessions = SESSIONS, children = [], gh = GH_OK, env = {} } = {}) {
  const w = world({ state: { sessions, snapshots: [] }, children });
  try {
    const ghBin = gh === null ? join(w.dir, 'no-such-gh') : ghStub(w, gh);
    const e = { ...w.env, GH_BIN: ghBin, CLAUDE_WT_CACHE_DIR: join(w.dir, 'cache'), ...env };
    const r = runCli(['waiting', ...args], e);
    const again = env.AGAIN ? runCli(['waiting', ...args], e) : null;
    const log = existsSync(join(w.dir, 'gh.log')) ? readFileSync(join(w.dir, 'gh.log'), 'utf8').trim().split('\n') : [];
    const cache = existsSync(join(w.dir, 'cache', 'prs.json')) ? JSON.parse(readFileSync(join(w.dir, 'cache', 'prs.json'), 'utf8')) : null;
    return { ...r, o: args.includes('--json') && r.stdout ? JSON.parse(r.stdout) : null, again, log, cache };
  } finally {
    w.cleanup();
  }
}

const byName = (o) => Object.fromEntries(o.waiting.map((e) => [e.name, e]));

test('виды ожидания: разрешение, вопрос, ответ в чате, открытый PR; порядок — по срочности', () => {
  const r = run(['--json']);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.o.live, 9);
  assert.deepEqual(r.o.waiting.map((e) => [e.name, e.kind]), [
    ['perm', 'permission'], ['ask', 'question'], ['mailfail', 'attention'], ['decide', 'reply'], ['pr-open', 'pr'],
  ]);
  const w = byName(r.o);
  assert.equal(w.perm.text, 'Claude needs your permission to use Bash');
  assert.equal(w.perm.hint, 'approve in its window');
  assert.equal(w.ask.text, 'Which option?');
  assert.equal(w.mailfail.text, '.agent-mail failed');
  assert.equal(w.mailfail.hint, 'look at its window', 'не всякое уведомление — запрос разрешения');
  assert.equal(w.ask.hint, 'answer in its window');
  assert.equal(w.decide.hint, 'reply in its chat');
  assert.equal(w['pr-open'].hint, `merge PR ${PR_OPEN}`);
  assert.deepEqual(w['pr-open'].pr, { url: PR_OPEN, state: 'OPEN' });
  assert.equal(w.decide.short, ID(3).slice(0, 8));
  assert.ok(Math.abs(w.decide.ageSec - 86400 * 2) < 5, 'возраст — от agent.updated');
  assert.equal(w.decide.since, T - 86400 * 2);
});

test('не ждут: смерженный PR, работающая сессия с PR, закрытая, без записи агента, сводка без вопроса', () => {
  const r = run(['--json']);
  const names = r.o.waiting.map((e) => e.name);
  for (const n of ['pr-merged', 'working', 'closed', 'noagent', 'done']) assert.ok(!names.includes(n), n);
});

test('gh спрашивается раз на URL, ответ кэшируется: смерженный навсегда, открытый — на 10 минут', () => {
  const r = run(['--json'], { env: { AGAIN: '1' } });
  assert.equal(r.again.status, 0, r.again.stderr);
  assert.deepEqual(r.log.sort(), [PR_OPEN, PR_MERGED].sort(), 'второй вызов gh не звал');
  assert.equal(r.cache[PR_MERGED].state, 'MERGED');
  assert.equal(r.cache[PR_OPEN].state, 'OPEN');
});

test('открытый PR старше 10 минут в кэше перепроверяется', () => {
  const w = world({ state: { sessions: [SESSIONS[4]], snapshots: [] } });
  try {
    const cacheDir = join(w.dir, 'cache');
    const e = { ...w.env, GH_BIN: ghStub(w, GH_OK), CLAUDE_WT_CACHE_DIR: cacheDir };
    runCli(['waiting', '--json'], e);
    const file = join(cacheDir, 'prs.json');
    const db = JSON.parse(readFileSync(file, 'utf8'));
    db[PR_OPEN].checkedAt -= 11 * 60;
    writeFileSync(file, JSON.stringify(db));
    runCli(['waiting', '--json'], e);
    assert.equal(readFileSync(join(w.dir, 'gh.log'), 'utf8').trim().split('\n').length, 2);
  } finally {
    w.cleanup();
  }
});

test('без gh PR помечен unknown и всё равно в списке', () => {
  const r = run(['--json'], { gh: null });
  assert.equal(r.status, 0, r.stderr);
  const w = byName(r.o);
  assert.equal(w['pr-open'].pr.state, 'unknown');
  assert.equal(w['pr-open'].pr.reason, 'gh not found');
  assert.equal(w['pr-merged'].kind, 'pr', 'неизвестно, смержен ли, — показываем');
  assert.equal(r.cache, null, 'неизвестное не кэшируется');
});

test('повисший gh не вешает команду: таймаут → unknown', () => {
  const t0 = Date.now();
  const r = run(['--json'], { gh: 'exec sleep 30', env: { CLAUDE_WT_GH_TIMEOUT_MS: '300' } });
  assert.equal(r.status, 0, r.stderr);
  assert.ok(Date.now() - t0 < 8000, `заняло ${Date.now() - t0} мс`);
  assert.equal(byName(r.o)['pr-open'].pr.reason, 'gh timeout');
});

test('сессия с вопросом и открытым PR — вид question, PR в подсказке', () => {
  const r = run(['--json'], { sessions: [sess(1, 'both', { state: 'question', question: 'Ок?', pr_url: PR_OPEN })] });
  const e = r.o.waiting[0];
  assert.equal(e.kind, 'question');
  assert.equal(e.pr.state, 'OPEN');
  assert.equal(e.hint, `answer in its window; then merge PR ${PR_OPEN}`);
});

test('--tree: ждущий ребёнок под неждущим head, head — заголовком', () => {
  const sessions = [
    sess(10, 'head', { state: 'review', summary: 'Раздал задачи.' }),
    sess(11, '└kid', { state: 'question', message: 'Claude needs your permission' }),
    sess(12, '└kid2', { state: 'idle', summary: 'Жду твоего ока на мерж' }),
    sess(13, 'solo', { state: 'idle', summary: 'Что дальше?' }),
  ];
  const children = [{ sessionId: ID(11), headId: ID(10) }, { sessionId: ID(12), headId: ID(10) }];
  const r = run(['--tree', '--json'], { sessions, children });
  assert.equal(r.status, 0, r.stderr);
  const roots = Object.fromEntries(r.o.tree.map((n) => [n.name, n]));
  assert.equal(roots.head.waiting, false);
  assert.deepEqual(roots.head.children.map((n) => [n.name, n.kind]), [['└kid', 'permission'], ['└kid2', 'reply']]);
  assert.equal(roots.solo.waiting, true);
  assert.equal(r.o.waiting.find((e) => e.name === '└kid').parent, ID(10));
  const t = run(['--tree'], { sessions, children });
  assert.match(t.stdout, /^head {2}cccccccc {2}\(not waiting\)$/m);
  assert.match(t.stdout, /^ {2}└kid {2}cccccccc {2}permission {2}1m {2}-> approve in its window$/m);
});

test('без --json — сводка для человека; никого — так и сказано', () => {
  const r = run([]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /^waiting: 5 of 9 live \(permission 1, question 1, attention 1, reply 1, pr 1\)/);
  assert.match(r.stdout, /decide {2}cccccccc {2}reply {2}2d {2}-> reply in its chat\n {4}Готово\. Жду твоих решений/);
  const n = run([], { sessions: [SESSIONS[3]] });
  assert.equal(n.stdout.trim(), 'nothing is waiting (1 live sessions)');
});

test('эвристика «сводка — вопрос к человеку»', () => {
  for (const s of ['Жду твоих решений по вопросам из сводки.', 'Что дальше?', 'жду ок на мерж', 'Нужно твоё решение по схеме', 'Let me know which one.', 'Берём «A»?', 'Мержим (#12)?'])
    assert.equal(asksHuman(s), true, s);
  for (const s of ['Оба пункта сделаны: чекаут обновлён.', 'Вопросов к тебе за этот шаг не появилось.', 'Ждёт ответа сервера, ретраю.', 'см. https://x.example/y?a=1 там всё', ''])
    assert.equal(asksHuman(s), false, s);
  assert.equal(promptKind({ state: 'active', summary: 'Что дальше?' }), null, 'работающая не ждёт ответа в чате');
  assert.equal(promptKind({ state: 'active', question: 'A или B?' }), 'question');
});
