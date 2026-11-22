// Кто «свой»: вызывающая сессия и её потомки по ~/.ccfzf/children.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { ownSet } from '../../cli/lib/own.mjs';
import { descendants } from '../../cli/lib/lineage.mjs';
import { readTrackers } from '../../cli/lib/sources.mjs';
import { world } from './helpers.mjs';
import { CHILDREN, HEAD, CHILD1, CHILD2, GRAND, OTHER } from './fixtures.mjs';

test('потомки вглубь и петля не зацикливает', () => {
  const w = world({
    children: [
      ...CHILDREN,
      // Петля из записей, поправленных руками: L1 → L2 → L1.
      { sessionId: 'loop-1', headId: 'loop-2' },
      { sessionId: 'loop-2', headId: 'loop-1' },
      { sessionId: 'loop-3', headId: 'loop-1' },
    ],
  });
  try {
    assert.deepEqual([...descendants(HEAD, w.childrenDir)].sort(), [CHILD1, CHILD2, GRAND].sort());
    assert.deepEqual([...descendants(CHILD1, w.childrenDir)], [GRAND]);
    assert.deepEqual([...descendants(GRAND, w.childrenDir)], []);
    assert.deepEqual([...descendants('loop-1', w.childrenDir)].sort(), ['loop-2', 'loop-3']);
    const own = ownSet(CHILD1, w.childrenDir);
    assert.deepEqual([...own].sort(), [CHILD1, GRAND].sort(), 'исполнитель — сам и свои дети, не head');
    assert.equal(own.has(OTHER), false);
  } finally {
    w.cleanup();
  }
});

test('нет каталога children — свой только сам', () => {
  assert.deepEqual([...ownSet(HEAD, '/nonexistent/children')], [HEAD]);
  assert.deepEqual([...ownSet(undefined, '/nonexistent/children')], []);
});

test('файл мака без http не роняет readTrackers', () => {
  const w = world({
    trackers: {
      'box-a': { host: 'box-a', generated: 1000, http: { port: 9722, host: 'box-a.lan' } },
      mac: { host: 'mac', generated: 100, openSession: false },
      broken: '{not json',
    },
  });
  try {
    writeFileSync(join(w.windowsDir, 'notes.txt'), 'не трекер');
    const t = readTrackers(w.windowsDir, 1000 + 899);
    assert.deepEqual(t.map((x) => x.host).sort(), ['box-a', 'mac'], 'битый файл пропущен');
    const a = t.find((x) => x.host === 'box-a');
    assert.deepEqual(a.http, { host: 'box-a.lan', port: 9722 });
    assert.equal(a.fresh, true);
    assert.equal(a.file, 'box-a.json');
    const m = t.find((x) => x.host === 'mac');
    assert.equal(m.http, null);
    assert.equal(m.fresh, false);
    assert.equal(readTrackers(w.windowsDir, 1000 + 900).find((x) => x.host === 'box-a').fresh, false,
      '15 минут и старше — протух');
    assert.deepEqual(readTrackers('/nonexistent/windows', 0), []);
  } finally {
    w.cleanup();
  }
});
