// Каркас claude-wt: вывод, коды выхода, справка.
// Запуск: node --test tests/cli/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EXIT, emit } from '../../cli/lib/out.mjs';
import { runCli } from './helpers.mjs';

// Подменяем stdout/stderr, чтобы увидеть, что и куда напечатал emit.
function capture(fn) {
  const out = [];
  const err = [];
  const so = process.stdout.write;
  const se = process.stderr.write;
  process.stdout.write = (s) => { out.push(String(s)); return true; };
  process.stderr.write = (s) => { err.push(String(s)); return true; };
  try {
    return { code: fn(), out: out.join(''), err: err.join('') };
  } finally {
    process.stdout.write = so;
    process.stderr.write = se;
  }
}

test('коды выхода по смыслу', () => {
  assert.deepEqual(EXIT, { OK: 0, REFUSED: 1, NOT_FOUND: 2, UNKNOWN: 3 });
});

test('emit json печатает одну строку и возвращает code', () => {
  const r = capture(() => emit({ code: 0, a: 1, text: 'hi' }, { json: true }));
  assert.equal(r.code, 0);
  assert.equal(r.out.trim().split('\n').length, 1);
  const o = JSON.parse(r.out);
  assert.equal(o.a, 1);
  assert.equal(o.code, 0);
  assert.equal('text' in o, false, 'человеческий текст в json не нужен');
  assert.equal(r.err, '');
});

test('emit без json печатает text', () => {
  const r = capture(() => emit({ code: 0, text: 'done' }, { json: false }));
  assert.equal(r.out, 'done\n');
});

test('ошибка уходит в stderr', () => {
  const r = capture(() => emit({ code: 1, error: 'nope' }, { json: false }));
  assert.equal(r.code, 1);
  assert.equal(r.out, '');
  assert.match(r.err, /nope/);
  const j = capture(() => emit({ code: 2, error: 'missing' }, { json: true }));
  assert.equal(j.code, 2);
  assert.equal(JSON.parse(j.out).error, 'missing', 'при --json error и в теле');
  assert.match(j.err, /missing/);
});

test('предупреждения уходят в stderr', () => {
  const r = capture(() => emit({ code: 0, text: 'ok', warnings: ['careful'] }, { json: false }));
  assert.equal(r.out, 'ok\n');
  assert.match(r.err, /careful/);
});

test('без аргументов и --help — справка и код 0', () => {
  for (const args of [[], ['--help'], ['help']]) {
    const r = runCli(args);
    assert.equal(r.status, 0, args.join(' '));
    assert.match(r.stdout, /usage: claude-wt/);
    assert.match(r.stdout, /window focus/);
  }
});

test('неизвестная команда — код 1 и справка', () => {
  const r = runCli(['frobnicate', 'now']);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /unknown command/);
  assert.match(r.stderr, /usage: claude-wt/);
});

test('имена из прототипа — неизвестная команда, без трассы', () => {
  for (const name of ['__proto__', 'constructor', 'toString', 'hasOwnProperty']) {
    const r = runCli([name]);
    assert.equal(r.status, 1, name);
    assert.match(r.stderr, /unknown command/, name);
    assert.doesNotMatch(r.stderr, /TypeError|is not a function/, name);
  }
});
