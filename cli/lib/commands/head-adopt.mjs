// claude-wt head adopt: взять живые сессии, которые этот head не открывал, в свои дети
// (Стас 2026-11-12): пикер показывает их под head, раскладка группы их берёт, session close может закрыть.
//   head adopt <name|sessionId>...
//   head adopt --release <name|sessionId>...   (только записи adopted:true)
// Пишет ~/.ccfzf/children/<sid>.json как claude-wt-new, плюс adopted:true; перепривязка от другого head
// сохраняет прежнего в prevHeadId/prevHead. Окна не двигаются.
// Вывод и коды — как у head-adopt.mjs скилла head-session: {ok, results:[...]}; 0 — без отказов, 1 — отказ / не head.
import { readdirSync, writeFileSync, mkdirSync, renameSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { readJson } from '../sources.mjs';
import { ancestors } from '../lineage.mjs';
import { exit, legacyPaths, liveAgents } from '../legacy.mjs';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NOT_HEAD = 'head-adopt только из head-сессии: вызови head-mark';
const fail = (error, extra = {}) => exit(1, { ok: false, error, ...extra });
// "@x", как пользователь пишет в /head-session; sessionId сравниваются в нижнем регистре.
const norm = (t) => { const s = t.replace(/^@/, ''); return UUID.test(s) ? s.toLowerCase() : s; };
const listJson = (dir) => { try { return readdirSync(dir).filter((f) => f.endsWith('.json')); } catch { return []; } };

export default async function headAdopt(argv, env) {
  const p = legacyPaths(env);
  // Не parseLegacyArgs: у скрипта всё, кроме --release, — цели (и слова с `--` тоже).
  const release = argv.includes('--release');
  const targets = argv.filter((a) => a !== '--release');
  if (!targets.length) fail('usage: claude-wt head adopt [--release] <name|sessionId>...');

  // --- только head с живой меткой ---
  const me = env.CLAUDE_CODE_SESSION_ID;
  if (!me) fail(NOT_HEAD, { why: 'CLAUDE_CODE_SESSION_ID missing' });
  if (readJson(join(p.headsDir, `${me}.json`))?.sessionId !== me) fail(NOT_HEAD, { why: 'no head mark' });
  const registry = listJson(p.sessionsDir).map((f) => readJson(join(p.sessionsDir, f))).filter(Boolean);
  const self = registry.find((r) => r.sessionId === me);
  if (!self) fail(NOT_HEAD, { why: 'head mark of a session that is not alive' });
  const myName = self.name;

  let live;
  try {
    live = liveAgents(p, env, { pipe: true });
  } catch (e) {
    fail('claude agents --json failed: nothing adopted or released', { why: String(e.stderr || e.message).trim().slice(0, 300) });
  }

  function findLive(raw) {
    const target = norm(raw);
    const hits = live.filter((s) => (UUID.test(target) ? s.sessionId === target : s.name === target));
    if (!hits.length) return { why: `no live session ${target}` };
    if (hits.length > 1) return { why: `ambiguous name ${target}: ${hits.length} live sessions, pass sessionId` };
    return { session: hits[0] };
  }

  function writeAtomic(sid, obj) {
    mkdirSync(p.childrenDir, { recursive: true });
    const tmp = join(p.childrenDir, `.${sid}.${process.pid}.tmp`);
    writeFileSync(tmp, `${JSON.stringify(obj)}\n`);
    renameSync(tmp, join(p.childrenDir, `${sid}.json`));
  }

  function adopt(target) {
    const { session: s, why } = findLive(target);
    if (!s) return { target, refused: true, why };
    const base = { target, sessionId: s.sessionId, name: s.name, cwd: s.cwd };
    if (s.sessionId === me) return { ...base, refused: true, why: 'cannot adopt self' };
    if (ancestors(me, p.childrenDir).includes(s.sessionId)) {
      return { ...base, refused: true, why: `cycle: ${s.name} is an ancestor of this head` };
    }
    const prev = readJson(join(p.childrenDir, `${s.sessionId}.json`));
    if (prev?.headId === me) return { ...base, already: true };
    writeAtomic(s.sessionId, {
      sessionId: s.sessionId,
      name: s.name,
      head: myName,
      headId: me,
      cwd: s.cwd,
      createdAt: Math.floor(Date.now() / 1000),
      adopted: true,
      ...(prev?.headId && { prevHeadId: prev.headId, prevHead: prev.head ?? null }),
    });
    return { ...base, adopted: true, ...(prev?.headId && { prevHeadId: prev.headId, prevHead: prev.head ?? null }) };
  }

  // Запись для --release ищется по sessionId, по живому имени или по имени в моих записях (сессии может уже не быть).
  function releaseOne(target) {
    const t = norm(target);
    let sid = UUID.test(t) ? t : findLive(t).session?.sessionId;
    if (!sid) {
      const mine = listJson(p.childrenDir)
        .map((f) => readJson(join(p.childrenDir, f))).filter((c) => c?.headId === me && c.name === t);
      if (mine.length === 1) sid = mine[0].sessionId;
      else return { target, refused: true, why: mine.length ? `ambiguous name ${target}: pass sessionId` : `no record for ${target}` };
    }
    const c = readJson(join(p.childrenDir, `${sid}.json`));
    const base = { target, sessionId: sid, name: c?.name ?? null, cwd: c?.cwd ?? null };
    if (!c) return { ...base, refused: true, why: `no record for ${target}` };
    if (c.headId !== me) return { ...base, refused: true, why: `not your child (head: ${c.head ?? c.headId ?? '?'})` };
    if (c.adopted !== true) return { ...base, refused: true, why: 'spawned child: release only adopted (Stas 2026-11-12)' };
    rmSync(join(p.childrenDir, `${sid}.json`), { force: true });
    return { ...base, released: true };
  }

  const results = targets.map(release ? releaseOne : adopt);
  const ok = !results.some((r) => r.refused);
  return { code: ok ? 0 : 1, out: { ok, results } };
}
