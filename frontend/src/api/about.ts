import http from './http'

export interface About {
  id: number
  title: string
  content: string
  updated_at: string | null
}

export interface AboutInput {
  title: string
  content: string
}

export const aboutApi = {
  get() {
    return http.get<unknown, About>('/about')
  },
  adminGet() {
    return http.get<unknown, About>('/admin/about')
  },
  save(data: AboutInput) {
    return http.put<unknown, About>('/admin/about', data)
  },
}
