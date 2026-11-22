// «Свои» сессии: вызывающая (CLAUDE_CODE_SESSION_ID) и все её потомки
// по записям ~/.ccfzf/children. Обход — в lineage.mjs.
import { descendants } from './lineage.mjs';

export function ownSet(callerId, childrenDir, children) {
  if (!callerId) return new Set();
  return new Set([callerId, ...descendants(callerId, childrenDir, children)]);
}
