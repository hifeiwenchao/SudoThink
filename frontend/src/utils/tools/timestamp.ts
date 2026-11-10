export type TimestampUnit = 'seconds' | 'milliseconds'
export type DateZone = 'local' | 'utc'
export const MAX_TIMESTAMP_INPUT_LENGTH = 128

const DATE_LIMIT = 8_640_000_000_000_000

function validMilliseconds(value: number): number {
  if (!Number.isInteger(value) || Math.abs(value) > DATE_LIMIT) {
    throw new Error('时间戳超出支持范围（±8640000000000000 毫秒）')
  }
  return value
}

export function parseTimestamp(input: string, unit: TimestampUnit): number {
  if (input.length > MAX_TIMESTAMP_INPUT_LENGTH) throw new Error('时间戳输入过长，最多 128 个字符（含空白）')
  const value = input.trim()
  const match = (unit === 'seconds' ? /^([+-]?)(\d+)(?:\.(\d{1,3}))?$/ : /^([+-]?)(\d+)$/).exec(value)
  if (!match) throw new Error(unit === 'seconds' ? '秒时间戳须为整数或最多三位小数' : '毫秒时间戳须为整数')
  const magnitude = unit === 'seconds'
    ? BigInt(match[2]) * 1000n + BigInt((match[3] ?? '').padEnd(3, '0'))
    : BigInt(match[2])
  const milliseconds = match[1] === '-' ? -magnitude : magnitude
  if (milliseconds > BigInt(DATE_LIMIT) || milliseconds < -BigInt(DATE_LIMIT)) {
    throw new Error('时间戳超出支持范围（±8640000000000000 毫秒）')
  }
  return Number(milliseconds)
}

export function parseDateTime(input: string, zone: DateZone): number {
  if (input.length > MAX_TIMESTAMP_INPUT_LENGTH) throw new Error('日期时间输入过长，最多 128 个字符（含空白）')
  const match = /^([+-]\d{6}|\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?(Z|[+-]\d{2}:\d{2})?$/i.exec(input.trim())
  if (!match) throw new Error('日期格式应为 YYYY-MM-DD HH:mm:ss，可附毫秒、Z 或 ±HH:mm 偏移')
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, fraction, offset] = match
  const [year, month, day, hour, minute, second, millisecond] = [
    Number(yearText), Number(monthText), Number(dayText), Number(hourText), Number(minuteText), Number(secondText ?? 0), Number((fraction ?? '').padEnd(3, '0')),
  ]
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  if (month < 1 || month > 12 || day < 1 || day > days[month - 1] || hour > 23 || minute > 59 || second > 59) {
    throw new Error('日期或时间不存在，请检查年月日、时分秒')
  }
  let offsetMinutes = 0
  if (offset && offset.toUpperCase() !== 'Z') {
    const hours = Number(offset.slice(1, 3))
    const minutes = Number(offset.slice(4, 6))
    if (hours > 23 || minutes > 59) throw new Error('时区偏移无效')
    offsetMinutes = (hours * 60 + minutes) * (offset[0] === '-' ? -1 : 1)
  }
  const date = new Date(0)
  if (offset || zone === 'utc') {
    date.setUTCFullYear(year, month - 1, day)
    date.setUTCHours(hour, minute, second, millisecond)
    return validMilliseconds(date.getTime() - offsetMinutes * 60_000)
  }
  date.setHours(0, 0, 0, 0)
  date.setFullYear(year, month - 1, day)
  date.setHours(hour, minute, second, millisecond)
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day || date.getHours() !== hour || date.getMinutes() !== minute || date.getSeconds() !== second) {
    throw new Error('该本地日期或时间不存在，可能处于夏令时跳转时段')
  }
  return validMilliseconds(date.getTime())
}

export function formatTimestamp(milliseconds: number, unit: TimestampUnit): string {
  validMilliseconds(milliseconds)
  if (unit === 'milliseconds') return String(milliseconds)
  const value = BigInt(milliseconds)
  const absolute = value < 0n ? -value : value
  const fraction = String(absolute % 1000n).padStart(3, '0').replace(/0+$/, '')
  return `${value < 0n ? '-' : ''}${absolute / 1000n}${fraction ? `.${fraction}` : ''}`
}

export function formatDateTime(milliseconds: number, zone: DateZone): string {
  const date = new Date(validMilliseconds(milliseconds))
  const values = zone === 'utc'
    ? [date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate(), date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds(), date.getUTCMilliseconds()]
    : [date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours(), date.getMinutes(), date.getSeconds(), date.getMilliseconds()]
  const [year, month, day, hour, minute, second, fraction] = values
  const yearText = year >= 0 && year <= 9999 ? String(year).padStart(4, '0') : `${year < 0 ? '-' : '+'}${String(Math.abs(year)).padStart(6, '0')}`
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${yearText}-${pad(month)}-${pad(day)} ${pad(hour)}:${pad(minute)}:${pad(second)}.${String(fraction).padStart(3, '0')}`
}

export function describeTimestamp(milliseconds: number) {
  const date = new Date(validMilliseconds(milliseconds))
  const offset = -date.getTimezoneOffset()
  const offsetText = `${offset < 0 ? '-' : '+'}${String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0')}:${String(Math.abs(offset) % 60).padStart(2, '0')}`
  return {
    utc: date.toISOString(),
    local: `${formatDateTime(milliseconds, 'local')} UTC${offsetText}`,
    seconds: formatTimestamp(milliseconds, 'seconds'),
    milliseconds: formatTimestamp(milliseconds, 'milliseconds'),
  }
}
