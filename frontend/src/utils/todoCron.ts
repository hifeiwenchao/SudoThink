import { CronExpressionParser } from 'cron-parser'
import cronstrue from 'cronstrue'
import 'cronstrue/locales/zh_CN'

export type TodoCronPreset = 'daily' | 'weekly' | 'monthly' | 'yearly' | 'interval' | 'custom'

export interface TodoCronBuilder {
  preset: TodoCronPreset
  time: string
  weekdays: number[]
  day: number
  month: number
  interval: number
}

const fieldSpans = [60, 24, 31, 12, 7]
const monthNames = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const weekdayNames = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']

/** Only the five-field syntax understood by the reminder scheduler is accepted. */
export function normalizeTodoCron(expression: string): string {
  const error = () => new Error('请输入有效的五段 crontab 表达式：分 时 日 月 周')
  if (typeof expression !== 'string' || expression.length > 128) throw error()
  const normalized = expression.trim().replace(/\s+/g, ' ').toUpperCase()
  const fields = normalized.split(' ')
  if (fields.length !== 5) throw error()
  for (const [index, field] of fields.entries()) {
    const numeric = field.replace(/[A-Z]+/g, name => {
      if (index === 3) {
        const month = monthNames.indexOf(name)
        if (month >= 0) return String(month + 1)
      }
      if (index === 4) {
        const weekday = weekdayNames.indexOf(name)
        if (weekday >= 0) return String(weekday)
      }
      return name
    })
    if (!/^(?:\*|\d+(?:-\d+)?)(?:\/\d+)?(?:,(?:\*|\d+(?:-\d+)?)(?:\/\d+)?)*$/.test(numeric)) throw error()
    for (const term of numeric.split(',')) {
      const step = term.split('/')[1]
      if (step !== undefined && !(Number(step) >= 1 && Number(step) <= fieldSpans[index]!)) throw error()
    }
  }
  try {
    // This only checks the input. Displayed execution times come from the server.
    CronExpressionParser.parse(normalized, { currentDate: '2024-01-01T00:00:00Z', tz: 'UTC' }).next()
  } catch {
    throw error()
  }
  return normalized
}

export function buildTodoCron(builder: TodoCronBuilder): string {
  if (builder.preset === 'interval') {
    if (!Number.isInteger(builder.interval) || builder.interval < 1 || builder.interval > 59) {
      throw new Error('提醒间隔须为 1 至 59 分钟')
    }
    return `*/${builder.interval} * * * *`
  }
  if (!/^\d{2}:\d{2}$/.test(builder.time)) throw new Error('请选择有效的提醒时间')
  const [hour, minute] = builder.time.split(':').map(Number)
  if (hour! > 23 || minute! > 59) throw new Error('请选择有效的提醒时间')
  const clock = `${minute} ${hour}`
  if (builder.preset === 'daily') return `${clock} * * *`
  if (builder.preset === 'weekly') {
    if (!builder.weekdays.length || builder.weekdays.some(day => !Number.isInteger(day) || day < 0 || day > 6)) {
      throw new Error('请至少选择一个有效的星期')
    }
    return `${clock} * * ${[...new Set(builder.weekdays)].sort((a, b) => a - b).join(',')}`
  }
  if (!Number.isInteger(builder.day) || builder.day < 1 || builder.day > 31) throw new Error('日期须为 1 至 31 日')
  if (builder.preset === 'monthly') return `${clock} ${builder.day} * *`
  if (builder.preset === 'yearly') {
    if (!Number.isInteger(builder.month) || builder.month < 1 || builder.month > 12) throw new Error('月份须为 1 至 12 月')
    return normalizeTodoCron(`${clock} ${builder.day} ${builder.month} *`)
  }
  throw new Error('自定义规则请直接填写 crontab 表达式')
}

export function describeTodoCron(expression: string): string {
  try {
    return cronstrue.toString(normalizeTodoCron(expression), {
      locale: 'zh_CN', use24HourTimeFormat: true, logicalAndDayFields: false, throwExceptionOnParseError: true,
    })
  } catch {
    return '自定义提醒'
  }
}
