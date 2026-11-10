import { CronExpressionParser } from 'cron-parser'
import cronstrue from 'cronstrue'
import 'cronstrue/locales/zh_CN'
import { parseDateTime } from './timestamp'

export interface CronPreviewOptions {
  startTime: string
  timezone: string
}

export function previewCron(expression: string, options: CronPreviewOptions) {
  const normalized = expression.trim().replace(/\s+/g, ' ')
  if (![5, 6].includes(normalized.split(' ').length) || normalized.length > 256) {
    throw new Error('Cron 表达式须包含 5 个字段，或附带秒的 6 个字段')
  }
  const timezone = options.timezone === 'local' ? Intl.DateTimeFormat().resolvedOptions().timeZone : options.timezone
  let formatter: Intl.DateTimeFormat
  try {
    formatter = new Intl.DateTimeFormat('sv-SE', {
      timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZoneName: 'shortOffset',
    })
    if (!timezone) throw new Error('empty timezone')
  } catch {
    throw new Error('时区无效，请选择或输入有效的 IANA 时区名称')
  }
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(options.startTime.trim())) {
    throw new Error('开始时间必须包含 Z 或 ±HH:mm 时区偏移')
  }
  let start: number
  try {
    start = parseDateTime(options.startTime, 'utc')
  } catch (error) {
    throw new Error(`开始时间无效：${error instanceof Error ? error.message : String(error)}`)
  }
  try {
    const schedule = CronExpressionParser.parse(normalized, { currentDate: start, tz: timezone })
    const description = cronstrue.toString(normalized, {
      locale: 'zh_CN', use24HourTimeFormat: true, logicalAndDayFields: false, throwExceptionOnParseError: true,
    })
    // The parser bounds its internal search; take also caps the requested result count.
    const times = schedule.take(10).map(value => {
      const date = value.toDate()
      return { iso: date.toISOString(), formatted: formatter.format(date) }
    })
    if (times.length !== 10) throw new Error('无法找到未来 10 次执行时间')
    return { description, times, timezone }
  } catch (error) {
    throw new Error(`Cron 表达式无效或无法计算执行时间：${error instanceof Error ? error.message : String(error)}`)
  }
}
