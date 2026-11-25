// Чистые части `claude-wt session type`: проверка текста и готовности ребёнка,
// разбор экрана (поле ввода Claude Code), сборка скрипта PowerShell для nb,
// разбор его ответа, строка журнала. Сеть и файлы — в commands/session-type.mjs.
import { appendFileSync, mkdirSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { readJson } from './sources.mjs';

export const MAX_TEXT = 16000;

// Управляющие символы, кроме \n и \t, не пропускаются: ESC закрыл бы вставку
// (`\e[201~`) и дальше текст шёл бы как нажатия клавиш, \r — это Enter.
// DEL и C1 — туда же: терминал читает их как клавиши.
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/;

export function checkText(text) {
  if (typeof text !== 'string' || !text.trim()) return 'missing <text>';
  if (text.length > MAX_TEXT) return `text too long: ${text.length} chars, max ${MAX_TEXT}`;
  const m = text.match(CONTROL);
  if (m) return `text has a control character U+${m[0].charCodeAt(0).toString(16).padStart(4, '0').toUpperCase()}; only \\n and \\t are allowed`;
  return null;
}

// --- готовность ребёнка: реестр Claude Code и state.json хуков ---

// Запись реестра ~/.claude/sessions/<pid>.json сессии id: самая свежая.
export function registryRecord(sessionsDir, id) {
  let files = [];
  try { files = readdirSync(sessionsDir).filter((f) => f.endsWith('.json')); } catch {}
  let best = null;
  for (const f of files) {
    const r = readJson(join(sessionsDir, f));
    if (r?.sessionId !== id) continue;
    if (!best || (Number(r.updatedAt) || 0) > (Number(best.updatedAt) || 0)) best = r;
  }
  return best;
}

const alive = (pid) => {
  if (!Number.isInteger(pid) || pid <= 0) return true; // pid не назван — судить не по чему
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; }
};

// Печатать можно только в поле ввода (решение Стаса 25.11): ребёнок обязан
// быть idle. busy — диалог разрешения может открыться в любой миг, и текст уйдёт
// в него; waiting — диалог уже открыт (`waitingFor`: approve …, input needed,
// dialog open). `question` в state.json хуков — второй источник того же.
export function readiness(rec, hook, { isAlive = alive } = {}) {
  if (!rec) return { ok: false, reason: 'child is not running (no registry record)' };
  if (!isAlive(rec.pid)) return { ok: false, reason: `child is not running (pid ${rec.pid} is gone)` };
  if (rec.status === 'waiting') {
    return { ok: false, reason: `child is waiting on a dialog${rec.waitingFor ? `: ${rec.waitingFor}` : ''}; only the input box is typed into` };
  }
  if (rec.status !== 'idle') {
    return { ok: false, reason: `child is ${rec.status || 'in an unknown state'}, not idle: a permission dialog may open any moment` };
  }
  if (hook?.state === 'question') return { ok: false, reason: 'child is on a question or permission prompt (hook state: question)' };
  return { ok: true };
}

// --- заголовки ---

// Заголовок панели — `<глиф> <имя>` (`✳ .waiting`, `◐ .session-type`), у
// строки агрегатора — `└имя`. Снимается всё, что до первой буквы, цифры,
// точки, `_` или `-`.
export const normTitle = (t) => String(t ?? '').replace(/^[^\p{L}\p{N}._-]+/u, '').trim();

export function titleMatches(paneTitle, names) {
  const t = normTitle(paneTitle);
  return Boolean(t) && names.map(normTitle).filter(Boolean).includes(t);
}

// Панели из `wezterm cli list --format json`. Окно claude-wt — одна панель.
export function pickPane(listJson, names) {
  let list;
  try { list = JSON.parse(listJson); } catch { return { error: 'wezterm cli list: bad JSON' }; }
  if (!Array.isArray(list) || !list.length) return { error: 'wezterm window has no panes' };
  if (list.length > 1) return { error: `wezterm window has ${list.length} panes; only a single-pane window is typed into` };
  const p = list[0];
  if (!Number.isInteger(p?.pane_id)) return { error: 'wezterm cli list: no pane_id' };
  if (!titleMatches(p.title, names)) {
    return { error: `pane title "${p.title ?? ''}" is not the child (${names.filter(Boolean).join(' / ')}): wrong window` };
  }
  return { pane: p.pane_id, title: p.title };
}

