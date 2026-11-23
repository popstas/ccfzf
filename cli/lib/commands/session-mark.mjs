// claude-wt session unread|seen <session>: отметки «непросмотрено» и
// «просмотрено» у оконных трекеров своей сессии. Окно не поднимается и фокус
// не уходит — только отметки (решение head 2026-11-22).
//
// Отметок «просмотрено» две, и пикер складывает их по максимуму: своя
// (seen.json) и `focusedAt` трекера. `unread` ставит у трекера `unreadAt` —
// пикер считает сессию непросмотренной, пока он новее обеих; `seen` ставит
// `focusedAt` «сейчас» и снимает `unreadAt`. Своей отметки пикера CLI не
// трогает: её не видно отсюда, а `unreadAt` перебивает её и так.
//
// Цели — трекеры **всех** окон сессии, как у «Mark unread» пикера: отметь у
// одного, и второй вернёт «просмотрено» своей карточкой. Окна нет — код 2:
// отметке негде лечь (у трекера она живёт в записи окна). Обе просьбы
// идемпотентны, и код 3 повторять можно.
import { EXIT } from '../out.mjs';
import { context, ownTarget, manager } from '../act.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';
import { windowHosts, worst } from '../hosts.mjs';

const ROUTE = { unread: '/claude-wt/session-unread', seen: '/claude-wt/session-seen' };

// Поле ответа, по которому видно менеджера, ставящего отметку в файл трекера.
// Старый менеджер отвечает `{ok:true}` без него: на unread — ни на что не
// глядя (и на отказ тоже), на seen — гасит только кнопку панели задач.
const MARK_FIELD = { unread: 'unreadAt', seen: 'focusedAt' };
const OLD = {
  unread: 'manager did not report unreadAt (old manager?): the picker may still show the session as seen',
  seen: 'manager did not report focusedAt (old manager?): only the taskbar button was put out',
};

async function markOne(kind, id, host, trackers, opts, env) {
  const mg = manager(host, trackers, opts);
  if (mg.fail) return { host, ...mg.fail };
  const { url } = mg.m;
  const res = answer(await post(url, ROUTE[kind], { id }, { timeoutMs: timeoutMs(env) }));
  const out = { host: mg.m.host ?? host, url };
  if (res.code !== EXIT.OK) {
    // «Не знаю такой сессии» — трекер не держит её слота: то же «не найдено».
    const code = /^unknown session/.test(res.error ?? '') ? EXIT.NOT_FOUND : res.code;
    return { ...out, code, error: res.error };
  }
  const b = res.body;
  const field = MARK_FIELD[kind];
  return {
    ...out,
    code: EXIT.OK,
    ...(Array.isArray(b.ids) ? { ids: b.ids } : {}),
    ...(Number.isFinite(b.focusedAt) ? { focusedAt: b.focusedAt } : {}),
    ...(Number.isFinite(b.unreadAt) ? { unreadAt: b.unreadAt } : {}),
    // Демон в другом процессе: отметка ляжет на его ближайшем тике (раз в секунду).
    ...(b.requested === true ? { pending: true } : {}),
    ...(Number.isFinite(b[field]) ? {} : { warning: OLD[kind] }),
  };
}

async function mark(kind, args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const t = ownTarget(args[0], ctx.pic);
  if (t.fail) return t.fail;
  const s = t.session;
  const base = { id: s.id, title: s.title };
  const trackers = ctx.trackers();
  // --url/--machine — одна названная машина вместо машин окон.
  const hosts = opts.url !== undefined || opts.machine !== undefined
    ? [opts.machine ?? s.window?.host ?? null]
    : windowHosts(ctx.pic.state, s.id);
  if (!hosts.length) return { ...base, code: EXIT.NOT_FOUND, error: 'no window' };

  // Каждая машина — своя попытка, независимо от исхода соседних: ранний выход
  // оставил бы вторую машину неотмеченной, и её карточка вернула бы прежнее.
  const results = [];
  for (const host of hosts) results.push(await markOne(kind, s.id, host, trackers, opts, env));

  const code = worst(results.map((r) => r.code));
  const failed = results.filter((r) => r.code !== EXIT.OK);
  const warnings = results.filter((r) => r.warning).map((r) => `${r.host}: ${r.warning}`);
  const pending = results.some((r) => r.pending);
  const out = {
    ...base,
    code,
    results: results.map(({ warning, ...r }) => r),
    ...(pending ? { pending: true } : {}),
    ...(warnings.length ? { warnings } : {}),
  };
  if (failed.length) {
    const why = failed.map((r) => `${r.host ?? '?'}: ${r.error}`).join('; ');
    return { ...out, error: results.length > 1 ? why : failed[0].error };
  }
  const where = results.map((r) => r.host).join(', ');
  return { ...out, text: `marked ${s.title ?? s.id} ${kind} on ${where}${pending ? ' (applies on the next tracker tick)' : ''}` };
}

export const unread = (args, opts, env) => mark('unread', args, opts, env);
export const seen = (args, opts, env) => mark('seen', args, opts, env);
