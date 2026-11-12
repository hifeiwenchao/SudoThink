import http from './http'

export type CdnRefreshType = 'File' | 'Directory' | 'Regex'
export type CdnOperation = CdnRefreshType | 'Preload'

export interface CdnConfiguration {
  enabled: boolean
  cdn_base_url: string
  refresh_types: CdnRefreshType[]
  limits: {
    refresh_file: number
    refresh_directory: number
    refresh_regex: number
    preload: number
    max_url_length: number
  }
}

export interface CdnSubmission {
  task_id: string
  request_id: string
}

export interface CdnTask {
  task_id: string
  object_path: string
  object_type: string
  status: string
  process: string
  creation_time: string
  description?: string
}

export interface CdnTaskPage {
  items: CdnTask[]
  total: number
  page: number
  size: number
  request_id: string
}

export const operationsApi = {
  config(signal?: AbortSignal) {
    return http.get<unknown, CdnConfiguration>('/admin/operations/cdn/config', { signal })
  },
  refresh(urls: string[], objectType: CdnRefreshType) {
    return http.post<unknown, CdnSubmission>('/admin/operations/cdn/refresh', { urls, object_type: objectType })
  },
  preload(urls: string[]) {
    return http.post<unknown, CdnSubmission>('/admin/operations/cdn/preload', { urls })
  },
  tasks(taskId = '', page = 1, size = 20, signal?: AbortSignal) {
    return http.get<unknown, CdnTaskPage>('/admin/operations/cdn/tasks', {
      params: { task_id: taskId || undefined, page, size }, signal,
    })
  },
}
