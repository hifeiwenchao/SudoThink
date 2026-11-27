import http from './http'
import type { ContactFields } from '@/utils/aboutContacts'

export interface About extends ContactFields {
  id: number
  title: string
  content: string
  updated_at: string | null
}

export interface AboutInput extends ContactFields {
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
