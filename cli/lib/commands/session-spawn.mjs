// claude-wt session spawn: открыть дочернюю сессию Claude Code в окне claude-wt (POST /claude-wt/session-new).
//   session spawn --task <slug> --prompt-file <path> [--cwd <dir>] [--dry-run]
//                 [--name <full name>] [--machine <host>] [--url http://host:port]
//                 [--permission-mode <mode>] [--terminal <t>] [--cursor <c>] [--timeout 20]
//                 [--zone <monitor>:<position>]   зона FancyZones; без неё решает конфиг менеджера
//                 [--session-id <uuid>]           вместо случайного (бот-делегат регистрирует его заранее)
//                 [--mcp-config <file.json>]      копия в ~/.ccfzf/prompts/<sid>.mcp.json, claude-wt-new передаёт --mcp-config
//                 [--dev-channels server:a,...]   ~/.ccfzf/prompts/<sid>.channels по строке, claude-wt-new передаёт
//                                                 --dangerously-load-development-channels
//                 [--fork]                        ребёнок стартует форком разговора этого head:
//                                                 ~/.ccfzf/prompts/<sid>.fork, claude-wt-new передаёт
//                                                 --resume <headId> --fork-session
//                 [--model <name>]                модель ребёнка: ~/.ccfzf/prompts/<sid>.model, claude-wt-new
//                                                 передаёт --model <name> (sonnet, opus, claude-sonnet-5-5, opus[1m])
// Только изнутри head-сессии (нужны CLAUDE_PID / CLAUDE_CODE_SESSION_ID). Ребёнок стартует с коротким
// вступлением (кто его head, ответить ему «готов»); задача из --prompt-file лежит в taskFile, и head
// шлёт её сообщением после «готов»: у первого промпта нет отправителя, и ребёнок с целой задачей
// отчитывался бы в свой чат. У --fork вступление другое: над ребёнком весь разговор head, и ему
// надо сказать, что он не head.
// Вывод и коды — как у spawn.mjs скилла session-spawn: 0 — открыта (или dry-run), 1 — отказ,
// 3 — исход неизвестен (таймаут): НЕ повторять, искать по выданному sessionId.
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import {
  readFileSync, writeFileSync, readdirSync, mkdirSync, chmodSync, rmSync, openSync, readSync, closeSync, fstatSync,
  accessSync, constants as fsc,
} from 'node:fs';
import { join, resolve } from 'node:path';
import { readJson, readTrackers } from '../sources.mjs';
import { parseLegacyArgs } from '../args.mjs';
import { ancestors, sessionCwd } from '../lineage.mjs';
import { managerFor } from '../manager.mjs';
import { exit, legacyPaths, LegacyExit } from '../legacy.mjs';

const ROUTE = '/claude-wt/session-new';
const ISSUED_NAME_TTL_MS = 10 * 60 * 1000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// То же правило, что у claude-wt-new: строку, которую он не примет, он остановит (код 2).
const CHANNEL = /^server:[a-z0-9][a-z0-9-]{0,40}$/;
// Имя модели уходит в argv claude: алиас, полный id, суффикс окна вроде [1m]. Тот же знак у claude-wt-new.
const MODEL = /^[a-z0-9][a-z0-9.[\]-]{0,60}$/;
// Префикс имени ребёнка (Стас 13.11, точка с 21.11: ведущее тире читается как опция в
// claude --resume, ccfzf --session и менеджере). --name берётся как есть.
const CHILD_MARK = '.';
const NOT_HEAD = 'session-spawn только из head-сессии: вызови /head-session';

const fail = (msg, extra = {}) => exit(1, { ok: false, error: msg, ...extra });

