// Разбор аргументов в манере старых скриптов скиллов (session-*, head-*): их
// вызовы и обёртки передают те же argv, поэтому правила — те же, вплоть до краёв.
// `--k v` — значение, если следующее слово непустое и не начинается с `--`;
// иначе `--k` — флаг true. `--k=v` не разбирается (ключ "k=v"), как и раньше.
// Слова, не съеденные флагом, — позиционные (их читает только head adopt).
// bool — флаги, которые значения не берут никогда (`--release x` → x позиционный).
export function parseLegacyArgs(argv, { bool = [] } = {}) {
  const flags = {};
  const positional = [];
  const noValue = new Set(bool);
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { positional.push(a); continue; }
    const k = a.slice(2);
    const n = argv[i + 1];
    flags[k] = !noValue.has(k) && n && !n.startsWith('--') ? argv[++i] : true;
  }
  return { flags, positional };
}
