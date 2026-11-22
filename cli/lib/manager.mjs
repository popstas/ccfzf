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

// {status, body} | {timeout: true} | {error} (соединение не случилось).
export async function post(url, path, body, { timeoutMs: ms = DEFAULT_TIMEOUT_MS } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = await fetch(`${url}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    const raw = await res.text();
    let parsed = null;
    try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = null; }
    return { status: res.status, body: parsed };
  } catch (e) {
    if (e.name === 'AbortError') return { timeout: true };
    const why = e.cause?.code || e.cause?.message || e.message;
    return { error: `manager unreachable: ${why}` };
  } finally {
    clearTimeout(timer);
  }
}

// Ответ менеджера → {code, error?} + тело. Отказ — `ok:false` в теле при любом
// коде ответа (429 throttled тоже несёт его); не-2xx без него — `HTTP <status>`.
export function answer(r) {
  if (r.timeout) return { code: EXIT.UNKNOWN, error: 'timeout' };
  if (r.error) return { code: EXIT.REFUSED, error: r.error };
  const body = r.body && typeof r.body === 'object' ? r.body : {};
  if (body.ok === false) return { code: EXIT.REFUSED, error: body.reason || body.error || 'refused by manager', body };
  if (r.status < 200 || r.status >= 300) return { code: EXIT.REFUSED, error: body.error || `HTTP ${r.status}`, body };
  return { code: EXIT.OK, body };
}
