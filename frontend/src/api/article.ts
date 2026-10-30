import http from './http'

export interface ArticleAuthor {
  id: number
  username: string
  nickname: string
  avatar: string
}

export interface ArticleBrief {
  id: number
  name: string
  slug: string
}

export interface Article {
  id: number
  title: string
  slug: string
  summary: string
  content: string
  cover: string
  is_published: boolean
  view_count: number
  published_at: string | null
  created_at: string
  updated_at: string
  author: ArticleAuthor
  category: ArticleBrief | null
  tags: ArticleBrief[]
}

export interface ArticleListResp {
  items: Article[]
  total: number
  page: number
  size: number
}

export const articleApi = {
  list(params: { page?: number; size?: number; q?: string; category_id?: number; tag_id?: number } = {}) {
    return http.get<unknown, ArticleListResp>('/articles', { params })
  },
  detail(id: number) {
    return http.get<unknown, Article>(`/articles/${id}`)
  },
  create(data: {
    title: string
    summary?: string
    content: string
    cover?: string
    is_published?: boolean
    category_id?: number | null
    tag_ids?: number[]
  }) {
    return http.post<unknown, Article>('/articles', data)
  },
  update(id: number, data: Partial<{
    title: string
    summary: string
    content: string
    cover: string
    is_published: boolean
    category_id: number | null
    tag_ids: number[]
  }>) {
    return http.put<unknown, Article>(`/articles/${id}`, data)
  },
  remove(id: number) {
    return http.delete<unknown, void>(`/articles/${id}`)
  },
}
