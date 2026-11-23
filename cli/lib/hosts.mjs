// Машины окон сессии и худший код из исходов на них — общее у команд,
// действующих на все окна сессии сразу (session unread/seen, window icon/badge).
import { EXIT } from './out.mjs';

const lc = (x) => String(x ?? '').toLowerCase();

// Машины окон сессии, без повторов, в порядке ответа агрегатора.
export function windowHosts(state, id) {
  const s = (state.sessions ?? []).find((x) => x.id === id) ?? {};
  const wins = Array.isArray(s.windows) && s.windows.length ? s.windows : (s.window ? [s.window] : []);
  const out = [];
  for (const w of wins) {
    const h = w?.host;
    if (h && !out.some((x) => lc(x) === lc(h))) out.push(h);
  }
  return out;
}

// Худший код из исходов: отказ и «неизвестно» важнее «не найдено», успех — последним.
const RANK = [EXIT.UNKNOWN, EXIT.REFUSED, EXIT.NOT_FOUND, EXIT.OK];
export const worst = (codes) => RANK.find((c) => codes.includes(c)) ?? EXIT.OK;
