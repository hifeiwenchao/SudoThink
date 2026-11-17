import http from './http'

export type TodoReminderStatus = 'disabled' | 'pending' | 'sending' | 'sent' | 'failed'
export type TodoFilter = 'all' | 'pending' | 'completed' | 'overdue'
export type TodoRepeat = 'once' | 'daily' | 'monthly' | 'yearly'

export interface Todo {
  id: number
  title: string
  content: string
  due_at: string | null
  is_completed: boolean
  reminder_enabled: boolean
  reminder_email: string
  reminder_repeat: TodoRepeat
  reminder_timezone: string
  reminder_next_run_at: string | null
  reminder_status: TodoReminderStatus
  reminder_sent_at: string | null
  reminder_attempts: number
  reminder_error: string
  created_at: string
  updated_at: string
}

export interface TodoInput {
  title: string
  content: string
  due_at: string | null
  reminder_enabled: boolean
  reminder_email: string
  reminder_repeat: TodoRepeat
  reminder_timezone: string
}

export interface TodoPage {
  items: Todo[]
  total: number
  page: number
  size: number
  email_configured: boolean
}

export const todosApi = {
  list(params: { page: number; size: number; status: TodoFilter; q?: string }, signal?: AbortSignal) {
    return http.get<unknown, TodoPage>('/admin/todos', { params, signal })
  },
  create(input: TodoInput) {
    return http.post<unknown, Todo>('/admin/todos', input)
  },
  update(id: number, input: TodoInput) {
    return http.put<unknown, Todo>(`/admin/todos/${id}`, input)
  },
  complete(id: number, is_completed: boolean) {
    return http.patch<unknown, Todo>(`/admin/todos/${id}/completion`, { is_completed })
  },
  remove(id: number) {
    return http.delete<unknown, null>(`/admin/todos/${id}`)
  },
  retry(id: number) {
    return http.post<unknown, Todo>(`/admin/todos/${id}/retry`)
  },
}
