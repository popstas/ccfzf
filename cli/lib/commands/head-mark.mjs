// claude-wt head mark: пометить эту сессию как head — ~/.ccfzf/heads/<sessionId>.json.
// Сессия, записанная чьим-то ребёнком, тоже может быть head (Стас 2026-11-12):
// вывод называет этого родителя. Метка действует, пока сессия жива; её никто не снимает.
// Вывод и коды — как у head-mark.mjs скилла head-session: 0 — помечено (повтор тоже), 1 — отказ.
import { writeFileSync, mkdirSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { readJson } from '../sources.mjs';
import { exit, legacyPaths } from '../legacy.mjs';

const fail = (error, extra = {}) => exit(1, { ok: false, error, ...extra });

export default async function headMark(_argv, env) {
  const p = legacyPaths(env);
  const sessionId = env.CLAUDE_CODE_SESSION_ID;
  const pid = env.CLAUDE_PID;
  if (!sessionId || !pid) fail('not inside a Claude Code session: CLAUDE_CODE_SESSION_ID / CLAUDE_PID missing');
  const reg = readJson(join(p.sessionsDir, `${pid}.json`));
  if (!reg?.name) fail(`no registry name in ~/.claude/sessions/${pid}.json`);

  const child = readJson(join(p.childrenDir, `${sessionId}.json`));
  const parent = child?.headId ? { head: child.head ?? null, headId: child.headId } : null;

  const file = join(p.headsDir, `${sessionId}.json`);
  const prev = readJson(file);
  const mark = {
    sessionId,
    name: reg.name,
    cwd: reg.cwd ?? process.cwd(),
    createdAt: Number.isInteger(prev?.createdAt) ? prev.createdAt : Math.floor(Date.now() / 1000),
  };
  mkdirSync(p.headsDir, { recursive: true });
  // Через временный файл: читатель не должен увидеть полу-запись.
  const tmp = join(p.headsDir, `.${sessionId}.${process.pid}.tmp`);
  writeFileSync(tmp, `${JSON.stringify(mark)}\n`);
  renameSync(tmp, file);
  return { code: 0, out: { ok: true, marked: true, already: Boolean(prev), file, ...mark, parent } };
}
