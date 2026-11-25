// claude-wt waiting: живые сессии, которые чего-то ждут, и чем это снять.
// Только из того, что уже знают хуки и агрегатор (`ccfzf --state`) плюс
// состояние PR из gh. Правила — docs/claude-wt.md, раздел про waiting.
import { spawn } from 'node:child_process';
import { mkdirSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { EXIT } from '../out.mjs';
import { readJson } from '../sources.mjs';
import { picture } from './tree.mjs';

// Порядок вывода: то, что держит сессию прямо сейчас, — первым.
export const KINDS = ['permission', 'question', 'reply', 'pr'];

const HINTS = {
  permission: () => 'approve in its window',
  question: () => 'answer in its window',
  reply: () => 'reply in its chat',
  pr: (e) => `merge PR ${e.pr.url}`,
};

// Открытый PR перепроверяется не чаще раза в 10 минут; смерженный и закрытый не меняются.
const OPEN_TTL_SEC = 10 * 60;
const FINAL = new Set(['MERGED', 'CLOSED']);
const TEXT_MAX = 200;

// «Сводка — вопрос к человеку». Сводка — начало последнего ответа (хук берёт
// первые строки), поэтому вопрос в самом конце ответа отсюда не виден.
const ASKS = [
  /\?/,
  /(^|[^\p{L}])жду\s+(тво|ваш|ок|ответ|решени|подтвержд|команд|отмашк)/iu,
  /(тво[её]|ваше)\s+(решение|ок|подтверждение|ответ)/iu,
  /тво(его|их)\s+(решени|ок|ответ|подтвержд)/iu,
  /(^|[^\p{L}])(дай|дайте)\s+ок/iu,
  /\b(waiting for your|let me know|should i|do you want|want me to)\b/i,
];
export const asksHuman = (text) => Boolean(text) && ASKS.some((re) => re.test(text));

const clip = (s, n = TEXT_MAX) => {
  const t = String(s ?? '').replace(/\s+/g, ' ').trim();
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
};

export function ago(sec) {
  if (!Number.isFinite(sec) || sec < 0) return '?';
  if (sec < 60) return `${Math.floor(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

// Вид ожидания живой сессии без учёта PR: permission | question | reply | null.
// question — по непустому полю, а не по состоянию: хук кладёт вопрос уже на
// PreToolUse, когда состояние ещё active. Запрос разрешения — состояние question
// без текста вопроса (его текста нет нигде, только message уведомления).
export function promptKind(agent) {
  if (!agent) return null;
  if (agent.question) return 'question';
  if (agent.state === 'question') return 'permission';
  if ((agent.state === 'idle' || agent.state === 'review') && asksHuman(agent.summary || agent.lastSummary)) return 'reply';
  return null;
}

// Кандидаты: живые, и либо ждут ответа, либо закончили ход с pr_url.
// Работающая сессия с открытым PR не ждёт: она ещё сама его двигает.
export function candidates(sessions) {
  const out = [];
  for (const s of sessions) {
    if (!s.live) continue;
    const a = s.agent || null;
    const kind = promptKind(a);
    const prUrl = a && (kind || a.state !== 'active') ? a.pr_url || '' : '';
    if (kind || prUrl) out.push({ s, kind, prUrl });
  }
  return out;
}

// ---- PR: gh с таймаутом и кэшем ----

function cacheFile(env) {
  const dir = env.CLAUDE_WT_CACHE_DIR || join(env.XDG_CACHE_HOME || join(env.HOME || homedir(), '.cache'), 'claude-wt');
  return { dir, file: join(dir, 'prs.json') };
}

// Один вызов gh. Таймаут свой, со сносом группы процессов: ждать закрытия
// stdout у повисшего gh (или его детей) — значит повиснуть вместе с ним.
function ghState(bin, url, timeoutMs, env) {
  return new Promise((resolve) => {
    let out = '';
    let err = '';
    let done = false;
    const finish = (r) => { if (!done) { done = true; clearTimeout(timer); resolve(r); } };
    let p;
    try {
      p = spawn(bin, ['pr', 'view', url, '--json', 'state'], {
        detached: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...env, GH_PROMPT_DISABLED: '1', GH_NO_UPDATE_NOTIFIER: '1' },
      });
    } catch (e) {
      return finish({ state: 'unknown', reason: e.message });
    }
    const timer = setTimeout(() => {
      try { process.kill(-p.pid, 'SIGKILL'); } catch {}
      finish({ state: 'unknown', reason: 'gh timeout' });
    }, timeoutMs);
    p.unref();
    p.stdout.on('data', (d) => { out += d; });
    p.stderr.on('data', (d) => { err += d; });
    p.on('error', (e) => finish({ state: 'unknown', reason: e.code === 'ENOENT' ? 'gh not found' : e.message }));
    p.on('close', (code) => {
      if (code !== 0) return finish({ state: 'unknown', reason: clip(err.split('\n')[0] || `gh exit ${code}`, 120) });
      try {
        const state = JSON.parse(out).state;
        finish(state ? { state: String(state).toUpperCase() } : { state: 'unknown', reason: 'gh: no state' });
      } catch {
        finish({ state: 'unknown', reason: 'gh: bad JSON' });
      }
    });
  });
}

// url → {state, reason?, cached}. Неизвестное не кэшируется: в следующий раз спросим снова.
export async function prStates(urls, env, now = Date.now() / 1000) {
  const { dir, file } = cacheFile(env);
  const cache = readJson(file);
  const db = cache && typeof cache === 'object' && !Array.isArray(cache) ? cache : {};
  const out = new Map();
  const ask = [];
  for (const url of new Set(urls)) {
    const c = db[url];
    if (c && typeof c.state === 'string' && (FINAL.has(c.state) || now - Number(c.checkedAt || 0) < OPEN_TTL_SEC)) {
      out.set(url, { state: c.state, cached: true });
    } else ask.push(url);
  }
  if (ask.length) {
    const bin = env.GH_BIN || 'gh';
    const timeoutMs = Number(env.CLAUDE_WT_GH_TIMEOUT_MS) || 8000;
    const got = await Promise.all(ask.map((u) => ghState(bin, u, timeoutMs, env)));
    let dirty = false;
    ask.forEach((u, i) => {
      out.set(u, { ...got[i], cached: false });
      if (got[i].state !== 'unknown') { db[u] = { state: got[i].state, checkedAt: Math.floor(now) }; dirty = true; }
    });
    if (dirty) {
      try {
        mkdirSync(dir, { recursive: true });
        const tmp = `${file}.${process.pid}.tmp`;
        writeFileSync(tmp, JSON.stringify(db));
        renameSync(tmp, file);
      } catch {} // кэш — только ускорение
    }
  }
  return out;
}

// ---- сборка ----

export function entryOf({ s, kind, prUrl }, prs, now, rel) {
  const a = s.agent || {};
  const pr = prUrl ? { url: prUrl, ...(({ state, reason }) => ({ state, ...(reason ? { reason } : {}) }))(prs.get(prUrl) || { state: 'unknown' }) } : null;
  const prWaits = pr && pr.state !== 'MERGED' && pr.state !== 'CLOSED';
  const k = kind || (prWaits ? 'pr' : null);
  if (!k) return null;
  const since = Number(a.updated) || 0;
  const text = k === 'question' ? a.question
    : k === 'permission' ? a.message || 'permission request'
      : k === 'reply' ? a.summary || a.lastSummary
        : a.summary || a.lastSummary || pr.url;
  const e = {
    id: s.id,
    short: s.id.slice(0, 8),
    name: s.title ?? null,
    kind: k,
    since: since || null,
    ageSec: since ? Math.max(0, Math.floor(now - since)) : null,
    text: clip(text),
    hint: '',
    state: a.state || null,
    ...(pr ? { pr } : {}),
    own: rel.own.has(s.id),
    parent: rel.parent.get(s.id) ?? null,
  };
  e.hint = HINTS[k](e);
  if (k !== 'pr' && prWaits) e.hint += `; then merge PR ${pr.url}`;
  return e;
}

const order = (a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind) || (b.ageSec ?? -1) - (a.ageSec ?? -1);

// Дерево head → дети, только ветви, где кто-то ждёт; промежуточные head без
// ожидания стоят заголовками (waiting: false), иначе ребёнок упал бы в корень.
export function buildTree(entries, rel, titles) {
  const byId = new Map(entries.map((e) => [e.id, e]));
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) {
      const e = byId.get(id);
      nodes.set(id, e ? { ...e, waiting: true, children: [] } : { id, short: id.slice(0, 8), name: titles.get(id) ?? null, waiting: false, children: [] });
    }
    return nodes.get(id);
  };
  const roots = [];
  const attached = new Set();
  for (const e of entries) {
    let id = e.id;
    const seen = new Set();
    for (;;) {
      if (attached.has(id) || seen.has(id)) break;
      seen.add(id);
      attached.add(id);
      const parent = rel.parent.get(id);
      if (!parent || seen.has(parent)) { roots.push(node(id)); break; }
      node(parent).children.push(node(id));
      id = parent;
    }
  }
  const sortRec = (list) => { list.sort((a, b) => (a.waiting && b.waiting ? order(a, b) : a.waiting ? -1 : b.waiting ? 1 : 0)); list.forEach((n) => sortRec(n.children)); return list; };
  return sortRec(roots);
}

function line(e, depth) {
  const pad = '  '.repeat(depth);
  if (!e.waiting && e.waiting !== undefined) return `${pad}${e.name ?? '?'}  ${e.short}  (not waiting)`;
  const head = `${pad}${e.name ?? '?'}  ${e.short}  ${e.kind}  ${e.ageSec == null ? '?' : ago(e.ageSec)}  -> ${e.hint}`;
  return e.text ? `${head}\n${pad}    ${clip(e.text, 140)}` : head;
}

function human(entries, tree, live) {
  if (!entries.length) return `nothing is waiting (${live} live sessions)`;
  const counts = KINDS.map((k) => [k, entries.filter((e) => e.kind === k).length]).filter(([, n]) => n);
  const lines = [`waiting: ${entries.length} of ${live} live (${counts.map(([k, n]) => `${k} ${n}`).join(', ')})`];
  if (tree) {
    const walk = (list, d) => list.forEach((n) => { lines.push(line(n, d)); walk(n.children, d + 1); });
    walk(tree, 0);
  } else for (const e of entries) lines.push(line(e, 0));
  const unknown = entries.filter((e) => e.pr?.state === 'unknown');
  if (unknown.length) lines.push(`(PR state unknown for ${unknown.length}: ${[...new Set(unknown.map((e) => e.pr.reason).filter(Boolean))].join('; ') || 'gh did not answer'})`);
  return lines.join('\n');
}

export default async function waiting(_args, opts, env) {
  const { state, sessions: rows, own } = picture(env);
  const all = state.sessions ?? [];
  const now = Date.now() / 1000;
  const rel = { own, parent: new Map(rows.filter((r) => r.parent).map((r) => [r.id, r.parent])) };
  const titles = new Map(rows.map((r) => [r.id, r.title]));
  const cands = candidates(all);
  const prs = await prStates(cands.map((c) => c.prUrl).filter(Boolean), env, now);
  const entries = cands.map((c) => entryOf(c, prs, now, rel)).filter(Boolean).sort(order);
  const live = all.filter((s) => s.live).length;
  const tree = opts.tree ? buildTree(entries, rel, titles) : null;
  return { code: EXIT.OK, live, waiting: entries, ...(tree ? { tree } : {}), text: human(entries, tree, live) };
}
