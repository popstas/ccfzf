// claude-wt session find: живая сессия по sessionId (или имени) и её текущее имя.
//   session find --session-id <uuid> [--timeout 45] [--interval 2]
//   session find --name <name>
//   session find --list [--cwd <path>]
// Место окна (windowHost, monitor, zone, slot) — из ~/.ccfzf/windows/*.json, null, если нет.
// Вывод и коды — как у find.mjs скилла session-find: 0 найдено, 2 нет (после таймаута), 1 ошибка.
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { readJson } from '../sources.mjs';
import { parseLegacyArgs } from '../args.mjs';
import { legacyPaths, liveAgents } from '../legacy.mjs';

const USAGE = 'usage: claude-wt session find --session-id <uuid> [--timeout 45] | --name <name> | --list [--cwd <path>]';

// Поля, которые есть только в файле реестра процесса (nameSource, formerNames).
function registry(p, pid) {
  const r = readJson(join(p.sessionsDir, `${pid}.json`));
  if (!r) return {};
  return { nameSource: r.nameSource, formerNames: (r.formerNames || []).map((f) => f.name) };
}

// Где стоит окно: демон окон пишет ~/.ccfzf/windows/<host>.json, окна — по sessionId.
// monitor/zone/slot появились с зонами head; в старых файлах их нет — null.
function placement(p, sessionId) {
  let files = [];
  try { files = readdirSync(p.windowsDir).filter((f) => f.endsWith('.json')); } catch {}
  let best = null;
  for (const f of files) {
    const o = readJson(join(p.windowsDir, f));
    const w = o?.windows?.[sessionId];
    if (!w || typeof w !== 'object') continue;
    if (best && (best.generated ?? 0) >= (o.generated ?? 0)) continue;
    best = { generated: o.generated, host: o.host ?? f.replace(/\.json$/, ''), w };
  }
  const v = (k) => (best && Number.isInteger(best.w[k]) ? best.w[k] : null);
  return { windowHost: best?.host ?? null, monitor: v('monitor'), zone: v('zone'), slot: v('slot') };
}

function describe(p, s, all) {
  const dupes = all.filter((x) => x.name === s.name && x.sessionId !== s.sessionId).length;
  return {
    found: true,
    sessionId: s.sessionId,
    name: s.name,
    status: s.status,
    kind: s.kind,
    cwd: s.cwd,
    pid: s.pid,
    ...registry(p, s.pid),
    ...placement(p, s.sessionId),
    duplicateName: dupes > 0,
  };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function find(argv, env) {
  const args = parseLegacyArgs(argv).flags;
  const p = legacyPaths(env);
  const agents = () => liveAgents(p, env);

  if (args.list) {
    let list = agents();
    if (typeof args.cwd === 'string') list = list.filter((s) => s.cwd === args.cwd);
    return { code: 0, out: list.map((s) => ({ name: s.name, sessionId: s.sessionId, status: s.status, kind: s.kind, cwd: s.cwd })) };
  }

  if (typeof args.name === 'string') {
    const all = agents();
    const hits = all.filter((s) => s.name === args.name);
    if (!hits.length) return { code: 2, out: { found: false, name: args.name } };
    return { code: 0, out: hits.length === 1 ? describe(p, hits[0], all) : hits.map((h) => describe(p, h, all)) };
  }

  const id = args['session-id'];
  if (typeof id !== 'string') return { code: 1, stderr: USAGE };
  const timeoutMs = Number(args.timeout ?? 45) * 1000;
  const intervalMs = Number(args.interval ?? 2) * 1000;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const all = agents();
    const s = all.find((x) => x.sessionId === id);
    if (s) return { code: 0, out: describe(p, s, all) };
    if (Date.now() >= deadline) break;
    await sleep(intervalMs);
  }
  // Что записали session spawn / claude-wt-new о ребёнке, если что-то записали.
  const c = readJson(join(p.childrenDir, `${id}.json`));
  return {
    code: 2,
    out: {
      found: false,
      sessionId: id,
      waitedSec: timeoutMs / 1000,
      childRecord: c,
      hint: c
        ? 'claude-wt-new recorded the launch, but the session is not live: window closed, claude crashed, or still starting (trust dialog?)'
        : 'no launch record in ~/.ccfzf/children: the request probably never reached the machine where claude-wt-new runs',
    },
  };
}

// Сбой (claude agents упал) — сообщение в stderr и код 1, как у скрипта.
export default async function sessionFind(argv, env) {
  try { return await find(argv, env); } catch (e) { return { code: 1, stderr: e.message }; }
}
