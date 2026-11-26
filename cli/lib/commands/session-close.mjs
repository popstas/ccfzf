// claude-wt session close: закрыть дочернюю сессию этого head — SIGTERM её claude, дождаться выхода.
//   session close --session-id <uuid> [--wait 15] [--force] [--kill]
//     --force  закрыть и занятого ребёнка
//     --kill   SIGKILL, если SIGTERM не помог (только по явной просьбе пользователя)
// Только из head с живой меткой и только своих детей. Запись children остаётся (она нужна
// истории пикера); копии промпта и боковые файлы (<sid>.md, .task.md, .mcp.json, .channels, .fork, .model) удаляются.
// Вывод и коды — как у close.mjs скилла session-close: {ok, sessionId, name, closed, adopted, why}; 0 — закрыт, 1 — нет.
import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { readJson } from '../sources.mjs';
import { parseLegacyArgs } from '../args.mjs';
import { exit, legacyPaths, liveAgents } from '../legacy.mjs';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NOT_HEAD = 'session-close только из head-сессии: вызови /head-session';
const out = (ok, o) => exit(ok ? 0 : 1, { ok, ...o });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export default async function sessionClose(argv, env) {
  const args = parseLegacyArgs(argv).flags;
  const p = legacyPaths(env);

  const sessionId = args['session-id'];
  if (typeof sessionId !== 'string' || !UUID.test(sessionId)) {
    out(false, { closed: false, why: 'usage: claude-wt session close --session-id <uuid> [--wait 15] [--force] [--kill]' });
  }

  // --- только head с живой меткой, то же правило, что у session spawn; head может быть и ребёнком ---
  const me = env.CLAUDE_CODE_SESSION_ID;
  const registry = () => readdirSync(p.sessionsDir).filter((f) => f.endsWith('.json')).map((f) => readJson(join(p.sessionsDir, f))).filter(Boolean);
  if (!me) out(false, { sessionId, closed: false, why: NOT_HEAD, detail: 'CLAUDE_CODE_SESSION_ID missing' });
  if (readJson(join(p.headsDir, `${me}.json`))?.sessionId !== me) out(false, { sessionId, closed: false, why: NOT_HEAD, detail: 'no head mark' });
  if (!registry().some((r) => r.sessionId === me)) out(false, { sessionId, closed: false, why: NOT_HEAD, detail: 'head mark of a session that is not alive' });
  if (sessionId === me) out(false, { sessionId, closed: false, why: 'a head does not close itself' });

  // --- цель: живая, своя, свободная ---
  const live = liveAgents(p, env);
  const target = live.find((s) => s.sessionId === sessionId);
  if (!target) out(false, { sessionId, closed: false, why: 'session is not running: nothing to close' });
  const name = target.name;
  const child = readJson(join(p.childrenDir, `${sessionId}.json`));
  // adopted: сессию взял head adopt, head её не открывал. Его несут все ответы отсюда;
  // отказы выше (не head, не запущена) — до чтения записи, без adopted.
  const adopted = Boolean(child?.adopted);
  const outC = (ok, o) => out(ok, { ...o, adopted });
  if (child?.headId !== me) {
    outC(false, {
      sessionId, name, closed: false,
      why: child ? `not your child (head: ${child.head ?? child.headId})` : 'not a child of any head: the user closes it',
    });
  }
  if (target.status === 'busy' && !args.force) {
    outC(false, { sessionId, name, closed: false, why: 'child is busy (working): ask the user, then --force' });
  }

  // pid должен быть всё тем же claude: иначе сигнал получил бы чужой процесс с тем же pid.
  const pid = Number(target.pid);
  const reg = registry().find((r) => r.sessionId === sessionId && Number(r.pid) === pid);
  const startOf = (x) => { try { return readFileSync(`/proc/${x}/stat`, 'utf8').split(') ')[1].split(' ')[19]; } catch { return null; } };
  if (!reg || (reg.procStart && startOf(pid) !== String(reg.procStart))) {
    outC(false, { sessionId, name, closed: false, why: `pid ${pid} does not match the session registry: not signalling` });
  }

  const alive = (x) => { try { process.kill(x, 0); return true; } catch (e) { return e.code === 'EPERM'; } };
  async function waitExit(ms) {
    const end = Date.now() + ms;
    while (Date.now() < end) { if (!alive(pid)) return true; await sleep(300); }
    return !alive(pid);
  }

  process.kill(pid, 'SIGTERM');
  let closed = await waitExit(Number(args.wait ?? 15) * 1000);
  let signal = 'SIGTERM';
  if (!closed && args.kill) {
    process.kill(pid, 'SIGKILL'); // окно остаётся открытым с кодом 137
    signal = 'SIGKILL';
    closed = await waitExit(5000);
  }
  if (!closed) {
    outC(false, { sessionId, name, pid, closed: false, why: `did not exit after ${signal}; SIGKILL only on an explicit request of the user (--kill)` });
  }
  for (const f of [`${sessionId}.md`, `${sessionId}.task.md`, `${sessionId}.mcp.json`, `${sessionId}.channels`, `${sessionId}.fork`, `${sessionId}.model`]) rmSync(join(p.promptsDir, f), { force: true });
  // Отметка закрытия рядом с состоянием хуков: ccfzf (closed_marks) перестаёт
  // считать последнюю отметку хука доводом о жизни. Без неё закрытый ребёнок ещё
  // до HOOK_LIVE_TTL (2 мин) стоял `live` без процесса, и `waiting` его показывал.
  // Сбой записи закрытие не отменяет: процесс уже вышел.
  try {
    const stateDir = env.CLAUDE_WT_STATE_DIR || join(p.home, '.claude', 'claude-wt');
    mkdirSync(stateDir, { recursive: true });
    writeFileSync(join(stateDir, `${sessionId}.closed.json`),
      `${JSON.stringify({ sessionId, closedAt: Math.floor(Date.now() / 1000), by: me })}\n`);
  } catch {}
  outC(true, { sessionId, name, pid, closed: true, signal, why: signal === 'SIGKILL' ? 'killed: the window stays open with code 137' : 'exited on SIGTERM' });
}
