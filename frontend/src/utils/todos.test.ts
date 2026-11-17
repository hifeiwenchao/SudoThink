import assert from 'node:assert/strict'
import { test } from 'node:test'
import { prepareTodoInput } from './todos'

test('a reminder preserves the selected instant across time zones in its API payload', () => {
  const result = prepareTodoInput({
    title: '  更新证书  ', content: '  检查域名证书  ',
    due_at: new Date('2026-11-18T09:30:00+08:00'), reminder_enabled: true,
    reminder_email: ' owner@example.com ',
  })
  assert.deepEqual(result, { errors: {}, input: {
    title: '更新证书', content: '检查域名证书',
    due_at: '2026-11-18T01:30:00.000Z', reminder_enabled: true,
    reminder_email: 'owner@example.com',
  } })
})

test('an ordinary todo may have no deadline while an enabled reminder needs a valid time', () => {
  assert.deepEqual(prepareTodoInput({ title: '读书', content: '', due_at: null, reminder_enabled: false, reminder_email: '' }), {
    errors: {}, input: { title: '读书', content: '', due_at: null, reminder_enabled: false, reminder_email: '' },
  })
  for (const due_at of [null, new Date('invalid')]) {
    const result = prepareTodoInput({ title: '读书', content: '', due_at, reminder_enabled: true, reminder_email: 'owner@example.com' })
    assert.equal(result.input, null)
    assert.ok(result.errors.due_at)
  }
})

test('blank and oversized fields cannot be submitted and valid boundary lengths remain intact', () => {
  for (const title of ['  ', '字'.repeat(201)]) {
    const result = prepareTodoInput({ title, content: '', due_at: null, reminder_enabled: false, reminder_email: '' })
    assert.equal(result.input, null)
    assert.ok(result.errors.title)
  }
  const tooLong = prepareTodoInput({ title: '标题', content: '字'.repeat(10001), due_at: null, reminder_enabled: false, reminder_email: '' })
  assert.equal(tooLong.input, null)
  assert.ok(tooLong.errors.content)
  const valid = prepareTodoInput({ title: '字'.repeat(200), content: '字'.repeat(10000), due_at: null, reminder_enabled: false, reminder_email: '' })
  assert.equal(valid.input?.title.length, 200)
  assert.equal(valid.input?.content.length, 10000)
})

test('past deadlines are preserved so an overdue todo can be reminded on the next check', () => {
  const result = prepareTodoInput({ title: '已到期', content: '', due_at: new Date('2020-01-01T00:00:00Z'), reminder_enabled: true, reminder_email: 'owner@example.com' })
  assert.equal(result.input?.due_at, '2020-01-01T00:00:00.000Z')
  assert.deepEqual(result.errors, {})
})

test('each enabled reminder requires one valid recipient and rejects mail lists or header injection', () => {
  for (const reminder_email of ['', '  ', 'invalid', 'owner@', '@example.com', 'Owner <owner@example.com>', 'one@example.com,two@example.com', 'one@example.com;two@example.com', 'owner@example.com\r\nBcc:other@example.com', 'owner@example.com\n', 'a'.repeat(255)]) {
    const result = prepareTodoInput({ title: '提醒', content: '', due_at: new Date('2026-11-18T09:30:00Z'), reminder_enabled: true, reminder_email })
    assert.equal(result.input, null, reminder_email)
    assert.ok(result.errors.reminder_email, reminder_email)
  }
})

test('turning email reminders off retains the chosen recipient for later reuse', () => {
  const result = prepareTodoInput({ title: '提醒', content: '', due_at: null, reminder_enabled: false, reminder_email: ' owner+todo@example.com ' })
  assert.equal(result.input?.reminder_email, 'owner+todo@example.com')
  assert.equal(result.input?.reminder_enabled, false)
})
