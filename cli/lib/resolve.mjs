// <session> → sessionId. Порядок: точный id; уникальный префикс id (от 6
// символов); точное имя живой сессии (`claude agents --json`); точный title
// из `ccfzf --state`. Несколько совпадений на любом шаге — отказ со списком:
// тёзки в связке не редкость, а первая попавшаяся — чужое окно.

export const MIN_PREFIX = 6;

export function resolveSession(arg, { state, agents }) {
  if (typeof arg !== 'string' || !arg) return { error: 'not found' };
  const sessions = state?.sessions ?? [];
  const titleOf = new Map(sessions.map((s) => [s.id, s.title ?? null]));
  let live = null;
  const getAgents = () => {
    if (live === null) live = (typeof agents === 'function' ? agents() : agents) ?? [];
    return live;
  };
  const pick = (ids) => {
    const uniq = [...new Set(ids)];
    if (uniq.length === 1) return { id: uniq[0] };
    if (uniq.length > 1) {
      const nameOf = new Map((live ?? []).map((a) => [a.sessionId, a.name]));
      return { error: 'ambiguous', candidates: uniq.map((id) => ({ id, title: titleOf.get(id) ?? nameOf.get(id) ?? null })) };
    }
    return null;
  };

  const known = new Set(sessions.map((s) => s.id));
  if (known.has(arg)) return { id: arg };
  if (arg.length >= MIN_PREFIX) {
    const r = pick([...known].filter((id) => id.startsWith(arg)));
    if (r) return r;
  }
  const byName = getAgents().filter((a) => a.name === arg).map((a) => a.sessionId);
  if (byName.length === 0 && getAgents().some((a) => a.sessionId === arg)) return { id: arg };
  const r1 = pick(byName);
  if (r1) return r1;
  const r2 = pick(sessions.filter((s) => s.title === arg).map((s) => s.id));
  if (r2) return r2;
  return { error: 'not found' };
}

// Текст отказа для человека и агента: ambiguous — со списком кандидатов.
export function resolveError(arg, r) {
  if (r.error === 'ambiguous') {
    const list = r.candidates.map((c) => `${c.id} (${c.title ?? '?'})`).join(', ');
    return `ambiguous session "${arg}": ${list}`;
  }
  return `session not found: ${arg}`;
}
