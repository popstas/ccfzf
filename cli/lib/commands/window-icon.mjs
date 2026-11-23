// claude-wt window icon|badge <session> <name>|--clear: явная иконка окна
// (WM_SETICON) и значок на кнопке панели задач своей сессии — по имени файла из
// папки иконок машины окна (`claudeWt.windowIcons.dir` у её менеджера, только
// .ico). Явное перебивает автоматику менеджера: иконку проекта, правила badges
// и значок head (решение Стаса 23.11, вариант A); `--clear` возвращает её.
//
// Менеджер сохраняет заданное всегда и отвечает, встало ли (`applied`,
// `reason`): окна сейчас нет, иконки выключены — встанет само, код 0. Отказ
// (код 1) — только неизвестное имя или нет папки. Цели — машины всех окон
// сессии, как у session unread/seen; окна нет — код 2, если машина не названа
// (`--machine`/`--url`: тогда заданное ляжет там и встанет с окном). Повтор
// безопасен.
import { EXIT } from '../out.mjs';
import { context, ownTarget, manager } from '../act.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';
import { windowHosts, worst } from '../hosts.mjs';

const ROUTE = { icon: '/claude-wt/window-icon', badge: '/claude-wt/window-badge' };

async function setOne(kind, id, name, host, trackers, opts, env) {
  const mg = manager(host, trackers, opts);
  if (mg.fail) return { host, ...mg.fail };
  const { url } = mg.m;
  const r = await post(url, ROUTE[kind], { id, [kind]: name }, { timeoutMs: timeoutMs(env) });
  const res = answer(r);
  const out = { host: mg.m.host ?? host, url };
  if (res.code !== EXIT.OK) {
    const error = r.status === 404 && !res.body?.reason ? `manager has no ${ROUTE[kind]} (old manager?)` : res.error;
    return { ...out, code: res.code, error };
  }
  const b = res.body;
  return {
    ...out,
    code: EXIT.OK,
    [kind]: typeof b[kind] === 'string' ? b[kind] : null,
    applied: b.applied === true,
    ...(b.applied === true ? {} : { reason: b.reason || 'not applied' }),
  };
}

async function set(kind, args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const t = ownTarget(args[0], ctx.pic);
  if (t.fail) return t.fail;
  const name = args[1];
  if (Boolean(name) === Boolean(opts.clear) || args.length > 2) {
    return { code: EXIT.REFUSED, error: 'need <name> or --clear' };
  }
  const s = t.session;
  const base = { id: s.id, title: s.title };
  const trackers = ctx.trackers();
  const hosts = opts.url !== undefined || opts.machine !== undefined
    ? [opts.machine ?? s.window?.host ?? null]
    : windowHosts(ctx.pic.state, s.id);
  if (!hosts.length) return { ...base, code: EXIT.NOT_FOUND, error: 'no window' };

  // Каждая машина — своя попытка, независимо от исхода соседних.
  const results = [];
  for (const host of hosts) results.push(await setOne(kind, s.id, name ?? null, host, trackers, opts, env));

  const code = worst(results.map((r) => r.code));
  const out = { ...base, code, results };
  const failed = results.filter((r) => r.code !== EXIT.OK);
  if (failed.length) {
    const why = failed.map((r) => `${r.host ?? '?'}: ${r.error}`).join('; ');
    return { ...out, error: results.length > 1 ? why : failed[0].error };
  }
  const who = s.title ?? s.id;
  const what = name ? `${kind} ${name}` : kind;
  const pending = results.filter((r) => !r.applied);
  if (!pending.length) {
    const where = results.map((r) => r.host).join(', ');
    return { ...out, text: name ? `set ${what} for ${who} on ${where}` : `cleared ${what} for ${who} on ${where}` };
  }
  const why = pending.map((r) => `${r.host}: ${r.reason}`).join('; ');
  return { ...out, text: `saved ${what} for ${who}, not applied on ${why}` };
}

export const icon = (args, opts, env) => set('icon', args, opts, env);
export const badge = (args, opts, env) => set('badge', args, opts, env);