// --- открывать может только head: живая метка head mark. Ребёнок тоже может быть head (Стас 2026-11-12) ---
function requireHead(p, env) {
  const sid = env.CLAUDE_CODE_SESSION_ID;
  if (!sid) fail(NOT_HEAD, { why: 'CLAUDE_CODE_SESSION_ID missing' });
  const mark = readJson(join(p.headsDir, `${sid}.json`));
  if (mark?.sessionId !== sid) fail(NOT_HEAD, { why: 'no head mark', sessionId: sid });
  // Метка действует, только пока её сессия жива.
  const alive = readdirSync(p.sessionsDir).some((f) => f.endsWith('.json') && readJson(join(p.sessionsDir, f))?.sessionId === sid);
  if (!alive) fail(NOT_HEAD, { why: 'head mark belongs to a session that is not alive', sessionId: sid });
}

// --- сам head: читается в момент вызова, имена под нами меняются ---
function head(p, env) {
  const pid = env.CLAUDE_PID;
  const headId = env.CLAUDE_CODE_SESSION_ID;
  if (!pid || !headId) fail('not inside a Claude Code session: CLAUDE_PID / CLAUDE_CODE_SESSION_ID missing');
  const reg = readJson(join(p.sessionsDir, `${pid}.json`));
  if (!reg?.name) fail(`no registry name in ~/.claude/sessions/${pid}.json`);
  const cwd = reg.cwd ?? readJson(join(p.headsDir, `${headId}.json`))?.cwd;
  return { name: reg.name, headId, cwd };
}

// Откуда профиль терминала для ребёнка вне claudeWt.projects: ближайший из head, его родителя, …,
// чей cwd — проект машины окна.
function profileCwd(p, me, projects) {
  const dirs = { headsDir: p.headsDir, childrenDir: p.childrenDir, sessionsDir: p.sessionsDir };
  const chain = [me.cwd, ...ancestors(me.headId, p.childrenDir).map((id) => sessionCwd(id, dirs))];
  return chain.find((c) => c && projects.includes(c));
}

// Режима прав нет ни в окружении, ни в реестре; транскрипт пишет его в каждую запись пользователя.
function permissionMode(p, headId) {
  const root = join(p.home, '.claude', 'projects');
  for (const dir of readdirSync(root)) {
    const f = join(root, dir, `${headId}.jsonl`);
    let fd;
    try { fd = openSync(f, 'r'); } catch { continue; }
    try {
      const size = fstatSync(fd).size;
      for (let chunk = 256 * 1024; ; chunk *= 4) {
        const len = Math.min(chunk, size);
        const buf = Buffer.alloc(len);
        readSync(fd, buf, 0, len, size - len);
        const m = [...buf.toString('utf8').matchAll(/"permissionMode":"([A-Za-z]+)"/g)];
        if (m.length) return m[m.length - 1][1];
        if (len === size) return undefined;
      }
    } finally { closeSync(fd); }
  }
  return undefined;
}

// --- уникальное имя: живые сессии + недавно выданные, но, может, ещё не записанные ---
function takenNames(p, env) {
  const taken = new Set();
  const live = JSON.parse(execFileSync(p.claudeBin, ['agents', '--json'], { encoding: 'utf8', timeout: 15000, env }));
  for (const s of live) if (s.name) taken.add(s.name);
  let files = [];
  try { files = readdirSync(p.childrenDir); } catch {}
  for (const f of files) {
    const c = readJson(join(p.childrenDir, f));
    // claude-wt-new пишет unix-секунды
    const n = Number(c?.createdAt);
    const at = Number.isFinite(n) ? (n < 1e12 ? n * 1000 : n) : Date.parse(c?.createdAt ?? '') || 0;
    if (c?.name && Date.now() - at < ISSUED_NAME_TTL_MS) taken.add(c.name);
  }
  return taken;
}

function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9а-яё]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 40);
}

function uniqueName(base, taken) {
  if (!taken.has(base)) return base;
  for (let i = 2; ; i++) if (!taken.has(`${base}-${i}`)) return `${base}-${i}`;
}

