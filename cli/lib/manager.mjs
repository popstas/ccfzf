// Менеджер окон той машины, где стоит окно: адрес — из файла её трекера
// (`http.host`/`http.port`), запрос — POST с таймаутом. Транспорт только http:
// у MQTT нет ответа, а CLI обязан сказать, что вышло.
import { EXIT } from './out.mjs';

export const DEFAULT_TIMEOUT_MS = 5000;

export const timeoutMs = (env = process.env) => {
  const v = Number(env.CLAUDE_WT_TIMEOUT_MS);
  return Number.isFinite(v) && v > 0 ? v : DEFAULT_TIMEOUT_MS;
};

// --url перебивает всё; иначе трекер машины окна (или --machine).
export function managerFor({ host, trackers, url, machine }) {
  if (typeof url === 'string' && url) return { url: url.replace(/\/+$/, ''), host: machine ?? host ?? null, source: '--url' };
  const want = machine ?? host;
  if (!want) return { error: 'no machine: the window does not name its host (pass --machine or --url)', code: EXIT.NOT_FOUND };
  const mine = trackers.filter((t) => t.host === want).sort((a, b) => (b.generated ?? 0) - (a.generated ?? 0));
  if (!mine.length) return { error: `no tracker for ${want}`, code: EXIT.NOT_FOUND };
  const t = mine.find((x) => x.http) ?? mine[0];
  if (!t.http) return { error: `no http manager for ${want}`, code: EXIT.REFUSED };
  if (!t.fresh) return { error: `tracker stale: ${t.file}`, code: EXIT.REFUSED };
  return { url: `http://${t.http.host}:${t.http.port}`, host: want, source: t.file };
}

// Ошибки, при которых запрос до менеджера точно не дошёл: соединения не было.
// Ошибка без сетевого кода (плохой адрес или порт) — тоже до отправки.
// Остальные коды (сброс, обрыв сокета) и обрыв на чтении ответа — запрос мог
// уже исполняться: исход неизвестен, повторять restore нельзя.
const NOT_CONNECTED = new Set(['ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN', 'EAI_NONAME', 'EHOSTUNREACH', 'ENETUNREACH', 'EADDRNOTAVAIL', 'UND_ERR_CONNECT_TIMEOUT']);

// {status, body} | {timeout: true} | {error} (соединение не случилось) |
// {lost} (соединение было, ответа нет — исход неизвестен).
export async function post(url, path, body, { timeoutMs: ms = DEFAULT_TIMEOUT_MS } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  let res;
  try {
    res = await fetch(`${url}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') return { timeout: true };
    const code = e.cause?.code || e.code;
    const why = code || e.cause?.message || e.message;
    if (!code || NOT_CONNECTED.has(code)) return { error: `manager unreachable: ${why}` };
    return { lost: `connection lost after the request was sent: ${why}` };
  }
  try {
    const raw = await res.text();
    let parsed = null;
    try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = null; }
    return { status: res.status, body: parsed };
  } catch (e) {
    if (e.name === 'AbortError') return { timeout: true };
    return { lost: `answer cut off (HTTP ${res.status}): ${e.cause?.code || e.message}` };
  } finally {
    clearTimeout(timer);
  }
}

// Ответ менеджера → {code, error?} + тело. Отказ — `ok:false` в теле при любом
// коде ответа (429 throttled тоже несёт его); не-2xx без него — `HTTP <status>`.
// Успех — только 2xx с `ok: true` (его шлёт и старый менеджер): чужой ответ
// на порту (прокси, занятый порт) не выдаётся за сделанное.
export function answer(r) {
  if (r.timeout) return { code: EXIT.UNKNOWN, error: 'timeout' };
  if (r.lost) return { code: EXIT.UNKNOWN, error: `outcome unknown: ${r.lost}` };
  if (r.error) return { code: EXIT.REFUSED, error: r.error };
  const body = r.body && typeof r.body === 'object' && !Array.isArray(r.body) ? r.body : {};
  if (body.ok === false) return { code: EXIT.REFUSED, error: body.reason || body.error || 'refused by manager', body };
  if (r.status < 200 || r.status >= 300) return { code: EXIT.REFUSED, error: body.error || `HTTP ${r.status}`, body };
  if (body.ok !== true) return { code: EXIT.REFUSED, error: `unexpected answer from manager (HTTP ${r.status})`, body };
  return { code: EXIT.OK, body };
}
