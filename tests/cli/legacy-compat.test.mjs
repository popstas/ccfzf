// Сравнение со старыми скриптами скиллов на одной фикстуре (Review Focus 1):
// JSON и код выхода CLI = JSON и код скрипта. Каталог скриптов — WT_LEGACY_SKILLS
// (снимок закоммиченных скриптов); без него тесты пропускаются.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { legacyWorld, runAsync, runOld, normalize, LEGACY } from './legacy-world.mjs';

const skip = !LEGACY && 'WT_LEGACY_SKILLS не задан';
const SID = 'cccccccc-0000-4000-8000-000000000001';

// Два одинаковых мира: один для скрипта, другой для CLI (команды пишут файлы).
async function both(setup, rel, cmd, args, drop = [], { noJson = false } = {}) {
  const a = legacyWorld({ sessionId: SID, pid: 910001 });
  const b = legacyWorld({ sessionId: SID, pid: 910001 });
  try {
    setup(a); setup(b);
    const old = await runOld(rel, args(a), a.env);
    const neu = await runAsync(cmd, args(b), b.env);
    // Пустой вывод у обоих сравнился бы «равным» — снимок обязан быть.
    if (!noJson) assert.ok(old.json !== null, `старый скрипт без JSON: ${old.stdout}${old.stderr}`);
    assert.equal(neu.code, old.code, `код: ${neu.stdout}${neu.stderr} / ${old.stdout}${old.stderr}`);
    assert.deepEqual(normalize(neu.json, b.home, drop), normalize(old.json, a.home, drop));
    return { old, neu };
  } finally { a.cleanup(); b.cleanup(); }
}

test('head mark: как head-mark.mjs', { skip }, async () => {
  await both(() => {}, 'head-session/head-mark.mjs', ['head', 'mark'], () => [], ['createdAt']);
  await both((w) => { w.mark(); w.write(`.ccfzf/children/${SID}.json`, { headId: 'T', head: 'top' }); }, 'head-session/head-mark.mjs', ['head', 'mark'], () => []);
  await both((w) => { delete w.env.CLAUDE_PID; }, 'head-session/head-mark.mjs', ['head', 'mark'], () => []);
});
