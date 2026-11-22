// claude-wt tree: сессии, окна, head/дети, снимки; «свои» помечены.
import { EXIT } from '../out.mjs';
import { paths, readState, readChildren, readHeads } from '../sources.mjs';
import { ownSet } from '../own.mjs';

// Общая сборка картины: её же используют команды действия.
export function picture(env) {
  const p = paths(env);
  const caller = env.CLAUDE_CODE_SESSION_ID || null;
  const state = readState({ bin: p.ccfzfBin });
  const children = readChildren(p.childrenDir);
  const own = ownSet(caller, p.childrenDir, children);
  const heads = readHeads(p.headsDir);
  const parentOf = new Map(children.filter((c) => c.headId && c.headId !== c.sessionId).map((c) => [c.sessionId, c.headId]));
  for (const c of children) if (parentOf.has(c.sessionId)) heads.add(parentOf.get(c.sessionId));

  const sessions = (state.sessions ?? []).map((s) => ({
    id: s.id,
    title: s.title ?? null,
    live: Boolean(s.live),
    cwd: s.cwd ?? null,
    window: s.window ? { host: s.window.host ?? null, title: s.window.title ?? null } : null,
    own: own.has(s.id),
    head: heads.has(s.id),
    parent: parentOf.get(s.id) ?? s.headId ?? null,
  }));
  const snapshots = (state.snapshots ?? []).map((x) => {
    const ids = (x.sessions ?? []).map((s) => s.id).filter(Boolean);
    return { id: x.id, created: x.created ?? null, host: x.host ?? null, sessions: ids, own: ids.length > 0 && ids.every((id) => own.has(id)) };
  });
  return { p, caller, state, children, own, sessions, snapshots };
}

// Для человека — только живые, свои и с окном: закрытых в --state сотни.
function human({ caller, sessions: all, snapshots }) {
  const sessions = all.filter((s) => s.live || s.own || s.window);
  const byParent = new Map();
  const ids = new Set(sessions.map((s) => s.id));
  for (const s of sessions) {
    const k = s.parent && ids.has(s.parent) ? s.parent : null;
    if (!byParent.has(k)) byParent.set(k, []);
    byParent.get(k).push(s);
  }
  const lines = [`caller: ${caller ?? '(none: not inside Claude Code)'}`];
  const walk = (parent, depth, seen) => {
    for (const s of byParent.get(parent) ?? []) {
      if (seen.has(s.id)) continue;
      seen.add(s.id);
      const flags = [s.own ? 'own' : null, s.head ? 'head' : null, s.live ? 'live' : null].filter(Boolean).join(',');
      const win = s.window ? `window@${s.window.host}` : 'no window';
      lines.push(`${'  '.repeat(depth)}${s.title ?? '?'}  ${s.id.slice(0, 8)}  ${win}${flags ? `  [${flags}]` : ''}`);
      walk(s.id, depth + 1, seen);
    }
  };
  walk(null, 0, new Set());
  if (all.length > sessions.length) lines.push(`(${all.length - sessions.length} closed sessions without a window not shown; see --json)`);
  lines.push(`snapshots: ${snapshots.length}${snapshots.length ? ` (own: ${snapshots.filter((x) => x.own).length})` : ''}`);
  return lines.join('\n');
}

export default async function tree(_args, _opts, env) {
  const { caller, sessions, snapshots } = picture(env);
  return { code: EXIT.OK, caller, sessions, snapshots, text: human({ caller, sessions, snapshots }) };
}
