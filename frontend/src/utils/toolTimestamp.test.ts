import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { describeTimestamp, formatDateTime, formatTimestamp, parseDateTime, parseTimestamp } from './tools/timestamp'

describe('timestamp conversion', () => {
  it('bounds input length before parsing while accepting the exact boundary', () => {
    assert.equal(parseTimestamp('0'.repeat(127) + '1', 'seconds'), 1000)
    assert.throws(() => parseTimestamp('0'.repeat(129), 'seconds'), /128|过长/)
    assert.throws(() => parseTimestamp('0'.repeat(129), 'milliseconds'), /128|过长/)
    assert.equal(parseDateTime('1970-01-01T00:00:00Z'.padEnd(128, ' '), 'utc'), 0)
    assert.throws(() => parseDateTime('1970-01-01T00:00:00Z'.padEnd(129, ' '), 'utc'), /128|过长/)
  })

  it('keeps the Unix epoch and times before it in both units', () => {
    assert.equal(parseTimestamp('0', 'seconds'), 0)
    assert.equal(parseTimestamp('-1', 'seconds'), -1000)
    assert.equal(parseTimestamp('-1', 'milliseconds'), -1)
    assert.equal(parseDateTime('1970-01-01 00:00:00', 'utc'), 0)
    assert.equal(parseDateTime('1969-12-31T23:59:59.999Z', 'local'), -1)
    assert.equal(formatTimestamp(-1, 'seconds'), '-0.001')
    assert.equal(formatTimestamp(-1001, 'milliseconds'), '-1001')
  })

  it('honors explicit ISO offsets and retains subsecond precision', () => {
    assert.equal(parseDateTime('2024-02-29T08:30:15.123+08:00', 'utc'), 1709166615123)
    assert.equal(parseTimestamp('1709166615.123', 'seconds'), 1709166615123)
    assert.equal(formatDateTime(1709166615123, 'utc'), '2024-02-29 00:30:15.123')
    const result = describeTimestamp(1709166615123)
    assert.equal(result.utc, '2024-02-29T00:30:15.123Z')
    assert.equal(result.seconds, '1709166615.123')
    assert.equal(result.milliseconds, '1709166615123')
    assert.match(result.local, /UTC[+-]\d{2}:\d{2}$/)
  })

  it('uses the local timezone only for dates without an explicit offset', () => {
    const local = new Date(2026, 10, 10, 12, 34, 56, 789).getTime()
    assert.equal(parseDateTime('2026-11-10 12:34:56.789', 'local'), local)
    assert.equal(formatDateTime(local, 'local'), '2026-11-10 12:34:56.789')
    assert.equal(parseDateTime('0099-01-01T00:00:00Z', 'utc'), -59042995200000)
  })

  it('rejects impossible dates instead of letting Date normalize them', () => {
    for (const value of ['2025-02-29 00:00:00', '2024-04-31 00:00', '2024-13-01 00:00', '2024-02-29 24:00', '2024-02-29T10:00+24:00', '2024-02-29T12:60Z']) {
      assert.throws(() => parseDateTime(value, 'utc'), /日期|时间|偏移/)
    }
  })

  it('rejects empty, malformed, imprecise, and out-of-range timestamps', () => {
    for (const value of ['', '1e3', 'NaN', '1.0001', '8640000000001']) {
      assert.throws(() => parseTimestamp(value, 'seconds'), /时间戳|范围/)
    }
    for (const value of ['1.5', '8640000000000001', '-8640000000000001']) {
      assert.throws(() => parseTimestamp(value, 'milliseconds'), /时间戳|范围/)
    }
    assert.equal(parseTimestamp('8640000000000000', 'milliseconds'), 8640000000000000)
    assert.throws(() => describeTimestamp(Number.NaN), /时间戳|范围/)
  })
})
