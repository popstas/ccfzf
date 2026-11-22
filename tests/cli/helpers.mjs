// Общее для тестов claude-wt: запуск CLI подпроцессом в подставном окружении,
// заглушки ccfzf/claude, каталоги трекеров и детей, мок-сервер менеджера.
import { spawnSync, spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, chmodSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const CLI = join(ROOT, 'cli', 'claude-wt.mjs');

// Окружение без живых каталогов: HOME и все пути — во временном каталоге.
const BASE_ENV = { PATH: process.env.PATH, LANG: 'C.UTF-8' };

export function runCli(args, env = {}) {
  return spawnSync(process.execPath, [CLI, ...args], {
    encoding: 'utf8',
    timeout: 20000,
    env: { ...BASE_ENV, HOME: tmpdir(), ...env },
  });
}

// То же, но асинхронно: нужно, когда в этом же процессе крутится мок-сервер.
export function runCliAsync(args, env = {}) {
  return new Promise((resolve) => {
    const p = spawn(process.execPath, [CLI, ...args], {
      env: { ...BASE_ENV, HOME: tmpdir(), ...env },
    });
    let stdout = '';
    let stderr = '';
    p.stdout.on('data', (d) => { stdout += d; });
    p.stderr.on('data', (d) => { stderr += d; });
    p.on('close', (status) => resolve({ status, stdout, stderr }));
  });
}

// Подставной мир: state для `ccfzf --state`, агенты для `claude agents --json`,
// файлы трекеров и записи детей. Возвращает env для CLI и уборку.
export function world({ state = { sessions: [], snapshots: [] }, agents = [], trackers = {}, children = [], heads = [], caller } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'claude-wt-test-'));
  const bin = join(dir, 'bin');
  const windowsDir = join(dir, 'windows');
  const childrenDir = join(dir, 'children');
  const headsDir = join(dir, 'heads');
  for (const d of [bin, windowsDir, childrenDir, headsDir]) mkdirSync(d, { recursive: true });
  writeFileSync(join(dir, 'state.json'), JSON.stringify(state));
  writeFileSync(join(dir, 'agents.json'), JSON.stringify(agents));
  const stub = (name, file) => {
    const p = join(bin, name);
    writeFileSync(p, `#!/bin/sh\ncat '${join(dir, file)}'\n`);
    chmodSync(p, 0o755);
    return p;
  };
  for (const [name, o] of Object.entries(trackers)) {
    writeFileSync(join(windowsDir, `${name}.json`), typeof o === 'string' ? o : JSON.stringify(o));
  }
  for (const c of children) writeFileSync(join(childrenDir, `${c.sessionId}.json`), JSON.stringify(c));
  for (const h of heads) writeFileSync(join(headsDir, `${h.sessionId}.json`), JSON.stringify(h));
  const env = {
    HOME: dir,
    CCFZF_BIN: stub('ccfzf', 'state.json'),
    CLAUDE_BIN: stub('claude', 'agents.json'),
    CCFZF_WINDOWS_DIR: windowsDir,
    CCFZF_CHILDREN_DIR: childrenDir,
    CCFZF_HEADS_DIR: headsDir,
  };
  if (caller) env.CLAUDE_CODE_SESSION_ID = caller;
  return { dir, env, windowsDir, childrenDir, headsDir, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

// Мок менеджера: запоминает запросы, отвечает тем, что вернёт reply(path, body).
// reply может вернуть {status, body}, {status, raw} (тело как есть), 'hang' — ответа
// нет вовсе, или 'destroy' — соединение рвётся после чтения запроса.
export async function mockManager(reply) {
  const requests = [];
  const server = createServer((req, res) => {
    let raw = '';
    req.on('data', (c) => { raw += c; });
    req.on('end', () => {
      let body = null;
      try { body = raw ? JSON.parse(raw) : null; } catch { body = raw; }
      requests.push({ method: req.method, path: req.url, body });
      const r = reply(req.url, body);
      if (r === 'hang') return;
      // Запрос дошёл, а соединение оборвалось до ответа (менеджер упал).
      if (r === 'destroy') { req.socket.destroy(); return; }
      res.writeHead(r.status ?? 200, { 'Content-Type': 'application/json' });
      res.end(r.raw !== undefined ? r.raw : JSON.stringify(r.body ?? {}));
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const { port } = server.address();
  return {
    url: `http://127.0.0.1:${port}`,
    port,
    requests,
    close: () => { server.closeAllConnections?.(); return new Promise((r) => server.close(r)); },
  };
}

export const now = () => Math.floor(Date.now() / 1000);
