export interface Commenter {
  nickname: string
  email: string
}

const STORAGE_KEY = 'sudothink_commenter'

export function validateComment(input: Commenter & { content: string }): string | null {
  const nickname = input.nickname.trim()
  if (!/^[\p{Script=Han}A-Za-z0-9_]+$/u.test(nickname) || Array.from(nickname).length > 32) {
    return '昵称须为 1–32 个中文、英文字母、数字或下划线'
  }
  const email = input.email.trim()
  if (email && (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))) return '请填写有效的邮箱地址，或留空'
  const length = Array.from(input.content.trim()).length
  if (length < 1 || length > 1000) return '评论内容须为 1–1000 个字符'
  return null
}

export function readCommenter(storage?: Pick<Storage, 'getItem'>): Commenter {
  try {
    const saved: unknown = JSON.parse((storage ?? window.localStorage).getItem(STORAGE_KEY) || 'null')
    if (saved && typeof saved === 'object' && 'nickname' in saved && 'email' in saved
      && typeof saved.nickname === 'string' && typeof saved.email === 'string') {
      return { nickname: saved.nickname, email: saved.email }
    }
  } catch { /* Storage may be unavailable in private browsing. */ }
  return { nickname: '', email: '' }
}

export function saveCommenter(commenter: Commenter, storage?: Pick<Storage, 'setItem'>): void {
  try {
    ;(storage ?? window.localStorage).setItem(STORAGE_KEY, JSON.stringify({
      nickname: commenter.nickname.trim(), email: commenter.email.trim(),
    }))
  } catch { /* A storage failure must not turn a successful submission into an error. */ }
}
