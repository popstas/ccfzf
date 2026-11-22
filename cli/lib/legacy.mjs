// Команды, переехавшие из скриптов скиллов (session find/rename/close/spawn,
// head mark/adopt). Их вывод и коды — закон: обёртки в скиллах передают те же
// argv, а вызывающие читают ключи по имени. Поэтому у них свой путь мимо
// out.mjs: JSON старого скрипта одной строкой на stdout всегда (без --json и
// без ключа code), stderr — как у скрипта.
import { execFileSync } from 'node:child_process';
import { homedir } from 'node:os';
import { join } from 'node:path';

// Ранний выход посреди проверки: в скриптах это был process.exit — здесь
// бросок, его ловит диспетчер. Порядок проверок остаётся прежним.
export class LegacyExit {
  constructor(code, out, stderr) { this.code = code; this.out = out; this.stderr = stderr; }
}
export const exit = (code, out, stderr) => { throw new LegacyExit(code, out, stderr); };

// Пути — от HOME с прежними подменами окружения; `claude` — из PATH
// (CLAUDE_BIN — для тестов CLI; harness скиллов его вычищает).
export function legacyPaths(env) {
  const home = env.HOME || homedir();
  return {
    home,
    claudeBin: env.CLAUDE_BIN || 'claude',
    headsDir: env.CCFZF_HEADS_DIR || join(home, '.ccfzf', 'heads'),
    childrenDir: env.CCFZF_CHILDREN_DIR || join(home, '.ccfzf', 'children'),
    windowsDir: env.CCFZF_WINDOWS_DIR || join(home, '.ccfzf', 'windows'),
    promptsDir: join(home, '.ccfzf', 'prompts'),
    sessionsDir: join(home, '.claude', 'sessions'),
  };
}

// Живые сессии, как их видит Claude Code. Ошибка — бросок как есть: каждая
// команда отвечает на неё по-своему, как её скрипт.
export function liveAgents(p, env, { pipe = false } = {}) {
  const out = execFileSync(p.claudeBin, ['agents', '--json'], {
    encoding: 'utf8', timeout: 15000, env, ...(pipe && { stdio: ['ignore', 'pipe', 'pipe'] }),
  });
  return JSON.parse(out);
}

// Результат команды → поток и код. undefined out — на stdout ничего.
export function emitLegacy({ code, out, stderr }) {
  if (stderr) process.stderr.write(stderr.endsWith('\n') ? stderr : `${stderr}\n`);
  if (out !== undefined) process.stdout.write(`${JSON.stringify(out)}\n`);
  return code;
}

// Запуск: возврат {code, out, stderr} или бросок LegacyExit.
export async function runLegacy(run, argv, env) {
  try {
    return await run(argv, env);
  } catch (e) {
    if (e instanceof LegacyExit) return { code: e.code, out: e.out, stderr: e.stderr };
    throw e;
  }
}
