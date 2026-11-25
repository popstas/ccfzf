// claude-wt session type <child> <text> [--enter] | --check: напечатать текст в
// поле ввода дочерней сессии — так, как набрал бы его Стас (решения Стаса 25.11).
//
// Только потомкам вызывающей (не ей самой), поднятым session spawn — не
// усыновлённым head adopt ни на одном звене, — и только в поле ввода: ребёнок
// обязан быть idle по реестру Claude Code, без `question` в state.json хуков,
// а на экране — с пустым полем `❯`. busy, открытый диалог (status waiting),
// непустое поле — отказ. Окно — WezTerm: печать идёт по ssh на машину окна
// (`wezterm cli send-text` в сокет gui-sock-<pid> его процесса; pid и app —
// из файла трекера). Других терминалов нет: wt — отказ `unsupported terminal`.
//
// Текст вставляется (bracketed paste: переносы строк не отправляют его раньше
// времени), Enter — отдельно и только с --enter, после повторной проверки
// реестра и того, что текст встал в поле. Каждая попытка — строка в
// ~/.ccfzf/typed.jsonl: строка-намерение (`sending`) перед каждой отправкой и
// строка исхода. --check ничего не печатает: показывает поле ввода.
//
// Код 3 — исход неизвестен (ssh оборвался после отправки). Повторять вслепую
// нельзя — текст удвоится: сначала --check, по полю ввода решать. Поле пустое
// или в нём ровно этот текст — повтор той же команды безопасен: стоящий в поле
// текст второй раз не печатается, с --enter нажимается только Enter.
import { spawnSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { EXIT } from '../out.mjs';
import { context, ownTarget, offMachine } from '../act.mjs';
import { readJson } from '../sources.mjs';
import {
  checkText, registryRecord, readiness, pickPane, inputBox, boxHasText, boxIsText,
  sshCommand, stdinFor, payload, parseOut, sshNotConnected, journal,
} from '../type.mjs';

const SSH_TIMEOUT_MS = 45000;
const lc = (x) => String(x ?? '').toLowerCase();

function where(env) {
  const home = env.HOME;
  return {
    sessionsDir: env.CLAUDE_WT_SESSIONS_DIR || join(home, '.claude', 'sessions'),
    hookDir: env.CLAUDE_WT_STATE_DIR || join(home, '.claude', 'claude-wt'),
    log: env.CLAUDE_WT_TYPED_LOG || join(home, '.ccfzf', 'typed.jsonl'),
    ssh: env.CLAUDE_WT_SSH || 'ssh',
  };
}

// Запись окна сессии в файле трекера её машины: {pid, app, title} и куда ssh.
function trackerWindow(windowsDir, host, id) {
  let files = [];
  try { files = readdirSync(windowsDir).filter((f) => f.endsWith('.json')); } catch {}
  let best = null;
  for (const f of files) {
    const o = readJson(join(windowsDir, f));
    if (!o || typeof o !== 'object') continue;
    if (lc(o.host ?? f.replace(/\.json$/, '')) !== lc(host)) continue;
    if (!best || (Number(o.generated) || 0) > (Number(best.generated) || 0)) best = o;
  }
  if (!best) return { error: `no tracker for ${host}`, code: EXIT.NOT_FOUND };
  const w = best.windows?.[id];
  if (!w || typeof w !== 'object') return { error: `tracker of ${host} has no window of this session`, code: EXIT.NOT_FOUND };
  return { win: w, sshHost: best.http?.host || best.host || host };
}

// Первое звено с adopted: true по пути ребёнок → … → вызывающая, иначе null.
export function adoptedLink(children, id, caller) {
  const byId = new Map(children.map((c) => [c.sessionId, c]));
  const seen = new Set();
  for (let cur = id; cur && cur !== caller && !seen.has(cur); cur = byId.get(cur)?.headId) {
    seen.add(cur);
    if (byId.get(cur)?.adopted === true) return cur;
  }
  return null;
}

function ssh(bin, host, body) {
  const r = spawnSync(bin, [
    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host,
    sshCommand(),
  ], { input: stdinFor(body), encoding: 'utf8', timeout: SSH_TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024 });
  const out = parseOut(r.stdout);
  return { status: r.status, stderr: r.stderr ?? '', timedOut: r.error?.code === 'ETIMEDOUT', spawnError: r.error && r.error.code !== 'ETIMEDOUT' ? r.error.message : null, ...out };
}

// Вызов скрипта → {ok, result} | {code, error, sent}. sent: ушло ли что-то в панель.
function call(w, host, mode, args) {
  const r = ssh(w.ssh, host, payload(mode, args));
  const sends = mode !== 'probe';
  if (r.result?.ok === true) return { ok: true, result: r.result, sent: Boolean(r.result.sent) };
  // Ушло, а потом сломалось (get-text завис, ssh оборвался): не отказ — исход неизвестен.
  if (sends && r.sent) return { code: EXIT.UNKNOWN, error: `${host}: sent, but ${r.result?.reason || 'no answer after it'}${r.timedOut ? ' (timeout)' : ''}`, sent: true };
  if (r.result && r.result.ok === false) {
    return { code: EXIT.REFUSED, error: `${host}: ${r.result.reason || r.result.step || 'refused'}`, sent: false };
  }
  if (r.spawnError) return { code: EXIT.REFUSED, error: `ssh: ${r.spawnError}`, sent: false };
  if (!sends) return { code: EXIT.REFUSED, error: `ssh ${host}: ${r.timedOut ? 'timeout' : (r.stderr.trim() || `exit ${r.status}`)}`, sent: false };
  if (sshNotConnected(r.status, r.stderr)) return { code: EXIT.REFUSED, error: `ssh ${host}: ${r.stderr.trim()}`, sent: false };
  return { code: EXIT.UNKNOWN, error: `ssh ${host}: ${r.timedOut ? 'timeout' : (r.stderr.trim() || `exit ${r.status}`)}; outcome unknown`, sent: null };
}

export default async function sessionType(args, opts, env) {
  const w = where(env);
  const check = opts.check === true;
  const enter = opts.enter === true;
  const childArg = args[0];
  const text = args[1];
  const entry = { headId: env.CLAUDE_CODE_SESSION_ID ?? null, child: childArg ?? null };
  // Результат команды → строка журнала (кроме --check) и сам результат.
  // `text` результата — для человека; в журнал идёт напечатанный текст.
  const line = (o) => {
    const { code, text: _human, warnings, error, id, title, ...rest } = o;
    return {
      ...entry, text: text ?? null, enter, ...rest,
      ...(error ? { reason: error } : {}), ...(warnings?.length ? { warnings } : {}),
    };
  };
  // Исход пишется после действия; не записался — результат тот же, с
  // предупреждением: печать уже случилась, и отказом её не назвать.
  const log = (o) => {
    if (check) return o;
    try {
      journal(w.log, line(o));
      return o;
    } catch (e) {
      return { ...o, warnings: [...(o.warnings ?? []), `journal ${w.log} not written: ${e.message}`] };
    }
  };
  // Строка-намерение — до каждой отправки в панель: CLI могут убить между
  // отправкой и исходом, а Стас должен видеть всё, что ушло от его имени. Не
  // записалась — ничего не отправляется.
  const intend = (step, extra = {}) => {
    try {
      journal(w.log, line({ result: 'sending', step, ...extra }));
      return null;
    } catch (e) {
      return { code: EXIT.REFUSED, error: `journal ${w.log} not writable (${e.message}); nothing typed` };
    }
  };
  const refuse = (error, extra = {}, code = EXIT.REFUSED) => log({ code, result: 'refused', error, ...extra });

  if (check && enter) return { code: EXIT.REFUSED, error: '--check and --enter do not go together' };
  if (check ? args.length !== 1 : args.length !== 2) {
    return { code: EXIT.REFUSED, error: check ? 'usage: session type <child> --check' : 'usage: session type <child> <text> [--enter]' };
  }
  if (opts.url !== undefined) return refuse('session type goes over ssh to the window\'s machine; --url is not used');

  const ctx = context(env);
  if (ctx.fail) return refuse(ctx.fail.error, {}, ctx.fail.code);
  const me = registryRecord(w.sessionsDir, ctx.pic.caller);
  entry.headName = me?.name ?? ctx.pic.sessions.find((s) => s.id === ctx.pic.caller)?.title ?? null;
  if (!check) {
    const bad = checkText(text);
    if (bad) return refuse(bad);
  }
  const t = ownTarget(childArg, ctx.pic);
  if (t.fail) return refuse(t.fail.error, {}, t.fail.code);
  const s = t.session;
  entry.childId = s.id;
  if (s.id === ctx.pic.caller) return refuse('only child sessions are typed into, not this session itself');
  // Только дети, поднятые session spawn (решение Стаса 25.11, 1a): head adopt
  // берёт в дети любую живую сессию, и печать «от Стаса» достала бы до любой.
  // Проверяется вся цепочка от ребёнка до вызывающей: усыновлённое звено где
  // угодно — отказ.
  const via = adoptedLink(ctx.pic.children, s.id, ctx.pic.caller);
  if (via) {
    return refuse(via === s.id
      ? 'child was adopted (head adopt), not opened by session spawn: only spawned children are typed into'
      : `child descends from an adopted session ${via} (head adopt): only spawned children are typed into`);
  }

  const rec = registryRecord(w.sessionsDir, s.id);
  entry.childName = rec?.name ?? s.title;
  const names = [rec?.name, s.title, s.window?.title].filter(Boolean);
  const base = { id: s.id, title: s.title };

  const ready = () => readiness(registryRecord(w.sessionsDir, s.id), readJson(join(w.hookDir, `${s.id}.state.json`)));
  if (!check) {
    const r0 = ready();
    if (!r0.ok) return refuse(r0.reason, base);
  }

  const host = s.window?.host;
  if (!host) return refuse('child has no window', base, EXIT.NOT_FOUND);
  entry.host = host;
  const off = offMachine(host, [], { machine: opts.machine });
  if (off) return refuse(off, base);
  const tw = trackerWindow(ctx.pic.p.windowsDir, host, s.id);
  if (tw.error) return refuse(tw.error, base, tw.code);
  const app = String(tw.win.app ?? '');
  if (!/wezterm/i.test(app)) return refuse(`unsupported terminal: ${app || 'unknown (old tracker?)'}; only WezTerm windows are typed into`, base);
  const pid = tw.win.pid;
  if (!Number.isInteger(pid) || pid <= 0) return refuse(`tracker of ${host} gives no pid for the window (old manager?)`, base);

  // 1. Проба: окно то, поле ввода на экране и пустое.
  const pr = call(w, tw.sshHost, 'probe', { pid });
  if (!pr.ok) return refuse(pr.error, base, pr.code);
  const pane = pickPane(pr.result.list, names);
  if (pane.error) return refuse(pane.error, base);
  const box0 = inputBox(pr.result.screen);
  if (check) {
    return {
      ...base, code: EXIT.OK, host, pane: pane.pane, input: box0,
      text: box0 === null ? 'no input box on screen (a dialog may be open)' : (box0 ? `input: ${box0}` : 'input is empty'),
    };
  }
  if (box0 === null) return refuse('no input box on screen: a dialog may be open', base);
  // Ровно этот текст уже в поле — повтор после кода 3: второй раз не печатается.
  const already = boxIsText(box0, text);
  if (box0 && !already) return refuse(`child's input box is not empty: "${box0.slice(0, 80)}"`, base);

  // 2. Текст.
  let landed = already;
  if (already) {
    if (!enter) return log({ ...base, code: EXIT.OK, result: 'ok', typed: false, already: true, entered: false, text: `already in the input box of ${entry.childName}` });
  } else {
    const r1 = ready();
    if (!r1.ok) return refuse(r1.reason, base);
    const no1 = intend('text', base);
    if (no1) return no1;
    const tx = call(w, tw.sshHost, 'text', { pid, pane: pane.pane, text });
    if (!tx.ok) {
      if (tx.code === EXIT.UNKNOWN) return log({ ...base, code: EXIT.UNKNOWN, result: 'unknown', step: 'text', error: `${tx.error}; run session type ${s.id} --check before anything else` });
      return refuse(tx.error, { ...base, step: 'text' }, tx.code);
    }
    landed = boxHasText(inputBox(tx.result.screen), text);
    if (!enter) {
      const warnings = landed ? [] : ['the text is not seen in the input box; check with --check'];
      return log({ ...base, code: EXIT.OK, result: 'ok', typed: true, entered: false, warnings, text: `typed into ${entry.childName}` });
    }
  }
  const typed = !already;

  // 3. Enter: снова idle, и текст стоит в поле.
  if (!landed) return refuse('the text is not seen in the input box; Enter not sent (look with --check)', { ...base, typed, step: 'enter' });
  const r2 = ready();
  if (!r2.ok) return refuse(`${r2.reason}; Enter not sent, the text stays in the input box`, { ...base, typed, step: 'enter' });
  const no2 = intend('enter', { ...base, typed });
  if (no2) return no2;
  const en = call(w, tw.sshHost, 'enter', { pid, pane: pane.pane });
  if (!en.ok) {
    if (en.code === EXIT.UNKNOWN) return log({ ...base, code: EXIT.UNKNOWN, result: 'unknown', step: 'enter', typed, error: `${en.error}; run session type ${s.id} --check before anything else` });
    return refuse(`${en.error}; the text stays in the input box`, { ...base, typed, step: 'enter' }, en.code);
  }
  const box2 = inputBox(en.result.screen);
  const warnings = box2 === '' ? [] : ['the input box is not empty after Enter; check with --check'];
  return log({ ...base, code: EXIT.OK, result: 'ok', typed, ...(already ? { already: true } : {}), entered: true, warnings, text: `typed into ${entry.childName} and sent` });
}
