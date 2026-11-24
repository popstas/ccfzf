// claude-wt window taskbar <session> hide|show|auto: кнопка окна своей сессии на
// панели задач. `hide` прячет её, `show` держит видимой вопреки автоматике
// пикера (гашение приглушённых), `auto` возвращает решение менеджеру. Менеджер
// сам снимает `hide` на новом ходу сессии и при закрытии окна; сигнал (вопрос,
// непросмотренный итог, мигание кеша) держит кнопку при любом режиме.
//
// Менеджер сохраняет режим всегда и отвечает, встало ли (`applied`, `reason`) —
// как у window icon. Тело обязано нести ключ `taskbar`: без него менеджер
// отказывает, поэтому `auto` шлёт явный null. Цели — машины всех окон сессии;
// окна нет — код 2. Повтор безопасен.
import { EXIT } from '../out.mjs';
import { context, ownTarget, manager } from '../act.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';
import { windowHosts, worst } from '../hosts.mjs';

const ROUTE = '/claude-wt/window-taskbar';
const MODES = { hide: 'hidden', show: 'shown', auto: 'auto' };

async function setOne(id, mode, host, trackers, opts, env) {
  const mg = manager(host, trackers, opts);
  if (mg.fail) return { host, ...mg.fail };
  const { url } = mg.m;
  const r = await post(url, ROUTE, { id, taskbar: mode === 'auto' ? null : mode }, { timeoutMs: timeoutMs(env) });
  const res = answer(r);
  const out = { host: mg.m.host ?? host, url };
  if (res.code !== EXIT.OK) {
    const error = r.status === 404 && !res.body?.reason ? `manager has no ${ROUTE} (old manager?)` : res.error;
    return { ...out, code: res.code, error };
  }
  const b = res.body;
  return {
    ...out,
    code: EXIT.OK,
    taskbar: typeof b.taskbar === 'string' ? b.taskbar : null,
    applied: b.applied === true,
    ...(b.applied === true ? {} : { reason: b.reason || 'not applied' }),
  };
}

export async function taskbar(args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const t = ownTarget(args[0], ctx.pic);
  if (t.fail) return t.fail;
  const mode = args[1];
  if (!Object.hasOwn(MODES, mode) || args.length > 2) {
    return { code: EXIT.REFUSED, error: 'need hide, show or auto' };
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
  for (const host of hosts) results.push(await setOne(s.id, mode, host, trackers, opts, env));

  const code = worst(results.map((r) => r.code));
  const out = { ...base, code, results };
  const failed = results.filter((r) => r.code !== EXIT.OK);
  if (failed.length) {
    const why = failed.map((r) => `${r.host ?? '?'}: ${r.error}`).join('; ');
    return { ...out, error: results.length > 1 ? why : failed[0].error };
  }
  const who = s.title ?? s.id;
  const pending = results.filter((r) => !r.applied);
  if (!pending.length) {
    return { ...out, text: `taskbar ${MODES[mode]} for ${who} on ${results.map((r) => r.host).join(', ')}` };
  }
  const why = pending.map((r) => `${r.host}: ${r.reason}`).join('; ');
  return { ...out, text: `saved taskbar ${mode} for ${who}, not applied on ${why}` };
}
