// Вымышленный мир для тестов: head с двумя детьми и внуком, чужая сессия,
// два трекера — живой с http и «мак» без него.
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const loadState = () => JSON.parse(readFileSync(join(HERE, 'fixtures', 'state.json'), 'utf8'));

export const HEAD = 'aaaaaaaa-0000-4000-8000-000000000001';
export const CHILD1 = 'aaaaaaaa-0000-4000-8000-000000000002';
export const CHILD2 = 'aaaaaaaa-0000-4000-8000-000000000003';
export const GRAND = 'aaaaaaaa-0000-4000-8000-000000000004';
export const OTHER = 'bbbbbbbb-0000-4000-8000-000000000001';
export const CLOSED = 'bbbbbbbb-0000-4000-8000-000000000002';

export const CHILDREN = [
  { sessionId: CHILD1, headId: HEAD, createdAt: 10 },
  { sessionId: CHILD2, headId: HEAD, createdAt: 20 },
  { sessionId: GRAND, headId: CHILD1, createdAt: 30 },
];

export const HEADS = [{ sessionId: HEAD, name: 'demo-head', createdAt: 1 }];

// Живой трекер box-a (с http) и «мак» без http, оба свежие на момент t.
export function trackers(t, { port = 9722, httpHost = '127.0.0.1' } = {}) {
  return {
    'box-a': { host: 'box-a', generated: t, http: { port, host: httpHost }, windows: {} },
    'box-m': { host: 'box-m', generated: t, openSession: false, windows: {} },
  };
}
