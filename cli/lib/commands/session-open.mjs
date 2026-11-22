// claude-wt session open <session>: открыть окно своей сессии, когда окна нет
// (решение Стаса 2026-11-22: агенту можно без спроса). Окно есть — отказ без
// запроса: открывать второе окно нельзя, поднять — `window focus`.
// Машина — трекер с http, который берёт просьбы открыть сессию (`openSession`);
// --machine/--url перебивают, но не на машину, где openSession: false.
// Исход неизвестен (таймаут, обрыв после отправки) — код 3, повторять нельзя:
// повтор открыл бы второе окно.
import { EXIT } from '../out.mjs';
import { context, ownTarget } from '../act.mjs';
import { managerFor, post, answer } from '../manager.mjs';

// Открытие идёт дольше подъёма (resume, restore): свой срок, если не задан явно.
export const OPEN_TIMEOUT_MS = 20000;
const UNKNOWN = 'outcome unknown — do not retry; check with tree in 30 s';

const lc = (x) => String(x ?? '').toLowerCase();
const noOpen = (host) => `${host} does not open sessions (openSession: false in its tracker)`;

// Куда слать: {m} или {fail}.
function where(trackers, opts) {
  const pick = (args) => {
    const m = managerFor({ trackers, ...args });
    return m.error ? { fail: { code: m.code, error: m.error } } : { m };
  };
  if (opts.url !== undefined) {
    const r = pick({ url: opts.url, machine: opts.machine });
    if (r.fail) return r;
    const name = lc(new URL(r.m.url).hostname);
    const t = trackers.find((x) => lc(x.host) === name || lc(x.http?.host) === name);
    if (t && !t.openSession) return { fail: { code: EXIT.REFUSED, error: noOpen(t.host) } };
    return { m: { ...r.m, host: t?.host ?? r.m.host } };
  }
  if (opts.machine !== undefined) {
    const mine = trackers.filter((t) => lc(t.host) === lc(opts.machine));
    if (mine.length && !mine.some((t) => t.openSession)) return { fail: { code: EXIT.REFUSED, error: noOpen(opts.machine) } };
    return pick({ host: opts.machine });
  }
  const live = trackers.filter((t) => t.http && t.fresh);
  const cands = live.filter((t) => t.openSession).sort((a, b) => b.generated - a.generated);
  if (!cands.length) {
    if (live.length) return { fail: { code: EXIT.REFUSED, error: `no tracker opens sessions: ${live.map((t) => noOpen(t.host)).join('; ')}` } };
    return { fail: { code: EXIT.NOT_FOUND, error: 'no fresh tracker with an http manager (pass --machine or --url)' } };
  }
  return pick({ host: cands[0].host });
}

export default async function sessionOpen(args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const t = ownTarget(args[0], ctx.pic);
  if (t.fail) return t.fail;
  const s = t.session;
  const base = { id: s.id, title: s.title };
  if (s.window) return { ...base, code: EXIT.REFUSED, error: 'window exists, use window focus', window: s.window };
  const w = where(ctx.trackers(), opts);
  if (w.fail) return { ...base, ...w.fail };
  const { url, host } = w.m;
  // action обязателен: без него менеджер ничего не открывает и отвечает {ok:true}.
  // cwd — откуда взять профиль терминала, если сессию эта машина не помнит.
  const body = { id: s.id, action: 'terminal', ...(s.cwd && { cwd: s.cwd }) };
  const ms = Number(env.CLAUDE_WT_TIMEOUT_MS) > 0 ? Number(env.CLAUDE_WT_TIMEOUT_MS) : OPEN_TIMEOUT_MS;
  const res = answer(await post(url, '/claude-wt/session-open', body, { timeoutMs: ms }));
  const out = { ...base, host, url };
  if (res.code === EXIT.UNKNOWN) return { ...out, code: EXIT.UNKNOWN, error: UNKNOWN, detail: res.error };
  if (res.code !== EXIT.OK) return { ...out, code: res.code, error: res.error };
  const action = typeof res.body.action === 'string' ? res.body.action : null;
  const warnings = action ? undefined : ['manager did not say what it did (old manager?): check with tree'];
  const pending = action === 'pending';
  return {
    ...out,
    code: EXIT.OK,
    action,
    pending,
    warnings,
    text: pending ? `already opening ${s.title ?? s.id} on ${host}` : `${action ?? 'open'} ${s.title ?? s.id} on ${host}`,
  };
}
