import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildTodoCron, describeTodoCron, normalizeTodoCron, recommendedTodoSkipPeriod, type TodoCronBuilder } from './todoCron'

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

test('skip period recommendations follow the widest restricted calendar field', () => {
  const cases = [
    ['0 9 1,2,3 * *', 'month'],
    ['0 9 * JAN,MAR *', 'year'],
    ['0 9 */2 * *', 'month'],
    ['0 9 * */2 *', 'year'],
    ['0 9 * * MON-FRI', 'week'],
    ['0 9 * * 7', 'week'],
    ['0 9 * * */2', 'week'],
    ['0 9 1 * MON', 'month'],
    ['0 9 1 JUN MON', 'year'],
    ['0 9 * * *', 'day'],
    ['*/15 8-18 * * *', 'day'],
  ] as const
  for (const [expression, expected] of cases) {
    assert.equal(recommendedTodoSkipPeriod({ reminder_repeat: 'cron', reminder_cron: expression }), expected, expression)
  }
})

test('full calendar ranges, lists and unit steps do not restrict skip period recommendations', () => {
  for (const expression of [
    '0 9 1-31 1-12 0-6',
    '0 9 */1 */1 */1',
    '0 9 * JAN-DEC SUN-SAT',
    '0 9 * * 1-7',
    '0 9 * * 0,1,2,3,4,5,6,7',
    '0 9 1-15,16-31 1-6,7-12 0-3,4-6',
  ]) {
    assert.equal(recommendedTodoSkipPeriod({ reminder_repeat: 'cron', reminder_cron: expression }), 'day', expression)
  }
})

test('legacy reminders recommend their existing interval and invalid cron safely defaults to day', () => {
  for (const [repeat, expected] of [['daily', 'day'], ['monthly', 'month'], ['yearly', 'year'], ['once', 'day']] as const) {
    assert.equal(recommendedTodoSkipPeriod({ reminder_repeat: repeat, reminder_cron: '' }), expected)
  }
  for (const expression of ['invalid', '0 9 L * *', '0 9 31 4 *']) {
    assert.equal(recommendedTodoSkipPeriod({ reminder_repeat: 'cron', reminder_cron: expression }), 'day', expression)
  }
})