// --- где откроется окно: самый свежий файл трекера с http-портом (или --machine / --url) ---
// Выбор машины — свой (у spawn нет окна-ориентира: берётся свежайший трекер), адрес — managerFor.
function managerUrl(p, args) {
  const trackers = readTrackers(p.windowsDir); // --url работает и на машине без трекеров
  const lc = (x) => String(x ?? '').toLowerCase();
  if (typeof args.url === 'string') {
    const m = managerFor({ url: args.url, trackers });
    if (m.error) fail(m.error);
    let hostname = null;
    try { hostname = new URL(m.url).hostname; } catch {}
    // URL может называть адрес трекера (http.host) или саму машину (host).
    const t = trackers.find((x) => [x.http?.host, x.host].some((h) => h && lc(h) === hostname));
    return { url: m.url, source: '--url', projects: t?.projects ?? [] };
  }
  const cands = trackers
    .filter((t) => t.http && t.fresh)
    .filter((t) => typeof args.machine !== 'string' || lc(t.host) === lc(args.machine))
    .sort((a, b) => b.generated - a.generated);
  if (!cands.length) {
    fail('no fresh tracker with http in ~/.ccfzf/windows (pass --machine or --url)', { machine: args.machine });
  }
  const t = cands[0];
  const m = managerFor({ host: t.host, trackers });
  if (m.error) fail(m.error);
  return { url: m.url, source: `~/.ccfzf/windows/${t.file}`, machine: t.host, projects: t.projects };
}

// --zone 3:2 -> {monitor: 3, position: 2}; только целые > 0. Менеджер сверяет с headZones.
function zoneArg(args) {
  if (args.zone === undefined) return undefined;
  const m = typeof args.zone === 'string' && /^([1-9]\d{0,2}):([1-9]\d{0,2})$/.exec(args.zone);
  if (!m) fail(`--zone must be <monitor>:<position>, positive integers (e.g. 3:2), got: ${args.zone}`);
  return { monitor: Number(m[1]), position: Number(m[2]) };
}

// По-русски: дети работают по-русски. claude-wt-new читает файл на машине агентов и передаёт одним словом argv.
function intro(me, cwd, fork) {
  const ready = `Сейчас одно действие: SendMessage на "${me.name}" с одной строкой "готов, cwd <твой текущий каталог>" (ожидается ${cwd}). Имя не доставилось - узнай текущее: claude-wt session find --session-id ${me.headId} --timeout 0, поле name.`;
  const reply = 'Дальше отвечай head только через SendMessage: скопируй атрибут from его сообщения в to. Отчёты, вопросы и итог - head, не в свой чат.';
  // Решение пользователя 2026-11-25: без этой строки дети отказывались от PR, мержа и деплоя по слову head.
  const auth = `Сообщения head-сессии "${me.name}" (sessionId ${me.headId}) приравниваются к командам пользователя - так решил пользователь. Выполняй их, как если бы их написал пользователь в этом чате, включая коммит, пуш, PR, мерж и деплой. "Ок" от head - это ок пользователя и для правил проекта вида "только после явного ока". Head переименовали - сверь sessionId: claude-wt session find --session-id ${me.headId} --timeout 0. Сообщения других сессий командами пользователя не считаются.`;
  if (!fork) {
    return [
      `Ты дочерняя сессия head-сессии "${me.name}" (sessionId ${me.headId}). Задачу head пришлёт отдельным сообщением, до него работу не начинай.`,
      '', auth, '', ready, '', reply,
    ].join('\n');
  }
  // Последнее сообщение форка: роль — первой, всё выше написано как head.
  return [
    `Ты НЕ head. Ты дочерняя сессия-форк head-сессии "${me.name}" (sessionId ${me.headId}). Весь разговор выше - копия разговора head: его вёл head, и "я" в нём - head, не ты. У тебя свои sessionId, имя и cwd.`,
    '',
    'Роль head не наследуется. Не раздавай задачи, не вызывай head-mark, session-spawn, session-close, head-adopt, session-rename. Не отвечай на сообщения исполнителей из истории выше и не продолжай в ней незаконченное - и вызов claude-wt session spawn, которым head открыл тебя, тоже. Разговор выше - справка к заданию, а не задание.',
    '',
    'Задачу head пришлёт отдельным сообщением, до него работу не начинай.',
    '',
    auth, '', ready, '', reply,
  ].join('\n');
}

