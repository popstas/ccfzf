// claude-wt window place <session> --zone <monitor>:<position>: перенести
// существующее окно своей сессии в зону FancyZones его машины.
// Окна не открывает (как focus): окна нет — код 2 до запроса. Зону проверяет
// менеджер — по раскладке FancyZones подключённого монитора; здесь только форма.
import { EXIT } from '../out.mjs';
import { context, ownTarget, manager, offMachine } from '../act.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';

// "3:1" → {monitor: 3, position: 1}; номера — целые от 1, как у FancyZones.
export function parseZone(raw) {
  if (raw === undefined || raw === true) return { error: 'missing --zone <monitor>:<position>' };
  const m = /^\s*(\d+)\s*:\s*(\d+)\s*$/.exec(String(raw));
  const monitor = m ? Number(m[1]) : 0;
  const position = m ? Number(m[2]) : 0;
  if (!m || monitor < 1 || position < 1) return { error: `bad --zone ${raw}: need <monitor>:<position>, integers from 1 (e.g. 3:1)` };
  return { zone: { monitor, position } };
}

export default async function windowPlace(args, opts, env) {
  // Кривая зона — отказ раньше всего: ни картины, ни запроса.
  const z = parseZone(opts.zone);
  if (z.error) return { code: EXIT.REFUSED, error: z.error };
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const t = ownTarget(args[0], ctx.pic);
  if (t.fail) return t.fail;
  const s = t.session;
  const zone = `${z.zone.monitor}:${z.zone.position}`;
  const base = { id: s.id, title: s.title, zone };
  if (!s.window) return { ...base, code: EXIT.NOT_FOUND, error: 'no window' };
  const trackers = ctx.trackers();
  const off = offMachine(s.window.host, trackers, opts);
  if (off) return { ...base, code: EXIT.REFUSED, error: off };
  const mg = manager(s.window.host, trackers, opts);
  if (mg.fail) return { ...base, ...mg.fail };
  const { url, host } = mg.m;
  const res = answer(await post(url, '/claude-wt/place', { mode: 'zone', id: s.id, zone: z.zone }, { timeoutMs: timeoutMs(env) }));
  const out = { ...base, host, url };
  if (res.code === EXIT.REFUSED && res.body?.reason === 'no window') return { ...out, code: EXIT.NOT_FOUND, error: 'no window' };
  // Менеджер до mode zone разбирает тело как незнакомую раскладку.
  if (res.code === EXIT.REFUSED && res.body?.reason === 'bad payload') {
    return { ...out, code: EXIT.REFUSED, error: 'manager does not know mode zone (old manager?): bad payload' };
  }
  if (res.code !== EXIT.OK) return { ...out, code: res.code, error: res.error };
  const placed = Number.isInteger(res.body.placed) ? res.body.placed : null;
  const warnings = placed === null ? ['manager did not report whether it moved the window'] : undefined;
  const where = placed === 0 ? 'already in' : 'moved to';
  return { ...out, code: EXIT.OK, placed, warnings, text: `${s.title ?? s.id} ${where} zone ${zone} on ${host}` };
}
