// claude-wt window icons: какие имена можно ставить командами window icon и
// window badge — `.ico` из папки иконок менеджера. Спрашивается машина первого
// окна своей сессии; `--machine`/`--url` — другая, и тогда вызывающая сессия не
// нужна. Списки разных машин не сливаются: имя ставится там, где окно.
import { EXIT } from '../out.mjs';
import { context, manager } from '../act.mjs';
import { picture } from './tree.mjs';
import { readTrackers } from '../sources.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';
import { windowHosts } from '../hosts.mjs';

export default async function icons(args, opts, env) {
  let host = null;
  let trackers;
  if (opts.url !== undefined || opts.machine !== undefined) {
    host = opts.machine ?? null;
    trackers = readTrackers(picture(env).p.windowsDir);
  } else {
    const ctx = context(env);
    if (ctx.fail) return ctx.fail;
    host = windowHosts(ctx.pic.state, env.CLAUDE_CODE_SESSION_ID)[0];
    if (!host) return { code: EXIT.NOT_FOUND, error: 'your session has no window; pass --machine HOST' };
    trackers = ctx.trackers();
  }
  const mg = manager(host, trackers, opts);
  if (mg.fail) return mg.fail;
  const r = await post(mg.m.url, '/claude-wt/window-icons', {}, { timeoutMs: timeoutMs(env) });
  const res = answer(r);
  const where = mg.m.host ?? host;
  if (res.code !== EXIT.OK) {
    const error = r.status === 404 && !res.body?.reason ? 'manager has no /claude-wt/window-icons (old manager?)' : res.error;
    return { code: res.code, host: where, error };
  }
  const names = Array.isArray(res.body.names) ? res.body.names : [];
  const dir = res.body.dir ?? null;
  return {
    code: EXIT.OK, host: where, dir, names,
    text: names.length ? names.join('\n') : `no .ico files in ${dir} on ${where}`,
  };
}
