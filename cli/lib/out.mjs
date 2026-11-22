// Вывод claude-wt: один результат на вызов, код выхода по смыслу.
// result = {code, error?, warnings?, text?, ...поля}. `text` — для человека,
// в --json не попадает; error и warnings всегда дублируются в stderr, чтобы
// агент видел причину и без разбора JSON.

export const EXIT = { OK: 0, REFUSED: 1, NOT_FOUND: 2, UNKNOWN: 3 };

function summary(result) {
  const { code, text, warnings, error, ...rest } = result;
  return Object.keys(rest).length ? JSON.stringify(rest, null, 2) : '';
}

export function emit(result, { json = false } = {}) {
  // Без целого code — ошибка программы: отказ, а не «исход неизвестен, повтори».
  const code = Number.isInteger(result.code) ? result.code : EXIT.REFUSED;
  for (const w of result.warnings ?? []) process.stderr.write(`claude-wt: warning: ${w}\n`);
  if (result.error) process.stderr.write(`claude-wt: ${result.error}\n`);
  if (json) {
    const { text, ...rest } = result;
    process.stdout.write(`${JSON.stringify({ ...rest, code })}\n`);
  } else if (!result.error) {
    const s = result.text ?? summary(result);
    if (s) process.stdout.write(`${s}\n`);
  }
  return code;
}
