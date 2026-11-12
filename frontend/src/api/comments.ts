import axios, { type AxiosRequestConfig } from 'axios'

export interface PublicComment {
  id: number
  nickname: string
  location: string
  content: string
  created_at: string
  parent_id: number | null
}

export interface CommentPage {
  items: PublicComment[]
  total: number
  page: number
  size: number
}

export interface CommentInput {
  nickname: string
  email?: string
  content: string
  parent_id?: number
}

async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await axios.request<{ code: number; data: T; message?: string }>({
    baseURL: import.meta.env?.VITE_API_BASE_URL || '/api',
    timeout: 15000,
    ...config,
  })
  if (response.data?.code !== 0) throw new Error(response.data?.message || '评论请求失败')
  return response.data.data
}

export const commentsApi = {
  list(articleId: number, page = 1, size = 10, signal?: AbortSignal) {
    return request<CommentPage>({ method: 'get', url: `/articles/${articleId}/comments`, params: { page, size }, signal })
  },
  create(articleId: number, data: CommentInput, signal?: AbortSignal) {
    return request<{ id: number; is_approved: false }>({ method: 'post', url: `/articles/${articleId}/comments`, data, signal })
  },
}
