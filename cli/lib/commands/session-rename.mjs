// claude-wt session rename: поставить в очередь новое имя живой сессии Claude Code;
// pending-title-hook.sh применит его на следующем промпте цели (хватит SendMessage).
//   session rename --session-id <uuid> --to <new name> [--settings <file>]
//   session rename --session-id <uuid> --cancel
// Вывод и коды — как у rename.mjs скилла session-rename: 0 — в очереди, 1 — ошибка.
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { parseLegacyArgs } from '../args.mjs';
import { exit, legacyPaths, liveAgents } from '../legacy.mjs';

const HOOK = 'session-rename/pending-title-hook.sh';
const fail = (error, extra = {}) => exit(1, { ok: false, error, ...extra });

// Подключён ли хук хоть в одном файле настроек, который читает Claude Code? Без него очередь не читают.
function hookRegistered(p, args) {
  const files = [join(p.home, '.claude', 'settings.json'), join(p.home, '.claude', 'settings.local.json')];
  if (typeof args.settings === 'string') files.push(args.settings);
  return files.some((f) => { try { const t = readFileSync(f, 'utf8'); return t.includes(HOOK) || t.includes('pending-title-hook'); } catch { return false; } });
}

export default async function sessionRename(argv, env) {
  const args = parseLegacyArgs(argv).flags;
  const p = legacyPaths(env);
  const dir = env.SESSION_RENAME_DIR || join(p.home, '.claude', 'hooks', 'state', 'session-rename');

  const id = args['session-id'];
  if (typeof id !== 'string') fail('usage: claude-wt session rename --session-id <uuid> --to <new name> | --cancel');
  const file = join(dir, id);

  if (args.cancel) { rmSync(file, { force: true }); return { code: 0, out: { ok: true, cancelled: true, sessionId: id } }; }

  const to = typeof args.to === 'string' ? args.to.trim() : '';
  if (!to || /[\x00-\x1f]/.test(to)) fail('--to <new name> is required, one line');

  const live = liveAgents(p, env);
  const target = live.find((s) => s.sessionId === id);
  if (!target) fail('session is not live', { sessionId: id });
  const clash = live.find((s) => s.name === to && s.sessionId !== id);
  if (clash) fail('name is taken by another live session', { name: to, takenBy: clash.sessionId });

  // Без хука имя пролежало бы в очереди и сработало много позже, когда хук кто-то подключит.
  if (!hookRegistered(p, args)) {
    fail('pending-title-hook.sh is not registered in settings (hooks.UserPromptSubmit): nothing queued', {
      hookRegistered: false,
      sessionId: id,
    });
  }
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  writeFileSync(file, `${to}\n`, { mode: 0o600 });
  return {
    code: 0,
    out: {
      ok: true,
      queued: true,
      sessionId: id,
      from: target.name,
      to,
      hookRegistered: true,
      next: `SendMessage to "${target.name}" (any short message), then session-find --session-id ${id}`,
    },
  };
}
