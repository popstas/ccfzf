// Стенд для команд, переехавших из скриптов скиллов (session-*, head-*): как
// harness.mjs скиллов — временный HOME с ~/.claude и ~/.ccfzf и заглушка
// `claude` в PATH; живые записи и менеджер на :9722 не трогаются.
// Окружение вычищается так же (CLAUDE_*, CCFZF_*, SPAWN_TEST_*) — команды
// обязаны работать на умолчаниях, как старые скрипты под обёрткой.
import { spawn, spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { CLI } from './helpers.mjs';

let nextPid = 900001;

export function legacyWorld({ name = 'boss', cwd = '/p/demo', sessionId = randomUUID(), pid = nextPid++ } = {}) {
  const home = mkdtempSync(join(tmpdir(), 'claude-wt-legacy-'));
  for (const d of ['.claude/sessions', '.claude/projects', '.ccfzf/heads', '.ccfzf/children', '.ccfzf/windows', '.ccfzf/prompts', 'bin']) {
    mkdirSync(join(home, d), { recursive: true });
  }
  const me = { sessionId, pid, name, cwd };
  const agentsFile = join(home, 'agents.json');
  writeFileSync(join(home, 'bin', 'claude'), '#!/bin/sh\ncat "$FAKE_AGENTS_FILE"\n');
  chmodSync(join(home, 'bin', 'claude'), 0o755);

  const write = (rel, obj) => {
    const p = join(home, rel);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, typeof obj === 'string' ? obj : JSON.stringify(obj));
  };
  const read = (rel) => JSON.parse(readFileSync(join(home, rel), 'utf8'));
  const exists = (rel) => existsSync(join(home, rel));
  const agents = (list) => writeFileSync(agentsFile, JSON.stringify(list));
  const meAgent = { pid: me.pid, cwd, kind: 'interactive', sessionId: me.sessionId, name, status: 'busy' };

  write(`.claude/sessions/${me.pid}.json`, { pid: me.pid, sessionId: me.sessionId, name, cwd, procStart: '1' });
  agents([meAgent]);

  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(CLAUDE_|CCFZF_|SPAWN_TEST_|SESSION_RENAME_|WT_|XDG_|FAKE_)/.test(k)));
  Object.assign(env, {
    HOME: home,
    PATH: `${join(home, 'bin')}:${process.env.PATH}`,
    CLAUDE_CODE_SESSION_ID: me.sessionId,
    CLAUDE_PID: String(me.pid),
    FAKE_AGENTS_FILE: agentsFile,
    SPAWN_TEST_HEAD_MODE: 'auto',
  });

  return {
    home, env, me, meAgent, write, read, exists, agents,
    mark: () => write(`.ccfzf/heads/${me.sessionId}.json`, { sessionId: me.sessionId, name, cwd, createdAt: 1 }),
    // Свежий файл трекера машины окна с http-портом.
    tracker: (host, { projects = [], httpHost, port = 9722 } = {}) => write(`.ccfzf/windows/${host}.json`, {
      host, generated: Math.floor(Date.now() / 1000), windows: {},
      http: { port, ...(httpHost && { host: httpHost }) },
      projects: projects.map((p) => ({ cwd: p, name: p.split('/').pop() })),
    }),
    cleanup: () => rmSync(home, { recursive: true, force: true }),
  };
}

const parse = (s) => { try { return JSON.parse(s); } catch { return null; } };

// Команда CLI: cmd — ['session', 'find'] и т.п.
export function run(cmd, args, env, { timeout = 10000 } = {}) {
  const r = spawnSync(process.execPath, [CLI, ...cmd, ...args], { env, encoding: 'utf8', timeout });
  return { code: r.status, stdout: r.stdout, stderr: r.stderr, json: parse(r.stdout), timedOut: r.error?.code === 'ETIMEDOUT' };
}

// То же асинхронно: для тестов с мок-сервером и живыми процессами в этом же процессе.
export function runAsync(cmd, args, env, { timeout = 10000, bin = CLI } = {}) {
  return new Promise((resolve) => {
    const c = spawn(process.execPath, [bin, ...cmd, ...args], { env });
    let stdout = '';
    let stderr = '';
    c.stdout.on('data', (d) => (stdout += d));
    c.stderr.on('data', (d) => (stderr += d));
    const t = setTimeout(() => c.kill('SIGKILL'), timeout);
    c.on('close', (code) => {
      clearTimeout(t);
      resolve({ code, stdout, stderr, json: parse(stdout) });
    });
  });
}

// Старый скрипт скилла (снимок для сравнения): каталог — WT_LEGACY_SKILLS,
// без него сравнительные тесты пропускаются. rel — 'session-find/find.mjs'.
export const LEGACY = process.env.WT_LEGACY_SKILLS || null;
export function runOld(rel, args, env, opts) {
  return runAsync([], args, env, { ...opts, bin: join(LEGACY, rel) });
}

// Для сравнения: домашний каталог стенда → <HOME>, затем отброс полей,
// которые по природе разные между прогонами (время, случайные id).
export function normalize(o, home, drop = []) {
  const s = JSON.stringify(o ?? null).replaceAll(home, '<HOME>');
  return JSON.parse(s, (k, v) => (drop.includes(k) ? undefined : v));
}

// Настоящий процесс, которому close может слать сигналы: `sleep 60` с procStart из /proc.
export function liveProcess() {
  const c = spawn('sleep', ['60'], { stdio: 'ignore' });
  const stat = readFileSync(`/proc/${c.pid}/stat`, 'utf8');
  const procStart = stat.split(') ')[1].split(' ')[19];
  const exited = new Promise((r) => c.on('exit', (code, signal) => r({ code, signal })));
  return { pid: c.pid, procStart, exited, kill: () => { try { c.kill('SIGKILL'); } catch {} } };
}
