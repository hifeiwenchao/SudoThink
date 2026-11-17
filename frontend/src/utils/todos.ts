import type { TodoInput, TodoRepeat } from '../api/todos'
import { normalizeTodoCron } from './todoCron'

export interface TodoForm {
  title: string
  content: string
  due_at: Date | null
  reminder_enabled: boolean
  reminder_email: string
  reminder_repeat: TodoRepeat
  reminder_timezone: string
  reminder_cron: string
}

export type TodoFormErrors = Partial<Record<'title' | 'content' | 'due_at' | 'reminder_email' | 'reminder_repeat' | 'reminder_timezone' | 'reminder_cron', string>>

export function deviceTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai'
}

function validMailbox(value: string) {
  const parts = value.split('@')
  if (parts.length !== 2) return false
  const [local, domain] = parts as [string, string]
  if (!local || local.length > 64 || local.startsWith('.') || local.endsWith('.') || local.includes('..')) return false
  if (!/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)) return false
  const labels = domain.split('.')
  return labels.length >= 2 && labels.every(label => /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label))
}

export function prepareTodoInput(form: TodoForm): { input: TodoInput | null; errors: TodoFormErrors } {
  const errors: TodoFormErrors = {}
  const title = form.title.trim()
  const content = form.content.trim()
  const reminderEmail = form.reminder_email.trim()
  if (!title) errors.title = '请填写待办标题'
  else if (Array.from(title).length > 200) errors.title = '标题不能超过 200 个字符'
  if (Array.from(content).length > 10000) errors.content = '内容不能超过 10000 个字符'
  const hasDate = form.due_at !== null
  const validDate = form.due_at instanceof Date && Number.isFinite(form.due_at.getTime())
  if (hasDate && !validDate) errors.due_at = '请选择有效的到期时间'
  else if (form.reminder_enabled && form.reminder_repeat !== 'cron' && !validDate) errors.due_at = '请设置新的提醒规则'
  if (form.reminder_enabled && !reminderEmail) errors.reminder_email = '请填写收件邮箱'
  else if (/\r|\n/.test(form.reminder_email) || reminderEmail.length > 254 || (reminderEmail && !validMailbox(reminderEmail))) {
    errors.reminder_email = '请填写有效的单个邮箱地址，不能包含姓名、多个地址或换行'
  }
  if (!['once', 'daily', 'monthly', 'yearly', 'cron'].includes(form.reminder_repeat)) errors.reminder_repeat = '请选择有效的提醒规则'
  let cron = form.reminder_cron?.trim() || ''
  if (form.reminder_repeat === 'cron' && (form.reminder_enabled || cron)) {
    try { cron = normalizeTodoCron(cron) }
    catch (cause) { errors.reminder_cron = cause instanceof Error ? cause.message : '请填写有效的 crontab 表达式' }
  }
  try {
    if (!form.reminder_timezone || form.reminder_timezone.length > 64) throw new Error('invalid timezone')
    new Intl.DateTimeFormat('zh-CN', { timeZone: form.reminder_timezone }).format()
  } catch {
    errors.reminder_timezone = '提醒时区无效，请重新设置提醒时间'
  }
  if (Object.keys(errors).length) return { input: null, errors }
  return { errors, input: {
    title, content, due_at: validDate ? form.due_at!.toISOString() : null,
    reminder_enabled: form.reminder_enabled,
    reminder_email: reminderEmail,
    reminder_repeat: form.reminder_repeat,
    reminder_timezone: form.reminder_timezone,
    reminder_cron: cron,
  } }
}
