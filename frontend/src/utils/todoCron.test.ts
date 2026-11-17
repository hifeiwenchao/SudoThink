import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildTodoCron, describeTodoCron, normalizeTodoCron, type TodoCronBuilder } from './todoCron'

const builder = (overrides: Partial<TodoCronBuilder> = {}): TodoCronBuilder => ({
  preset: 'daily', time: '09:30', weekdays: [1], day: 15, month: 6, interval: 15, ...overrides,
})

test('friendly daily, weekly, monthly and yearly rules generate standard five-field cron', () => {
  assert.equal(buildTodoCron(builder()), '30 9 * * *')
  assert.equal(buildTodoCron(builder({ preset: 'weekly', weekdays: [5, 1, 3, 1] })), '30 9 * * 1,3,5')
  assert.equal(buildTodoCron(builder({ preset: 'monthly', day: 31 })), '30 9 31 * *')
  assert.equal(buildTodoCron(builder({ preset: 'yearly', day: 29, month: 2, time: '00:05' })), '5 0 29 2 *')
  assert.equal(buildTodoCron(builder({ preset: 'interval', interval: 20 })), '*/20 * * * *')
})

test('friendly inputs reject empty weekdays, impossible dates and invalid ranges', () => {
  for (const values of [
    { time: '24:00' }, { time: '09:60' }, { time: '9:30' },
    { preset: 'weekly', weekdays: [] }, { preset: 'weekly', weekdays: [7] },
    { preset: 'monthly', day: 0 }, { preset: 'monthly', day: 32 },
    { preset: 'yearly', month: 0 }, { preset: 'yearly', month: 13 },
    { preset: 'yearly', month: 2, day: 30 }, { preset: 'yearly', month: 4, day: 31 },
    { preset: 'interval', interval: 0 }, { preset: 'interval', interval: 60 },
    { preset: 'interval', interval: 1.5 }, { preset: 'custom' },
  ]) assert.throws(() => buildTodoCron(builder(values as Partial<TodoCronBuilder>)))
})

test('standard expressions normalize whitespace and month or weekday names', () => {
  assert.equal(normalizeTodoCron('  0  9  * *  mon-fri  '), '0 9 * * MON-FRI')
  assert.equal(normalizeTodoCron('*/15 8-18 * jan,mar 1,3,5'), '*/15 8-18 * JAN,MAR 1,3,5')
  assert.equal(normalizeTodoCron('0 9 31 2 MON'), '0 9 31 2 MON')
  assert.equal(normalizeTodoCron('0 9 * * 7'), '0 9 * * 7')
  assert.equal(normalizeTodoCron('*/60 * * * *'), '*/60 * * * *')
})

test('unsupported syntax, commands, out-of-range values and impossible dates are rejected', () => {
  for (const expression of [
    '', '* * * *', '0 * * * * *', '@daily', '0 9 * * * echo hello',
    '0 9 L * *', '0 9 * * MON#1', '0 9 ? * MON', '0 9 * * FOO',
    '0 9 SUN * *', '0 9 * JANUARY *', '0 9 * * 5-1',
    '61 9 * * *', '0 24 * * *', '0 9 0 * *', '0 9 * 13 *', '0 9 * * 8',
    '*/0 * * * *', '*/61 * * * *', '0 */25 * * *', '0 9 */32 * *',
    '0 9 * */13 *', '0 9 * * */8', '0 9 30 2 *', '0 9 31 4 *', '0'.repeat(129),
  ]) assert.throws(() => normalizeTodoCron(expression), /crontab|表达式|字段|执行|标准/i, expression)
})

test('rule descriptions explain weekday and time while malformed expressions use a safe fallback', () => {
  const description = describeTodoCron('30 9 * * MON-FRI')
  assert.match(description, /09:30/)
  assert.match(description, /星期一|星期五|周一|周五/)
  assert.equal(describeTodoCron('untrusted expression'), '自定义提醒')
})
