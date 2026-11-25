// Откуда CLI берёт картину: `ccfzf --state`, файлы трекеров окон,
// записи детей и отметки head, `claude agents --json`.
// Всё подменяется окружением — так тесты не трогают живые каталоги.
import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

// Файл трекера старше этого — протух (тот же порог, что у session-spawn).
export const TRACKER_MAX_AGE_SEC = 15 * 60;

export function paths(env = process.env) {
  const home = env.HOME || homedir();
  return {
    ccfzfBin: env.CCFZF_BIN || 'ccfzf',
    claudeBin: env.CLAUDE_BIN || 'claude',
    windowsDir: env.CCFZF_WINDOWS_DIR || join(home, '.ccfzf', 'windows'),
    childrenDir: env.CCFZF_CHILDREN_DIR || join(home, '.ccfzf', 'children'),
    headsDir: env.CCFZF_HEADS_DIR || join(home, '.ccfzf', 'heads'),
    stateDir: env.CLAUDE_WT_STATE_DIR || join(home, '.claude', 'claude-wt'),
  };
}

export const readJson = (p) => { try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return null; } };

function jsonFiles(dir) {
  try { return readdirSync(dir).filter((f) => f.endsWith('.json')); } catch { return []; }
}

function run(bin, args, what) {
  try {
    return execFileSync(bin, args, { encoding: 'utf8', timeout: 60000, maxBuffer: 256 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (e) {
    const why = (e.stderr && String(e.stderr).trim()) || e.message;
    throw new Error(`${what} failed: ${why}`);
  }
}

export function readState({ bin }) {
  const out = run(bin, ['--state'], 'ccfzf --state');
  try {
    return JSON.parse(out);
  } catch (e) {
    throw new Error(`ccfzf --state failed: bad JSON (${e.message})`);
  }
}

// Живые сессии, как их видит сам Claude Code: [{sessionId, name, status, ...}].
export function readAgents({ bin }) {
  const out = run(bin, ['agents', '--json'], 'claude agents --json');
  const list = JSON.parse(out);
  return Array.isArray(list) ? list : [];
}

// Файлы трекеров окон: где у машины менеджер и свеж ли файл.
// Битый файл пропускается; файл без http (мак) остаётся, но с http: null.
// projects — cwd проектов машины (профиль терминала ребёнка), openSession — принимает ли
// трекер просьбы открыть сессию: нет поля или мусор — да (windows11-manager его не пишет), у мака false — как в ccfzf.
export function readTrackers(dir, now = Date.now() / 1000) {
  const out = [];
  for (const file of jsonFiles(dir)) {
    const o = readJson(join(dir, file));
    if (!o || typeof o !== 'object' || Array.isArray(o)) continue;
    const port = o.http?.port;
    const host = o.host ?? file.replace(/\.json$/, '');
    const http = Number.isInteger(port) && port > 0 ? { host: o.http.host || host, port } : null;
    const generated = Number(o.generated) || 0;
    const projects = Array.isArray(o.projects) ? o.projects.map((x) => x?.cwd).filter(Boolean) : [];
    out.push({ file, host, http, generated, fresh: now - generated < TRACKER_MAX_AGE_SEC, projects, openSession: typeof o.openSession === 'boolean' ? o.openSession : true });
  }
  return out;
}

// Записи детей: [{sessionId, headId, createdAt, ...}], id — из имени файла, если в записи нет.
export function readChildren(dir) {
  return jsonFiles(dir)
    .map((f) => {
      const o = readJson(join(dir, f));
      return o && typeof o === 'object' ? { ...o, sessionId: o.sessionId || f.replace(/\.json$/, '') } : null;
    })
    .filter(Boolean);
}

// Отметки head: множество sessionId.
export function readHeads(dir) {
  return new Set(jsonFiles(dir).map((f) => readJson(join(dir, f))?.sessionId || f.replace(/\.json$/, '')));
}
