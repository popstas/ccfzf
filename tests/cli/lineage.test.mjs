// Цепочка head → родитель по ~/.ccfzf/children и где работает сессия.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ancestors, sessionCwd } from '../../cli/lib/lineage.mjs';

function dirs() {
  const root = mkdtempSync(join(tmpdir(), 'claude-wt-lineage-'));
  const d = { headsDir: join(root, 'heads'), childrenDir: join(root, 'children'), sessionsDir: join(root, 'sessions') };
  for (const x of Object.values(d)) mkdirSync(x);
  const put = (dir, file, o) => writeFileSync(join(dir, file), JSON.stringify(o));
  return { ...d, put, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

test('ancestors: родитель, дед, до записи без headId', () => {
  const d = dirs();
  try {
    d.put(d.childrenDir, 'C.json', { headId: 'B' });
    d.put(d.childrenDir, 'B.json', { headId: 'A' });
    d.put(d.childrenDir, 'A.json', { name: 'top' });
    assert.deepEqual(ancestors('C', d.childrenDir), ['B', 'A']);
    assert.deepEqual(ancestors('A', d.childrenDir), []);
    assert.deepEqual(ancestors('nobody', d.childrenDir), []);
    assert.deepEqual(ancestors('C', '/nonexistent/children'), []);
  } finally { d.cleanup(); }
});

test('ancestors: петля в цепочке headId останавливается', () => {
  const d = dirs();
  try {
    d.put(d.childrenDir, 'X.json', { headId: 'P' });
    d.put(d.childrenDir, 'P.json', { headId: 'Q' });
    d.put(d.childrenDir, 'Q.json', { headId: 'P' });
    assert.deepEqual(ancestors('X', d.childrenDir), ['P', 'Q']);
    d.put(d.childrenDir, 'S.json', { headId: 'T' });
    d.put(d.childrenDir, 'T.json', { headId: 'S' });
    assert.deepEqual(ancestors('S', d.childrenDir), ['T'], 'на себя не возвращается');
  } finally { d.cleanup(); }
});

test('sessionCwd: метка, затем запись ребёнка, затем реестр', () => {
  const d = dirs();
  try {
    d.put(d.sessionsDir, '42.json', { pid: 42, sessionId: 'S', cwd: '/p/from-registry' });
    assert.equal(sessionCwd('S', d), '/p/from-registry');
    d.put(d.childrenDir, 'S.json', { headId: 'H', cwd: '/p/from-child' });
    assert.equal(sessionCwd('S', d), '/p/from-child');
    d.put(d.headsDir, 'S.json', { sessionId: 'S', cwd: '/p/from-mark' });
    assert.equal(sessionCwd('S', d), '/p/from-mark');
    assert.equal(sessionCwd('ghost', d), null);
    assert.equal(sessionCwd('S', { headsDir: '/no', childrenDir: '/no', sessionsDir: '/no' }), null);
  } finally { d.cleanup(); }
});
