// claude-wt window focus <session>: поднять существующее окно своей сессии.
// Окна нет — отказ до запроса: старый менеджер без raiseOnly открыл бы новое.
import { EXIT } from '../out.mjs';
import { context, ownTarget, manager } from '../act.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';

export default async function windowFocus(args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const t = ownTarget(args[0], ctx.pic);
  if (t.fail) return t.fail;
  const s = t.session;
  const base = { id: s.id, title: s.title };
  if (!s.window) return { ...base, code: EXIT.NOT_FOUND, error: 'no window' };
  const mg = manager(s.window.host, ctx.trackers(), opts);
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
