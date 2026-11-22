// claude-wt window layout <head>: разложить окна своей группы head.
// Группа = head + его потомки с окном на той же машине, по порядку createdAt
// записей children. Правила группировки пикера здесь не повторяются: агенту
// нужна раскладка своей группы, а не совпадение с горячей клавишей до порядка.
import { EXIT } from '../out.mjs';
import { context, ownTarget, manager } from '../act.mjs';
import { descendants } from '../own.mjs';
import { post, answer, timeoutMs } from '../manager.mjs';

export default async function windowLayout(args, opts, env) {
  const ctx = context(env);
  if (ctx.fail) return ctx.fail;
  const { pic } = ctx;
  const t = ownTarget(args[0], pic);
  if (t.fail) return t.fail;
  const head = t.session;
  const base = { id: head.id, title: head.title };
  if (!head.window) return { ...base, code: EXIT.NOT_FOUND, error: 'no window: the head has no window to lay out around' };
  const host = head.window.host;
  const created = new Map(pic.children.map((c) => [c.sessionId, Number(c.createdAt) || 0]));
  const byId = new Map(pic.sessions.map((s) => [s.id, s]));
  const kids = [...descendants(head.id, pic.p.childrenDir, pic.children)]
    .filter((id) => byId.get(id)?.window?.host === host)
    .sort((a, b) => created.get(a) - created.get(b));
  const group = [head.id, ...kids];
  if (group.length < 2) return { ...base, group, code: EXIT.REFUSED, error: 'nothing to lay out' };
  const mg = manager(host, ctx.trackers(), opts);
  if (mg.fail) return { ...base, group, ...mg.fail };
  const body = { mode: 'group', groups: [group], selected: head.id };
  const res = answer(await post(mg.m.url, '/claude-wt/place', body, { timeoutMs: timeoutMs(env) }));
  const out = { ...base, group, host: mg.m.host, url: mg.m.url };
  if (res.code !== EXIT.OK) return { ...out, code: res.code, error: res.error };
  const placed = Number.isInteger(res.body.placed) ? res.body.placed : null;
  const warnings = placed === null ? ['manager did not report how many windows it placed (old manager?)'] : undefined;
  return { ...out, code: EXIT.OK, placed, warnings, text: `laid out ${placed ?? group.length} windows of ${head.title ?? head.id} on ${mg.m.host}` };
}