// --- поле ввода на экране ---

// Верхняя линия несёт имя сессии справа: `──── .session-type ─`.
const RULE = /^\s*─{8,}(?:\s+\S.*\s+─+)?\s*$/;
const PROMPT = /^\s*❯[\s\u00a0]?/;

// Поле ввода Claude Code: строка `❯ …` и её продолжения между двумя линиями
// `────`, последняя такая пара на экране. Нет поля — null (на экране диалог).
export function inputBox(screen) {
  const lines = String(screen ?? '').split(/\r?\n/).map((l) => l.replace(/\r$/, ''));
  for (let end = lines.length - 1; end > 0; end--) {
    if (!RULE.test(lines[end])) continue;
    let start = end - 1;
    while (start >= 0 && !RULE.test(lines[start])) start--;
    if (start < 0) return null;
    const body = lines.slice(start + 1, end);
    if (!body.length || !PROMPT.test(body[0])) { end = start + 1; continue; }
    const text = body.map((l, i) => (i === 0 ? l.replace(PROMPT, '') : l)).join('\n').replace(/\u00a0/g, ' ');
    return text.replace(/\s+$/, '').replace(/^\s+/, '');
  }
  return null;
}

const squash = (s) => String(s).replace(/[\s\u00a0]+/g, '');

// В поле стоит ровно этот текст (не свёрнутая вставка): прошлый вызов успел
// его напечатать. Повтор тогда не печатает второй раз.
export const boxIsText = (box, text) => typeof box === 'string' && Boolean(squash(text)) && squash(box) === squash(text);

