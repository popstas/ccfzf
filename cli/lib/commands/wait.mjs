// claude-wt wait set|clear|show [<session>]: агент сам объявляет, чего ждёт.
// Запись — `<id>.wait.json` в каталоге состояний хуков (рядом с state.json):
// оттуда её отдаёт `ccfzf --state` полем `wait`, а снимает `wait clear` и хук
// wt-progress.sh на промпте человека или сообщении своего head.
// Цель — своя сессия: вызывающая по умолчанию, иначе она же или её потомок.
import { mkdirSync, renameSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { EXIT } from '../out.mjs';
import { paths, readJson } from '../sources.mjs';
import { NO_CALLER, context, ownTarget } from '../act.mjs';

export const WAIT_KINDS = ['decision', 'review', 'external'];
const ASK_MAX = 500;

const fileOf = (env, id) => join(paths(env).stateDir, `${id}.wait.json`);

// Цель: без аргумента — сама вызывающая сессия (без чтения картины), иначе своя по own/lineage.
function target(args, env) {
  if (!env.CLAUDE_CODE_SESSION_ID) return { fail: { code: EXIT.REFUSED, error: NO_CALLER } };
  if (!args[0]) return { id: env.CLAUDE_CODE_SESSION_ID };
  const ctx = context(env);
  if (ctx.fail) return ctx;
  const t = ownTarget(args[0], ctx.pic);
  return t.fail ? t : { id: t.session.id };
}

// Запись с диска в том виде, в каком её отдаёт ccfzf (waits_all): только известные поля.
export function readWait(env, id) {
  const o = readJson(fileOf(env, id));
  if (!o || typeof o !== 'object' || !WAIT_KINDS.includes(o.kind) || typeof o.ask !== 'string' || !o.ask.trim()) return null;
  return { kind: o.kind, ask: o.ask.trim(), ...(typeof o.clearBy === 'string' && o.clearBy.trim() ? { clearBy: o.clearBy.trim() } : {}), setAt: Number(o.setAt) || 0 };
}

const describe = (w) => `${w.kind}: ${w.ask}${w.clearBy ? ` (clear by: ${w.clearBy})` : ''}`;

export async function set(args, opts, env) {
  const kind = opts.kind;
  if (!WAIT_KINDS.includes(kind)) return { code: EXIT.REFUSED, error: `--kind must be one of ${WAIT_KINDS.join('|')}` };
  const ask = typeof opts.ask === 'string' ? opts.ask.replace(/\s+/g, ' ').trim() : '';
  if (!ask) return { code: EXIT.REFUSED, error: '--ask "<what you wait for>" is required' };
  if (ask.length > ASK_MAX) return { code: EXIT.REFUSED, error: `--ask is longer than ${ASK_MAX} characters` };
  const clearBy = typeof opts['clear-by'] === 'string' ? opts['clear-by'].replace(/\s+/g, ' ').trim() : '';
  const t = target(args, env);
  if (t.fail) return t.fail;
  const file = fileOf(env, t.id);
  const wait = { kind, ask, ...(clearBy ? { clearBy } : {}), setAt: Math.floor(Date.now() / 1000) };
  try {
    mkdirSync(paths(env).stateDir, { recursive: true });
    const tmp = `${file}.${process.pid}.tmp`;
    writeFileSync(tmp, `${JSON.stringify({ sessionId: t.id, ...wait, setBy: env.CLAUDE_CODE_SESSION_ID })}\n`);
    renameSync(tmp, file);
  } catch (e) {
    return { code: EXIT.REFUSED, error: `cannot write ${file}: ${e.message}` };
  }
  return { code: EXIT.OK, id: t.id, wait, text: `waiting set for ${t.id.slice(0, 8)}: ${describe(wait)}` };
}

export async function clear(args, _opts, env) {
  const t = target(args, env);
  if (t.fail) return t.fail;
  const file = fileOf(env, t.id);
  const had = existsSync(file);
  try { rmSync(file, { force: true }); } catch (e) { return { code: EXIT.REFUSED, error: `cannot remove ${file}: ${e.message}` }; }
  return { code: EXIT.OK, id: t.id, cleared: had, text: had ? `wait cleared for ${t.id.slice(0, 8)}` : `nothing declared for ${t.id.slice(0, 8)}` };
}

export async function show(args, _opts, env) {
  const t = target(args, env);
  if (t.fail) return t.fail;
  const wait = readWait(env, t.id);
  return { code: EXIT.OK, id: t.id, wait, text: wait ? describe(wait) : `nothing declared for ${t.id.slice(0, 8)}` };
}
