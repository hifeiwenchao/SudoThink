import http from './http'

export interface ApiRequestLog {
  id: number
  method: string
  url: string
  path: string
  query_params: Record<string, unknown>
  path_params: Record<string, unknown>
  body_params: unknown | null
  status_code: number
  duration_ms: number
  created_at: string
}

export interface RequestLogFilters {
  url?: string
  method?: string
  status_code?: number
}

export interface RequestLogPage {
  items: ApiRequestLog[]
  total: number
  page: number
  size: number
}

export const requestLogsApi = {
  list(page = 1, size = 20, filters: RequestLogFilters = {}, signal?: AbortSignal) {
    return http.get<unknown, RequestLogPage>('/admin/operations/requests', {
      params: { page, size, ...filters }, signal,
    })
  },
}
