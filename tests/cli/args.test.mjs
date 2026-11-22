// Разбор аргументов в манере старых скриптов скиллов: `--k v`, `--flag`, позиционные.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseLegacyArgs } from '../../cli/lib/args.mjs';

test('--k v и --flag', () => {
  assert.deepEqual(parseLegacyArgs(['--session-id', 'abc', '--force']), { flags: { 'session-id': 'abc', force: true }, positional: [] });
});

test('--k --next: значение не съедает следующий флаг', () => {
  assert.deepEqual(parseLegacyArgs(['--session-id', '--timeout', '0']).flags, { 'session-id': true, timeout: '0' });
});

test('пустая строка — не значение, а флаг и позиционный', () => {
  assert.deepEqual(parseLegacyArgs(['--to', '', 'x']), { flags: { to: true }, positional: ['', 'x'] });
});

test('позиционные отдельно, флаг со значением их не трогает', () => {
  assert.deepEqual(parseLegacyArgs(['a', '--cwd', '/p/x', 'b']), { flags: { cwd: '/p/x' }, positional: ['a', 'b'] });
});

test('булевы флаги не берут значение: --release x оставляет x позиционным', () => {
  assert.deepEqual(parseLegacyArgs(['--release', 'x', 'y'], { bool: ['release'] }), { flags: { release: true }, positional: ['x', 'y'] });
  assert.deepEqual(parseLegacyArgs(['--fork', 'yes']).flags, { fork: 'yes' }, 'без bool --fork берёт значение — так spawn ловит «takes no value»');
});

test('одиночное тире и --k=v — как в старых скриптах', () => {
  assert.deepEqual(parseLegacyArgs(['-x', '--k=v']), { flags: { 'k=v': true }, positional: ['-x'] });
});
