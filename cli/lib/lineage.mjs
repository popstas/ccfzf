// Цепочка head → дети по записям ~/.ccfzf/children/<id>.json (headId — родитель).
// Записи правят руками, поэтому каждый обход помнит, где был, и на повторе встаёт.
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { readJson, readChildren } from './sources.mjs';

// Родитель, дед, … сессии. Стоп: нет записи, нет headId или повтор.
export function ancestors(sessionId, childrenDir) {
  const out = [];
  const seen = new Set([sessionId]);
  for (let id = sessionId; ;) {
    const parent = readJson(join(childrenDir, `${id}.json`))?.headId;
    if (!parent || seen.has(parent)) return out;
    seen.add(parent);
    out.push(parent);
    id = parent;
  }
}

// parent → [дети] по записям children.
export function kidsByParent(children) {
  const m = new Map();
  for (const c of children) {
    if (!c.headId || c.headId === c.sessionId) continue;
    if (!m.has(c.headId)) m.set(c.headId, []);
    m.get(c.headId).push(c);
  }
  return m;
}

// Все потомки вглубь, без самой сессии.
export function descendants(id, childrenDir, children = readChildren(childrenDir)) {
  const kids = kidsByParent(children);
  const out = new Set();
  const seen = new Set([id]);
  const queue = [id];
  while (queue.length) {
    for (const c of kids.get(queue.shift()) ?? []) {
      if (seen.has(c.sessionId)) continue;
      seen.add(c.sessionId);
      out.add(c.sessionId);
      queue.push(c.sessionId);
    }
  }
  return out;
}

// Где работает сессия: её метка head, иначе запись ребёнка, иначе живая запись реестра.
export function sessionCwd(id, { headsDir, childrenDir, sessionsDir }) {
  const fromMark = readJson(join(headsDir, `${id}.json`))?.cwd;
  if (fromMark) return fromMark;
  const fromChild = readJson(join(childrenDir, `${id}.json`))?.cwd;
  if (fromChild) return fromChild;
  let files = [];
  try { files = readdirSync(sessionsDir).filter((f) => f.endsWith('.json')); } catch {}
  for (const f of files) {
    const r = readJson(join(sessionsDir, f));
    if (r?.sessionId === id && r.cwd) return r.cwd;
  }
  return null;
}
