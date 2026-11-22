// «Свои» сессии: вызывающая (CLAUDE_CODE_SESSION_ID) и все её потомки
// по записям ~/.ccfzf/children (headId — родитель). Записи правят руками,
// поэтому обход помнит, где уже был, и на петле останавливается.
import { readChildren } from './sources.mjs';

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

export function ownSet(callerId, childrenDir, children) {
  if (!callerId) return new Set();
  return new Set([callerId, ...descendants(callerId, childrenDir, children)]);
}
