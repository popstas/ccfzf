// claude-wt window focus <session>: поднять существующее окно своей сессии.
// Окна нет — отказ до запроса: старый менеджер без raiseOnly открыл бы новое.
import { EXIT } from '../out.mjs';
import { context, ownTarget, manager } from '../act.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';

// --machine/--url, ведущие не на машину окна: там этого окна нет, и менеджер
// без raiseOnly открыл бы новое — а focus окон не открывает (решение Стаса).
// Адрес машины окна — её имя или http.host из её трекера; иначе не проверить — отказ.
function offMachine(host, trackers, opts) {
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

export default async function windowFocus(args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const t = ownTarget(args[0], ctx.pic);
  if (t.fail) return t.fail;
  const s = t.session;
  const base = { id: s.id, title: s.title };
  if (!s.window) return { ...base, code: EXIT.NOT_FOUND, error: 'no window' };
  const trackers = ctx.trackers();
  const off = offMachine(s.window.host, trackers, opts);
  if (off) return { ...base, code: EXIT.REFUSED, error: off };
  const mg = manager(s.window.host, trackers, opts);
  if (mg.fail) return { ...base, ...mg.fail };
  const { url, host } = mg.m;
  const res = answer(await post(url, '/claude-wt/focus', { id: s.id, raiseOnly: true }, { timeoutMs: timeoutMs(env) }));
  const out = { ...base, host, url };
  if (res.code !== EXIT.OK) return { ...out, ...res, body: undefined };
  const b = res.body;
  // Менеджер не поднял, а открыл окно заново: это не то, о чём просили.
  if (b.action && b.action !== 'focus') return { ...out, code: EXIT.REFUSED, error: `manager did ${b.action} instead of focus`, action: b.action };
  if (b.foreground === false) return { ...out, code: EXIT.REFUSED, error: 'window did not come to front', foreground: false };
  if (b.foreground === true) return { ...out, code: EXIT.OK, foreground: true, text: `focused ${s.title ?? s.id} on ${host}` };
  return {
    ...out,
    code: EXIT.OK,
    foreground: null,
    warnings: ['manager did not report foreground (old manager?): the window may not be in front'],
    text: `focus sent to ${s.title ?? s.id} on ${host}`,
  };
}
