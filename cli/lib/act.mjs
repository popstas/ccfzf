// Общий вход команд действия: есть ли вызывающая сессия, кто цель, своя ли она.
import { EXIT } from './out.mjs';
import { readAgents, readTrackers } from './sources.mjs';
import { resolveSession, resolveError } from './resolve.mjs';
import { picture } from './commands/tree.mjs';
import { managerFor } from './manager.mjs';

export const NO_CALLER = 'not inside a Claude Code session (CLAUDE_CODE_SESSION_ID is unset); only tree and snapshot list work';

// Картина + вызывающий; без вызывающего — отказ до чтения остального.
export function context(env) {
  if (!env.CLAUDE_CODE_SESSION_ID) return { fail: { code: EXIT.REFUSED, error: NO_CALLER } };
  const pic = picture(env);
  return { pic, trackers: () => readTrackers(pic.p.windowsDir) };
}

// <session> → своя сессия из картины или отказ.
export function ownTarget(arg, pic) {
  if (!arg) return { fail: { code: EXIT.REFUSED, error: 'missing <session>' } };
  const r = resolveSession(arg, { state: pic.state, agents: () => readAgents({ bin: pic.p.claudeBin }) });
  if (r.error === 'not found') return { fail: { code: EXIT.NOT_FOUND, error: resolveError(arg, r) } };
  if (r.error) return { fail: { code: EXIT.REFUSED, error: resolveError(arg, r), candidates: r.candidates } };
  const s = pic.sessions.find((x) => x.id === r.id) ?? { id: r.id, title: null, window: null, own: pic.own.has(r.id) };
  if (!s.own) return { fail: { code: EXIT.REFUSED, error: `not your session: ${s.id} (${s.title ?? '?'}); only this session and its descendants`, id: s.id } };
  return { session: s };
}

// Менеджер для хоста; отказ — в форме результата.
export function manager(host, trackers, opts) {
  const m = managerFor({ host, trackers, url: opts.url, machine: opts.machine });
  return m.error ? { fail: { code: m.code, error: m.error } } : { m };
}

// --machine/--url, ведущие не на машину окна: там этого окна нет. У focus
// менеджер без raiseOnly открыл бы новое (а focus окон не открывает, решение
// Стаса), у place — ответил бы про чужое окно или ни про какое.
// Адрес машины окна — её имя или http.host из её трекера; иначе не проверить — отказ.
export function offMachine(host, trackers, opts) {
  const lc = (x) => String(x ?? '').toLowerCase();
  if (opts.machine !== undefined && lc(opts.machine) !== lc(host)) {
    return `--machine ${opts.machine} is not the window's machine (${host})`;
  }
  if (opts.url !== undefined) {
    let name = null;
    try { name = lc(new URL(opts.url).hostname); } catch { return null; } // кривой --url отвергнет managerFor
    const known = new Set([lc(host)]);
    for (const t of trackers) if (lc(t.host) === lc(host) && t.http?.host) known.add(lc(t.http.host));
    if (!known.has(name)) return `--url ${opts.url} does not point to the window's machine (${host}); known addresses: ${[...known].join(', ')}`;
  }
  return null;
}
