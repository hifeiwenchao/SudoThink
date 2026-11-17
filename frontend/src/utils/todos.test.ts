import assert from 'node:assert/strict'
import { test } from 'node:test'
import { prepareTodoInput } from './todos'

const schedule = { reminder_repeat: 'once' as const, reminder_timezone: 'Asia/Shanghai', reminder_cron: '' }

test('a reminder preserves the selected instant across time zones in its API payload', () => {
  const result = prepareTodoInput({ ...schedule,
    title: '  更新证书  ', content: '  检查域名证书  ',
    due_at: new Date('2026-11-18T09:30:00+08:00'), reminder_enabled: true,
    reminder_email: ' owner@example.com ',
  })
  assert.deepEqual(result, { errors: {}, input: {
    ...schedule, title: '更新证书', content: '检查域名证书',
    due_at: '2026-11-18T01:30:00.000Z', reminder_enabled: true,
    reminder_email: 'owner@example.com',
  } })
})

test('an ordinary todo may have no deadline while an enabled reminder needs a valid time', () => {
  assert.deepEqual(prepareTodoInput({ ...schedule, title: '读书', content: '', due_at: null, reminder_enabled: false, reminder_email: '' }), {
    errors: {}, input: { ...schedule, title: '读书', content: '', due_at: null, reminder_enabled: false, reminder_email: '' },
  })
  for (const due_at of [null, new Date('invalid')]) {
    const result = prepareTodoInput({ ...schedule, title: '读书', content: '', due_at, reminder_enabled: true, reminder_email: 'owner@example.com' })
    assert.equal(result.input, null)
    assert.ok(result.errors.due_at)
  }
})

test('blank and oversized fields cannot be submitted and valid boundary lengths remain intact', () => {
  for (const title of ['  ', '字'.repeat(201)]) {
    const result = prepareTodoInput({ ...schedule, title, content: '', due_at: null, reminder_enabled: false, reminder_email: '' })
    assert.equal(result.input, null)
    assert.ok(result.errors.title)
  }
  const tooLong = prepareTodoInput({ ...schedule, title: '标题', content: '字'.repeat(10001), due_at: null, reminder_enabled: false, reminder_email: '' })
  assert.equal(tooLong.input, null)
  assert.ok(tooLong.errors.content)
  const valid = prepareTodoInput({ ...schedule, title: '字'.repeat(200), content: '字'.repeat(10000), due_at: null, reminder_enabled: false, reminder_email: '' })
  assert.equal(valid.input?.title.length, 200)
  assert.equal(valid.input?.content.length, 10000)
})

test('past deadlines are preserved so an overdue todo can be reminded on the next check', () => {
  const result = prepareTodoInput({ ...schedule, title: '已到期', content: '', due_at: new Date('2020-01-01T00:00:00Z'), reminder_enabled: true, reminder_email: 'owner@example.com' })
  assert.equal(result.input?.due_at, '2020-01-01T00:00:00.000Z')
  assert.deepEqual(result.errors, {})
})

test('each enabled reminder requires one valid recipient and rejects mail lists or header injection', () => {
  for (const reminder_email of ['', '  ', 'invalid', 'owner@', '@example.com', 'Owner <owner@example.com>', 'one@example.com,two@example.com', 'one@example.com;two@example.com', 'owner@example.com\r\nBcc:other@example.com', 'owner@example.com\n', 'a'.repeat(255)]) {
    const result = prepareTodoInput({ ...schedule, title: '提醒', content: '', due_at: new Date('2026-11-18T09:30:00Z'), reminder_enabled: true, reminder_email })
    assert.equal(result.input, null, reminder_email)
    assert.ok(result.errors.reminder_email, reminder_email)
  }
})

test('turning email reminders off retains the chosen recipient for later reuse', () => {
  const result = prepareTodoInput({ ...schedule, title: '提醒', content: '', due_at: null, reminder_enabled: false, reminder_email: ' owner+todo@example.com ' })
  assert.equal(result.input?.reminder_email, 'owner+todo@example.com')
  assert.equal(result.input?.reminder_enabled, false)
})

test('recurring reminders preserve their calendar rule and named time zone', () => {
  const result = prepareTodoInput({ ...schedule,
    title: '月末结算', content: '', due_at: new Date('2026-01-31T09:30:00+08:00'),
    reminder_enabled: true, reminder_email: 'owner@example.com',
    reminder_repeat: 'monthly', reminder_timezone: 'Asia/Shanghai',
  })
  assert.equal(result.input?.reminder_repeat, 'monthly')
  assert.equal(result.input?.reminder_timezone, 'Asia/Shanghai')
  assert.equal(result.input?.due_at, '2026-01-31T01:30:00.000Z')
})

test('unsupported recurrence or time zones cannot be submitted', () => {
  for (const rule of [
    { reminder_repeat: 'weekly', reminder_timezone: 'Asia/Shanghai' },
    { reminder_repeat: 'daily', reminder_timezone: 'Invalid/Timezone' },
  ]) {
    const result = prepareTodoInput({ ...schedule,
      title: '提醒', content: '', due_at: new Date('2026-11-18T01:30:00Z'),
      reminder_enabled: true, reminder_email: 'owner@example.com', ...rule,
    } as Parameters<typeof prepareTodoInput>[0])
    assert.equal(result.input, null)
    assert.ok(result.errors.reminder_repeat || result.errors.reminder_timezone)
  }
})

test('crontab reminders use an expression without requiring a legacy date', () => {
  const result = prepareTodoInput({ title: '工作日提醒', content: '', due_at: null,
    reminder_enabled: true, reminder_email: 'owner@example.com', reminder_repeat: 'cron',
    reminder_timezone: 'Asia/Shanghai', reminder_cron: '  0  9 * * 1-5  ',
  } as Parameters<typeof prepareTodoInput>[0])
  assert.equal(result.input?.reminder_repeat, 'cron')
  assert.equal((result.input as unknown as { reminder_cron: string })?.reminder_cron, '0 9 * * 1-5')
  assert.equal(result.input?.due_at, null)
})

test('crontab reminder input rejects empty, invalid and seconds expressions', () => {
  for (const reminder_cron of ['', '0 0 9 * * *', '61 9 * * *', '0 9 * * * rm -rf /']) {
    const result = prepareTodoInput({ title: '提醒', content: '', due_at: null,
      reminder_enabled: true, reminder_email: 'owner@example.com', reminder_repeat: 'cron',
      reminder_timezone: 'Asia/Shanghai', reminder_cron,
    } as Parameters<typeof prepareTodoInput>[0])
    assert.equal(result.input, null)
    assert.ok((result.errors as Record<string, string>).reminder_cron)
  }
})
