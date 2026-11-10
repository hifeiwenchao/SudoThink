import http from './http'
import type { ArticleBrief } from './article'

export type TaxonomyItem = ArticleBrief

export interface Category extends TaxonomyItem {
  description: string
  weight: number
  created_at: string
}

export interface CategoryInput {
  name: string
  slug?: string
  description: string
  weight: number
}

export interface Tag extends TaxonomyItem {
  created_at: string
}

export interface TagInput {
  name: string
  slug?: string
}

export const taxonomyApi = {
  categories() {
    return http.get<unknown, Category[]>('/categories')
  },
  create(data: CategoryInput) {
    return http.post<unknown, Category>('/categories', data)
  },
  update(id: number, data: CategoryInput) {
    return http.put<unknown, Category>(`/categories/${id}`, data)
  },
  remove(id: number) {
    return http.delete<unknown, void>(`/categories/${id}`)
  },
  tags() {
    return http.get<unknown, Tag[]>('/tags')
  },
  createTag(data: TagInput) {
    return http.post<unknown, Tag>('/tags', data)
  },
  updateTag(id: number, data: TagInput) {
    return http.put<unknown, Tag>(`/tags/${id}`, data)
  },
  removeTag(id: number) {
    return http.delete<unknown, void>(`/tags/${id}`)
  },
}
