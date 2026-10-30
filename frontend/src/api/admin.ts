import http from './http'

export interface DashboardResp {
  total_users: number
  total_articles: number
  total_comments: number
  pending_comments: number
}

export interface AdminUser {
  id: number
  username: string
  email: string
  nickname: string
  avatar: string
  bio: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface AdminArticleBrief {
  id: number
  title: string
  slug: string
  is_published: boolean
  view_count: number
  created_at: string
  author: { id: number; username: string }
}

export interface PendingComment {
  id: number
  content: string
  created_at: string
  article: { id: number; title: string }
  author: { id: number; username: string; nickname: string }
}

export interface PageResp<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export const adminApi = {
  dashboard() {
    return http.get<unknown, DashboardResp>('/admin/dashboard')
  },
  listUsers(page = 1, size = 10) {
    return http.get<unknown, PageResp<AdminUser>>('/admin/users', {
      params: { page, size },
    })
  },
  toggleAdmin(uid: number) {
    return http.post<unknown, { id: number; is_admin: boolean }>(`/admin/users/${uid}/toggle-admin`)
  },
  toggleActive(uid: number) {
    return http.post<unknown, { id: number; is_active: boolean }>(`/admin/users/${uid}/toggle-active`)
  },
  listArticles(page = 1, size = 10, q?: string) {
    return http.get<unknown, PageResp<AdminArticleBrief>>('/admin/articles', {
      params: { page, size, q },
    })
  },
  removeArticle(aid: number) {
    return http.delete<unknown, void>(`/admin/articles/${aid}`)
  },
  pendingComments(page = 1, size = 10) {
    return http.get<unknown, PageResp<PendingComment>>('/admin/comments/pending', {
      params: { page, size },
    })
  },
}
