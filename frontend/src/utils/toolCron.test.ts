import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { previewCron } from './tools/cron'

describe('cron preview', () => {
  it('returns ten UTC executions strictly after the supplied starting instant', () => {
    const result = previewCron('*/15 * * * *', { startTime: '2026-11-10T00:00:00Z', timezone: 'UTC' })
    assert.deepEqual(result.times.map(time => time.iso), [
      '2026-11-10T00:15:00.000Z', '2026-11-10T00:30:00.000Z', '2026-11-10T00:45:00.000Z',
      '2026-11-10T01:00:00.000Z', '2026-11-10T01:15:00.000Z', '2026-11-10T01:30:00.000Z',
      '2026-11-10T01:45:00.000Z', '2026-11-10T02:00:00.000Z', '2026-11-10T02:15:00.000Z',
      '2026-11-10T02:30:00.000Z',
    ])
    assert.match(result.description, /15/)
    assert.match(result.description, /分钟/)
  })

  it('evaluates the schedule in the selected timezone', () => {
    const result = previewCron('0 9 * * 1', { startTime: '2026-11-08T00:00:00+00:00', timezone: 'Asia/Shanghai' })
    assert.equal(result.times[0].iso, '2026-11-09T01:00:00.000Z')
    assert.equal(result.times[1].iso, '2026-11-16T01:00:00.000Z')
    assert.match(result.times[0].formatted, /09:00:00/)
    assert.match(result.description, /星期一/)
  })

  it('accepts an optional seconds field and observes daylight saving changes', () => {
    const seconds = previewCron('*/20 * * * * *', { startTime: '2026-11-10T00:00:01Z', timezone: 'UTC' })
    assert.equal(seconds.times[0].iso, '2026-11-10T00:00:20.000Z')
    assert.equal(seconds.times[1].iso, '2026-11-10T00:00:40.000Z')
    const dst = previewCron('0 9 * * *', { startTime: '2026-03-07T00:00:00Z', timezone: 'America/New_York' })
    assert.equal(dst.times[0].iso, '2026-03-07T14:00:00.000Z')
    assert.equal(dst.times[1].iso, '2026-03-08T13:00:00.000Z')
  })

  it('reports malformed and impossible expressions without returning partial results', () => {
    for (const expression of ['', '* * *', '0 0 0 * * * 2026', '61 * * * *', '0 0 31 2 *', '* * * * *oops']) {
      assert.throws(() => previewCron(expression, { startTime: '2026-11-10T00:00:00Z', timezone: 'UTC' }), /表达式|执行时间/)
    }
  })

  it('fails an impossible February 31 schedule promptly', () => {
    const started = performance.now()
    assert.throws(() => previewCron('0 0 31 2 *', { startTime: '2026-11-10T00:00:00Z', timezone: 'UTC' }), /表达式|执行时间/)
    assert.ok(performance.now() - started < 1000, 'An impossible calendar date must not perform an unbounded search')
  })

  it('rejects invalid timezone and ambiguous or normalized starting dates', () => {
    assert.throws(() => previewCron('* * * * *', { startTime: '2026-11-10T00:00:00Z', timezone: 'Not/AZone' }), /时区/)
    for (const startTime of ['2026-02-30T00:00:00Z', '2026-11-10 00:00:00', 'invalid']) {
      assert.throws(() => previewCron('* * * * *', { startTime, timezone: 'UTC' }), /开始时间|日期/)
    }
  })
})
