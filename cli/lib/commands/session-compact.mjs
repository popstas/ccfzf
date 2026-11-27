// claude-wt session compact <session> [--min-idle <мин>] [--dry-run]: набрать
// `/compact` в поле ввода простаивающей сессии — просьба таймера автокомпакта
// пикера (решения Стаса 27.11, 2a): сжать контекст, пока кеш промпта ещё тёплый.
//
// Механика session type (готовность по реестру и state.json хуков, проба окна
// WezTerm, пустое поле `❯`, вставка, Enter после повторной проверки, журнал
// ~/.ccfzf/typed.jsonl), но текст фиксирован, вызывающая сессия не нужна и
// проверки «только дети» нет: зовёт пикер по ssh, сам он не сессия. Узость
// команды и есть ограничение — произвольный текст сюда не проходит, а
// session type остаётся только для детей.
//
// Отказы машинно различимы: поле `reason` (slug), `error` — текст для
// человека. Пикер пишет их в свой журнал. --min-idle меряется от `cacheAt`
// (последний ответ с кешем, `agent.cacheAt` в --state), а не от `updated`:
// idle-уведомление и хук fail двигают `updated` без запроса к API (решение
// coord 27.11). Верхнюю границу (кеш уже мёртв) проверяет пикер.
//
// Строка-намерение перед Enter (`command: "compact"`, `step: "enter"`,
// `atSec`) — маркер для хука wt-progress.sh: по ней PreCompact отличает
// автокомпакт от набранного руками и не меняет состояние просмотра.
import { join } from 'node:path';
import { EXIT } from '../out.mjs';
import { picture } from './tree.mjs';
import { readAgents, readJson } from '../sources.mjs';
import { resolveSession, resolveError } from '../resolve.mjs';
import { registryRecord, readiness, pickPane, inputBox, boxHasText, journal } from '../type.mjs';
import { where, trackerWindow, call } from './session-type.mjs';

export const TEXT = '/compact';
const USAGE = 'usage: session compact <session> [--min-idle <min>] [--dry-run]';
// Флаги общего разбора, которых у команды нет.
const FOREIGN = ['url', 'machine', 'enter', 'check', 'clear', 'tree', 'sessions', 'zone', 'kind', 'ask', 'clear-by'];

// Отказ готовности → slug. Порядок проверок — как в readiness.
function readySlug(r, rec, hook) {
  if (/not running/.test(r.reason)) return 'not-running';
  if (rec?.status === 'waiting' || hook?.state === 'question') return 'question';
  return 'not-idle';
}