// Встал ли текст в поле: хвост текста (без пробелов — перенос строк в поле
// режет их) или свёрнутая вставка `[Pasted text #N …]`.
export function boxHasText(box, text) {
  if (box === null || box === undefined) return false;
  if (/\[Pasted text #\d+/.test(box)) return true;
  const tail = squash(text).slice(-30);
  return Boolean(tail) && squash(box).includes(tail);
}

// --- скрипт для nb ---

// Одна панель окна WezTerm, сокет — gui-sock-<pid> процесса окна. Каждый вызов
// `wezterm cli` несёт --no-auto-start: без него cli, не найдя сокета, поднимает
// wezterm-mux-server, и тот остаётся жить на машине (проба 25.11).
// Режимы: probe — list и экран; text — вставка текста (stdin wezterm, байты
// UTF-8 как есть: ни кавычек, ни перевода строки PowerShell); enter — `\r`
// с --no-paste. После отправки — строка SENT, затем экран: SENT без JSON
// значит «ушло, а что на экране — неизвестно».
export const SCRIPT = String.raw`$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
function Done($o) { [Console]::Out.WriteLine((ConvertTo-Json -InputObject $o -Compress -Depth 4)); exit 0 }
try {
  $p = [Console]::In.ReadToEnd() | ConvertFrom-Json
  $sock = Join-Path $env:USERPROFILE (".local\share\wezterm\gui-sock-" + [int]$p.pid)
  if (-not (Test-Path -LiteralPath $sock)) { Done @{ ok = $false; step = 'socket'; reason = "no wezterm socket for pid $([int]$p.pid)" } }
  $exe = Join-Path $env:ProgramFiles 'WezTerm\wezterm.exe'
  if (-not (Test-Path -LiteralPath $exe)) { $exe = 'wezterm.exe' }
  function Wez([string[]]$a, [byte[]]$in) {
    $si = New-Object Diagnostics.ProcessStartInfo $exe
    $si.Arguments = ((@('cli', '--no-auto-start') + $a) -join ' ')
    $si.UseShellExecute = $false
    $si.RedirectStandardInput = $true
    $si.RedirectStandardOutput = $true
    $si.RedirectStandardError = $true
    $si.StandardOutputEncoding = [Text.Encoding]::UTF8
    $si.StandardErrorEncoding = [Text.Encoding]::UTF8
    $si.EnvironmentVariables['WEZTERM_UNIX_SOCKET'] = $sock
    $pr = [Diagnostics.Process]::Start($si)
    if ($null -ne $in) { $pr.StandardInput.BaseStream.Write($in, 0, $in.Length) }
    $pr.StandardInput.Close()
    $o = $pr.StandardOutput.ReadToEndAsync()
    $e = $pr.StandardError.ReadToEndAsync()
    if (-not $pr.WaitForExit(15000)) { try { $pr.Kill() } catch {}; throw ('wezterm cli ' + $a[0] + ' timed out') }
    @{ code = $pr.ExitCode; out = $o.Result; err = $e.Result.Trim() }
  }
  function Screen([int]$pane) {
    $g = Wez @('get-text', '--pane-id', [string]$pane) $null
    if ($g.code -ne 0) { return $null }
    $g.out
  }
  if ($p.mode -eq 'probe') {
    $l = Wez @('list', '--format', 'json') $null
    if ($l.code -ne 0) { Done @{ ok = $false; step = 'list'; reason = ('wezterm cli list: ' + $l.err) } }
    $ids = [regex]::Matches($l.out, '"pane_id"\s*:\s*(\d+)')
    $screen = $null
    if ($ids.Count -eq 1) { $screen = Screen ([int]$ids[0].Groups[1].Value) }
    Done @{ ok = $true; list = $l.out; screen = $screen }
  }
  $pane = [int]$p.pane
  if ($p.mode -eq 'text') { $bytes = [Convert]::FromBase64String([string]$p.text); $flags = @() }
  elseif ($p.mode -eq 'enter') { $bytes = [byte[]](13); $flags = @('--no-paste') }
  else { Done @{ ok = $false; step = 'mode'; reason = ('unknown mode ' + $p.mode) } }
  $s = Wez (@('send-text', '--pane-id', [string]$pane) + $flags) $bytes
  if ($s.code -ne 0) { Done @{ ok = $false; step = 'send'; reason = ('wezterm cli send-text: ' + $s.err) } }
  [Console]::Out.WriteLine('SENT')
  Start-Sleep -Milliseconds ([int]$p.settleMs)
  Done @{ ok = $true; sent = $true; screen = (Screen $pane) }
} catch {
  Done @{ ok = $false; step = 'error'; reason = $_.Exception.Message }
}
`;

// -EncodedCommand: base64 от UTF-16LE. Скрипт едет в командной строке ssh, а
// данные (и текст) — в stdin: им не нужно переживать кавычки двух шеллов.
export const encodeScript = (script = SCRIPT) => Buffer.from(script, 'utf16le').toString('base64');

export const SETTLE_MS = { text: 500, enter: 800 };

export function payload(mode, { pid, pane, text } = {}) {
  const o = { mode, pid };
  if (mode !== 'probe') {
    o.pane = pane;
    o.settleMs = SETTLE_MS[mode] ?? 500;
  }
  if (mode === 'text') o.text = Buffer.from(text, 'utf8').toString('base64');
  return JSON.stringify(o);
}

// Ответ скрипта: последняя JSON-строка stdout и была ли строка SENT.
export function parseOut(stdout) {
  const lines = String(stdout ?? '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const sent = lines.includes('SENT');
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!lines[i].startsWith('{')) continue;
    try { return { sent, result: JSON.parse(lines[i]) }; } catch {}
  }
  return { sent, result: null };
}

// ssh не дошёл до машины: текст точно не ушёл.
const NOT_CONNECTED = /Could not resolve hostname|Connection refused|Connection timed out|No route to host|Network is unreachable|Permission denied|Host key verification failed|Operation timed out/i;
export const sshNotConnected = (status, stderr) => status === 255 && NOT_CONNECTED.test(String(stderr ?? ''));

// --- журнал ---

// Одна JSON-строка на попытку, отказы и «неизвестно» тоже: Стас видит, что
// ушло от его имени. --check ничего не печатает и в журнал не пишется.
export function journal(file, entry, now = new Date()) {
  mkdirSync(dirname(file), { recursive: true });
  appendFileSync(file, `${JSON.stringify({ at: now.toISOString(), ...entry })}\n`);
}