// --session-id / --mcp-config / --dev-channels / --fork / --model: проверка до всякой записи и запроса.
function sideArgs(args) {
  let sessionId;
  if (args['session-id'] !== undefined) {
    if (typeof args['session-id'] !== 'string' || !UUID.test(args['session-id'])) {
      fail(`--session-id must be a uuid, got: ${args['session-id']}`);
    }
    sessionId = args['session-id'].toLowerCase();
  }
  let mcpText;
  if (args['mcp-config'] !== undefined) {
    if (typeof args['mcp-config'] !== 'string') fail('--mcp-config <file.json> needs a path');
    try { mcpText = readFileSync(args['mcp-config'], 'utf8'); } catch (e) { fail(`--mcp-config: cannot read ${args['mcp-config']}: ${e.code ?? e.message}`); }
    try { JSON.parse(mcpText); } catch (e) { fail(`--mcp-config: not JSON: ${args['mcp-config']}: ${e.message}`); }
  }
  let channels;
  if (args['dev-channels'] !== undefined) {
    const list = typeof args['dev-channels'] === 'string' ? args['dev-channels'].split(',').map((c) => c.trim()).filter(Boolean) : [];
    if (!list.length) fail('--dev-channels needs a comma-separated list like server:telegram-delegate');
    const bad = list.find((c) => !CHANNEL.test(c));
    if (bad !== undefined) fail(`--dev-channels: "${bad}" does not match ${CHANNEL}`);
    channels = list;
  }
  // Флаг: разбор взял бы следующее слово значением и потерял бы его.
  if (args.fork !== undefined && args.fork !== true) fail(`--fork takes no value, got: ${args.fork}`);
  let model;
  if (args.model !== undefined) {
    if (typeof args.model !== 'string') fail('--model <name> needs a model name, e.g. sonnet');
    if (!MODEL.test(args.model)) fail(`--model: "${args.model}" does not match ${MODEL}`);
    model = args.model;
  }
  return { sessionId, mcpText, channels, fork: args.fork === true, model };
}

// claude-wt-new работает на этой машине: менеджер запускает его сюда по ssh, и он читает файлы промпта,
// записанные ниже. Старый файл не читает — сказать сразу, а не открыть ребёнка без него.
function wrapperText(env, flag) {
  const dir = (env.PATH || '').split(':').find((d) => {
    try { accessSync(join(d, 'claude-wt-new'), fsc.X_OK); return true; } catch { return false; }
  });
  if (!dir) return { missing: true };
  const path = join(dir, 'claude-wt-new');
  try { return { path, text: readFileSync(path, 'utf8') }; } catch (e) { fail(`${flag}: cannot read ${path}: ${e.code ?? e.message}`); }
}

// Без <sid>.fork ребёнок стартовал бы пустым под вступлением форка.
function requireForkSupport(env) {
  const w = wrapperText(env, '--fork');
  if (w.missing) fail('--fork: claude-wt-new не найден в PATH, поддержку форка не проверить');
  if (!w.text.includes('$sid.fork')) {
    fail('--fork: этот claude-wt-new не умеет форк, ребёнок стартовал бы пустым', {
      why: `${w.path} не читает <sid>.fork: нужен claude-wt-new из ccfzf с PR #27 (popstas/ccfzf, feat/fork-child)`,
    });
  }
}

// Без <sid>.model ребёнок молча стартовал бы на модели по умолчанию.
function requireModelSupport(env) {
  const w = wrapperText(env, '--model');
  if (w.missing) fail('--model: claude-wt-new is not in PATH, cannot check that it passes the model on');
  if (!w.text.includes('$sid.model')) {
    fail('--model: this claude-wt-new does not pass a model on, the child would start on the default one', {
      why: `${w.path} does not read <sid>.model: update claude-wt-new from popstas/ccfzf`,
    });
  }
}

