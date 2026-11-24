export type ArticleDraftForm = {
  title: string; summary: string; content: string; cover: string
  category_id: number | null; tag_ids: number[]
}
export type ArticleDraft = { version: 1; savedAt: string; baseline: string; form: ArticleDraftForm }
function key(userId: number, articleId: number | null) { return `sudothink:article-draft:${userId}:${articleId ?? 'new'}` }
export function readArticleDraft(userId: number, articleId: number | null): ArticleDraft | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(key(userId, articleId)) || 'null')
    const form = value?.form
    if (value?.version !== 1 || typeof value.savedAt !== 'string' || !Number.isFinite(Date.parse(value.savedAt))
      || typeof value.baseline !== 'string' || !form
      || !['title', 'summary', 'content', 'cover'].every((name) => typeof form[name] === 'string')
      || !(form.category_id === null || Number.isInteger(form.category_id))
      || !Array.isArray(form.tag_ids) || !form.tag_ids.every(Number.isInteger)) return null
    return value
  } catch { return null }
}
export function writeArticleDraft(userId: number, articleId: number | null, form: ArticleDraftForm, baseline: string): boolean {
  try {
    window.localStorage.setItem(key(userId, articleId), JSON.stringify({ version: 1, savedAt: new Date().toISOString(), baseline, form }))
    return true
  } catch { return false }
}
export function removeArticleDraft(userId: number, articleId: number | null): boolean {
  try { window.localStorage.removeItem(key(userId, articleId)); return true } catch { return false }
}
