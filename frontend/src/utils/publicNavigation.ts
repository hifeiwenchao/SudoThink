import type { LocationQuery, LocationQueryRaw } from 'vue-router'

export interface ArticleQuery { q: string; category?: number; tag?: number; page: number }
function positiveInteger(value: unknown): number | undefined {
  if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) return undefined
  const number = Number(value)
  return Number.isSafeInteger(number) ? number : undefined
}
export function parseArticleQuery(query: LocationQuery): ArticleQuery {
  return { q: typeof query.q === 'string' ? query.q.trim() : '', category: positiveInteger(query.category), tag: positiveInteger(query.tag), page: positiveInteger(query.page) || 1 }
}
export function articleQuery(state: ArticleQuery): LocationQueryRaw {
  return { ...(state.q ? { q: state.q } : {}), ...(state.category ? { category: String(state.category) } : {}), ...(state.tag ? { tag: String(state.tag) } : {}), ...(state.page > 1 ? { page: String(state.page) } : {}) }
}
export function safeListReturn(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return '/'
  try {
    const url = new URL(value, 'https://local.invalid')
    if (url.origin !== 'https://local.invalid' || url.pathname !== '/') return '/'
    const query = new URLSearchParams(articleQuery(parseArticleQuery(Object.fromEntries(url.searchParams))) as Record<string, string>)
    return `/${query.size ? `?${query}` : ''}${url.hash === '#articles' ? '#articles' : ''}`
  } catch { return '/' }
}

export function canReturnToListHistory(previous: unknown, listReturn: string): boolean {
  if (typeof previous !== 'string' || !previous.startsWith('/') || previous.startsWith('//') || previous.includes('\\')) return false
  try {
    const url = new URL(previous, 'https://local.invalid')
    if (url.origin !== 'https://local.invalid' || url.pathname !== '/') return false
    return safeListReturn(previous) === listReturn
  } catch { return false }
}
