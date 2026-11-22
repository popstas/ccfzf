// claude-wt snapshot list / restore: снимки раскладки трекеров, у которых есть
// http-менеджер; восстановить можно только свои сессии. Менеджер отвечает
// сразу, а окна поднимает хвостом до 30 с — исход CLI не знает (pending).
import { EXIT } from '../out.mjs';
import { picture } from './tree.mjs';
import { context, manager } from '../act.mjs';
import { readAgents, readTrackers } from '../sources.mjs';
import { resolveSession, resolveError } from '../resolve.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';

function withHttp(snapshots, trackers) {
  const hosts = new Set(trackers.filter((t) => t.http).map((t) => t.host));
  return snapshots.filter((x) => hosts.has(x.host)).sort((a, b) => (b.created ?? 0) - (a.created ?? 0));
}

function human(list) {
  if (!list.length) return 'no snapshots';
  return list.map((x) => `${x.id}  ${x.host}  ${x.sessions.length} sessions${x.own ? '  [own]' : ''}`).join('\n');
}

export async function list(_args, _opts, env) {
  const pic = picture(env);
  const snapshots = withHttp(pic.snapshots, readTrackers(pic.p.windowsDir));
  return { code: EXIT.OK, snapshots, text: human(snapshots) };
}

export async function restore(args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const { pic } = ctx;
  const arg = args[0];
  if (!arg) return { code: EXIT.REFUSED, error: 'missing <id|last>' };
  const trackers = ctx.trackers();
  const snaps = withHttp(pic.snapshots, trackers);
  const titleOf = (id) => pic.sessions.find((s) => s.id === id)?.title ?? '?';

  // --sessions: каждое имя → id; своё и (ниже) входит в снимок.
  let wanted = null;
  if (opts.sessions !== undefined) {
    const names = String(opts.sessions).split(',').map((s) => s.trim()).filter(Boolean);
    if (!names.length) return { code: EXIT.REFUSED, error: '--sessions is empty' };
    const agents = () => readAgents({ bin: pic.p.claudeBin });
    wanted = [];
    for (const n of names) {
      const r = resolveSession(n, { state: pic.state, agents });
      if (r.error) return { code: r.error === 'not found' ? EXIT.NOT_FOUND : EXIT.REFUSED, error: resolveError(n, r) };
      if (!pic.own.has(r.id)) return { code: EXIT.REFUSED, error: `not your session: ${r.id} (${titleOf(r.id)})` };
      if (!wanted.includes(r.id)) wanted.push(r.id);
    }
  }

  let snap;
  if (arg === 'last') {
    snap = snaps.find((x) => x.sessions.length && (wanted ? wanted.every((id) => x.sessions.includes(id)) : x.own));
    if (!snap) return { code: EXIT.NOT_FOUND, error: wanted ? 'no snapshot holds all of --sessions' : 'no snapshot of your own sessions' };
  } else {
    snap = snaps.find((x) => x.id === arg);
    if (!snap) return { code: EXIT.NOT_FOUND, error: `snapshot not found: ${arg} (only trackers with an http manager)` };
  }

  let sessionIds;
  if (wanted) {
    const missing = wanted.filter((id) => !snap.sessions.includes(id));
    if (missing.length) return { id: snap.id, code: EXIT.REFUSED, error: `not in snapshot ${snap.id}: ${missing.join(', ')}` };
    sessionIds = wanted;
  } else {
    const foreign = snap.sessions.filter((id) => !pic.own.has(id));
    if (foreign.length) {
      const list = foreign.map((id) => `${id} (${titleOf(id)})`).join(', ');
      return { id: snap.id, foreign, code: EXIT.REFUSED, error: `snapshot ${snap.id} has sessions that are not yours: ${list}; pass --sessions with your own` };
    }
    sessionIds = snap.sessions;
  }

  // Пустой sessionIds менеджер читает как «все сессии снимка» — чужие тоже.
  if (!sessionIds.length) return { id: snap.id, code: EXIT.REFUSED, error: `snapshot ${snap.id} lists no sessions by id; nothing to restore` };

  const mg = manager(snap.host, trackers, opts);
  if (mg.fail) return { id: snap.id, ...mg.fail };
  const res = answer(await post(mg.m.url, '/claude-wt/snapshot-restore', { id: snap.id, sessionIds }, { timeoutMs: timeoutMs(env) }));
  const out = { id: snap.id, host: mg.m.host, url: mg.m.url, sessionIds };
  if (res.code !== EXIT.OK) return { ...out, code: res.code, error: res.error };
  return { ...out, code: EXIT.OK, pending: true, text: `accepted, outcome unknown — see tracker log (${sessionIds.length} sessions of ${snap.id})` };
}