async function spawnChild(argv, env) {
  const args = parseLegacyArgs(argv).flags;
  const p = legacyPaths(env);
  const zone = zoneArg(args);
  const side = sideArgs(args);
  if (side.fork) requireForkSupport(env);
  if (side.model) requireModelSupport(env);
  requireHead(p, env);
  const cwd = resolve(typeof args.cwd === 'string' ? args.cwd : process.cwd());
  const promptSrc = args['prompt-file'];
  if (typeof promptSrc !== 'string') fail('--prompt-file <path> is required');
  const promptText = readFileSync(promptSrc, 'utf8');
  if (!promptText.trim()) fail(`prompt file is empty: ${promptSrc}`);

  const me = head(p, env);
  let base;
  if (typeof args.name === 'string') base = args.name;
  // Короткое имя со знаком ветки, без имени head впереди (Стас 13.11): пикер и так показывает ребёнка под head.
  else if (typeof args.task === 'string') {
    const s = slug(args.task);
    if (!s) fail('--task gives an empty name: use latin or cyrillic letters or digits');
    base = `${CHILD_MARK}${s}`;
  } else fail('--task <slug> or --name <full name> is required');
  const name = uniqueName(base, takenNames(p, env));

  const sessionId = side.sessionId ?? randomUUID();
  const promptFile = join(p.promptsDir, `${sessionId}.md`); // промпт запуска: вступление
  const taskFile = join(p.promptsDir, `${sessionId}.task.md`); // вся задача, head шлёт её после «готов»
  // Боковые файлы рядом с промптом читает claude-wt-new на машине агентов; тело session-new не меняется.
  const mcpConfig = side.mcpText !== undefined ? join(p.promptsDir, `${sessionId}.mcp.json`) : undefined;
  const channelsFile = side.channels ? join(p.promptsDir, `${sessionId}.channels`) : undefined;
  const forkFile = side.fork ? join(p.promptsDir, `${sessionId}.fork`) : undefined;
  const modelFile = side.model ? join(p.promptsDir, `${sessionId}.model`) : undefined;
  const sideOut = {
    ...(mcpConfig && { mcpConfig }), ...(side.channels && { devChannels: side.channels }), ...(forkFile && { fork: true, forkFile }),
    ...(modelFile && { model: side.model, modelFile }),
  };
  const introText = intro(me, cwd, side.fork);
  // SPAWN_TEST_HEAD_MODE: только для тестов, подменяет режим head из его транскрипта.
  const mode = typeof args['permission-mode'] === 'string'
    ? args['permission-mode']
    : env.SPAWN_TEST_HEAD_MODE || permissionMode(p, me.headId);
  // Решение Стаса: дети не получают bypassPermissions, ни унаследованным, ни явным.
  if (mode === 'bypassPermissions') {
    const own = typeof args['permission-mode'] !== 'string';
    fail('bypassPermissions для дочерних сессий запрещён', {
      why: own
        ? 'head работает в bypassPermissions и передал бы его ребёнку: запусти с --permission-mode auto'
        : '--permission-mode bypassPermissions не принимается: выбери auto или другой режим',
    });
  }
  const target = managerUrl(p, args);
  const profile = profileCwd(p, me, target.projects);

  const body = {
    cwd,
    name,
    sessionId,
    promptFile,
    ...(mode && { permissionMode: mode }),
    head: me.name,
    headId: me.headId,
    ...(me.cwd && { headCwd: me.cwd }),
    ...(profile && { profileCwd: profile }),
    ...(typeof args.terminal === 'string' && { terminal: args.terminal }),
    ...(typeof args.cursor === 'string' && { cursor: args.cursor }),
    ...(zone && { zone }),
  };
  const url = target.url + ROUTE;

  // То же сито, что у менеджера (session-new-helpers.js): эти знаки ломают командную строку wt.exe / ssh.
  for (const k of ['cwd', 'name', 'promptFile', 'head']) {
    if (/[;"'`$\\{}]/.test(body[k]) || /[\x00-\x1f]/.test(body[k])) fail(`${k} has characters the launch command cannot carry: ${body[k]}`);
  }
  if (body.name.startsWith('-') || body.head.startsWith('-')) fail('name and head must not start with a dash');

  if (args['dry-run']) {
    return { code: 0, out: { dryRun: true, url, urlSource: target.source, nameRequested: base, sessionId, ...sideOut, body, intro: introText, taskFile, taskBytes: Buffer.byteLength(promptText) } };
  }

  mkdirSync(p.promptsDir, { recursive: true, mode: 0o700 });
  chmodSync(p.promptsDir, 0o700);
  writeFileSync(promptFile, introText, { mode: 0o600 });
  writeFileSync(taskFile, promptText, { mode: 0o600 });
  if (mcpConfig) writeFileSync(mcpConfig, side.mcpText, { mode: 0o600 });
  if (channelsFile) writeFileSync(channelsFile, side.channels.map((c) => `${c}\n`).join(''), { mode: 0o600 });
  // claude-wt-new смотрит только на наличие; id head внутри — для человека, читающего каталог.
  if (forkFile) writeFileSync(forkFile, `${me.headId}\n`, { mode: 0o600 });
  if (modelFile) writeFileSync(modelFile, `${side.model}\n`, { mode: 0o600 });
  const dropCopies = () => { for (const f of [promptFile, taskFile, mcpConfig, channelsFile, forkFile, modelFile]) if (f) rmSync(f, { force: true }); };
  const unknown = (code) => ({
    code: 3,
    out: {
      ok: 'unknown', error: code, url, sessionId, name, taskFile, ...sideOut,
      hint: 'outcome unknown - do NOT resend; run session-find --session-id with this sessionId',
    },
  });

  // Ровно одна попытка: путь не идемпотентен, повтор открывает второе окно. Свой fetch, не post():
  // error — сырой код (его читают вызывающие), а «не дошло» — только по этому короткому списку.
  const timeoutMs = Number(args.timeout ?? 20) * 1000;
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    const code = e.cause?.code || e.name;
    const notSent = ['ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN', 'EHOSTUNREACH'].includes(code);
    if (notSent) dropCopies();
    return notSent ? {
      code: 1,
      out: { ok: false, error: code, url, sessionId, name, hint: 'request did not reach the manager; safe to fix the address and spawn again' },
    } : unknown(code);
  }
  // Тело 2xx не дочиталось (таймаут, обрыв посреди) — менеджер уже взялся за окно:
  // исход неизвестен, копии нужны ребёнку, повтор открыл бы второе окно.
  // (Скрипт отвечал здесь отказом 200 "OK" и стирал копии.) Тело не JSON — как раньше.
  let raw;
  try { raw = await res.text(); } catch (e) {
    if (res.ok) return unknown(e.cause?.code || e.name);
  }
  let data = {};
  try { data = JSON.parse(raw); } catch {}
  if (res.status === 200 && data.ok) {
    return {
      code: 0,
      out: {
        ok: true, sessionId: data.sessionId ?? sessionId, name: data.name ?? name, head: me.name, headId: me.headId, url, promptFile, taskFile, ...sideOut,
        next: 'session-find --session-id, wait for the child\'s "готов" message, then SendMessage the taskFile text to its from, notify_when_idle: true',
      },
    };
  }
  dropCopies(); // отказ: их никто не прочтёт
  const why = res.status === 403
    ? 'manager refused (reason in error). Passes: cwd in claudeWt.projects, or with headId - head window on this machine, headCwd in claudeWt.projects or under childCwdRoot, cwd under childCwdRoot'
    : undefined;
  return { code: 1, out: { ok: false, status: res.status, error: data.reason ?? data.error ?? res.statusText, ...(why && { why }), url, sessionId, name } };
}

// Сбой посреди (нет файла промпта, упал claude agents) — {ok:false, error} и код 1, как у скрипта.
export default async function sessionSpawn(argv, env) {
  try {
    return await spawnChild(argv, env);
  } catch (e) {
    if (e instanceof LegacyExit) throw e;
    return { code: 1, out: { ok: false, error: e.message } };
  }
}