export default async function sessionCompact(args, opts, env) {
  const w = where(env);
  const dry = opts['dry-run'] === true;
  const entry = { command: 'compact', id: null, name: null, host: null, text: TEXT };
  const minIdleRaw = opts['min-idle'];
  const minIdle = minIdleRaw === undefined ? null : Number(minIdleRaw);
  if (minIdleRaw !== undefined) entry.minIdle = minIdle;

  // Результат → строка журнала (кроме --dry-run) и сам результат.
  const line = (o) => {
    const { code, ok: _ok, text: _human, warnings, error, id: _id, name: _name, host: _host, ...rest } = o;
    return { ...entry, ...rest, ...(error ? { error } : {}), ...(warnings?.length ? { warnings } : {}), atSec: Math.floor(Date.now() / 1000) };
  };
  const log = (o) => {
    if (dry || !entry.id) return o;
    try {
      journal(w.log, line(o));
      return o;
    } catch (e) {
      return { ...o, warnings: [...(o.warnings ?? []), `journal ${w.log} not written: ${e.message}`] };
    }
  };
  const intend = (step) => {
    try {
      journal(w.log, line({ result: 'sending', step }));
      return null;
    } catch (e) {
      return { code: EXIT.REFUSED, ok: false, result: 'refused', reason: 'journal', error: `journal ${w.log} not writable (${e.message}); nothing typed` };
    }
  };
  const base = () => ({ id: entry.id, name: entry.name, host: entry.host });
  const refuse = (reason, error, extra = {}, code = EXIT.REFUSED) => log({ ...base(), code, ok: false, result: 'refused', reason, error, ...extra });
  const unknown = (step, error) => log({ ...base(), code: EXIT.UNKNOWN, ok: false, result: 'unknown', reason: 'unknown', step, error: `${error}; do not resend: look at the input box first` });

  if (args.length !== 1) return refuse('usage', USAGE);
  const foreign = FOREIGN.find((k) => opts[k] !== undefined);
  if (foreign) return refuse('usage', `--${foreign} is not an option of session compact; ${USAGE}`);
  if (minIdle !== null && !(Number.isFinite(minIdle) && minIdle >= 0 && /^\d+(\.\d+)?$/.test(minIdleRaw))) {
    return refuse('usage', `--min-idle needs minutes, a number >= 0: ${minIdleRaw}`);
  }

  let pic;
  try { pic = picture(env); } catch (e) { return refuse('state', e.message); }
  const res = resolveSession(args[0], { state: pic.state, agents: () => readAgents({ bin: pic.p.claudeBin }) });
  if (res.error === 'not found') return refuse('not-found', resolveError(args[0], res), {}, EXIT.NOT_FOUND);
  if (res.error) return refuse('ambiguous', resolveError(args[0], res), { candidates: res.candidates });
  const row = (pic.state.sessions ?? []).find((x) => x.id === res.id) ?? { id: res.id };
  const rec = registryRecord(w.sessionsDir, row.id);
  entry.id = row.id;
  entry.name = rec?.name ?? row.title ?? null;

  if (row.autoCompact === false) return refuse('disabled', `auto-compact is turned off for ${entry.name ?? row.id} (ccfzf --auto-compact ${row.id} on)`);

  const ready = () => {
    const r1 = registryRecord(w.sessionsDir, row.id);
    const hook = readJson(join(w.hookDir, `${row.id}.state.json`));
    const r = readiness(r1, hook);
    return r.ok ? r : { ok: false, slug: readySlug(r, r1, hook), reason: r.reason.replace(/^child\b/, 'session') };
  };
  const r0 = ready();
  if (!r0.ok) return refuse(r0.slug, r0.reason);

  if (minIdle !== null) {
    const cacheAt = Number(row.agent?.cacheAt) || 0;
    if (!cacheAt) return refuse('min-idle', 'no cacheAt for the session: idle time unknown, --min-idle cannot be checked');
    const idle = (Date.now() / 1000 - cacheAt) / 60;
    if (idle < minIdle) return refuse('min-idle', `idle ${idle.toFixed(1)} min since cacheAt, less than --min-idle ${minIdle}`);
  }

  const host = row.window?.host;
  if (!host) return refuse('no-window', 'session has no window', {}, EXIT.NOT_FOUND);
  entry.host = host;
  const tw = trackerWindow(pic.p.windowsDir, host, row.id);
  if (tw.error) return refuse('no-window', tw.error, {}, tw.code);
  const app = String(tw.win.app ?? '');
  if (!/wezterm/i.test(app)) return refuse('not-wezterm', `unsupported terminal: ${app || 'unknown (old tracker?)'}; only WezTerm windows are typed into`);
  const pid = tw.win.pid;
  if (!Number.isInteger(pid) || pid <= 0) return refuse('not-wezterm', `tracker of ${host} gives no pid for the window (old manager?)`);

  // 1. Проба: окно то, поле ввода на экране и пустое.
  const pr = call(w, tw.sshHost, 'probe', { pid });
  if (!pr.ok) return refuse('ssh', pr.error, {}, pr.code);
  const names = [rec?.name, row.title, row.window?.title].filter(Boolean);
  const pane = pickPane(pr.result.list, names);
  if (pane.error) return refuse('wrong-window', pane.error);
  const box0 = inputBox(pr.result.screen);
  if (box0 === null) return refuse('dialog', 'no input box on screen: a dialog may be open');
  // Любой текст в поле — человек здесь (анти-цель), даже `/compact`: пикер не
  // повторяет, и печатать поверх чужого незачем.
  if (box0) return refuse('input-busy', `input box is not empty: "${box0.slice(0, 80)}"`);
  if (dry) return { ...base(), code: EXIT.OK, ok: true, result: 'dry-run', pane: pane.pane, text: `would type ${TEXT} into ${entry.name ?? row.id} and press Enter` };

  // 2. Текст.
  const r1 = ready();
  if (!r1.ok) return refuse(r1.slug, r1.reason);
  const no1 = intend('text');
  if (no1) return no1;
  const tx = call(w, tw.sshHost, 'text', { pid, pane: pane.pane, text: TEXT });
  if (!tx.ok) {
    if (tx.code === EXIT.UNKNOWN) return unknown('text', tx.error);
    return refuse('ssh', tx.error, { step: 'text' }, tx.code);
  }
  if (!boxHasText(inputBox(tx.result.screen), TEXT)) {
    return refuse('not-landed', `${TEXT} is not seen in the input box; Enter not sent`, { step: 'enter', typed: true });
  }

  // 3. Enter: снова idle. Строка-намерение — маркер автокомпакта для хука.
  const r2 = ready();
  if (!r2.ok) return refuse(r2.slug, `${r2.reason}; Enter not sent, ${TEXT} stays in the input box`, { step: 'enter', typed: true });
  const no2 = intend('enter');
  if (no2) return no2;
  const en = call(w, tw.sshHost, 'enter', { pid, pane: pane.pane });
  if (!en.ok) {
    if (en.code === EXIT.UNKNOWN) return unknown('enter', en.error);
    return refuse('ssh', `${en.error}; ${TEXT} stays in the input box`, { step: 'enter', typed: true }, en.code);
  }
  const box2 = inputBox(en.result.screen);
  const warnings = box2 === '' ? [] : ['the input box is not empty after Enter'];
  return log({ ...base(), code: EXIT.OK, ok: true, result: 'ok', warnings, text: `${TEXT} sent to ${entry.name ?? row.id}` });
}
