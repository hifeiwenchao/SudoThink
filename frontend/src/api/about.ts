import http from './http'
import type { ContactFields } from '@/utils/aboutContacts'
import type { ArticleRecommendation } from './article'

export interface CurrentProject {
  name: string
  description: string
  url: string
}

export interface SidebarContent {
  featured_articles: ArticleRecommendation[]
  current_projects: CurrentProject[]
}

export interface About extends ContactFields {
  id: number
  title: string
  content: string
  updated_at: string | null
  featured_article_ids?: number[]
  current_projects?: CurrentProject[]
}

export interface AboutInput extends ContactFields {
  title: string
  content: string
  featured_article_ids?: number[]
  current_projects?: CurrentProject[]
}

export const aboutApi = {
  sidebar() {
    return http.get<unknown, SidebarContent>('/about/sidebar')
  },
  contacts() {
    return http.get<unknown, ContactFields>('/about/contacts')
  },
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
