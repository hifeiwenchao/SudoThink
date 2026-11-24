import type { User } from '../api/auth'

type Session = { token: string; user: User | null }
let memory: Session | undefined
const listeners = new Set<(session: Session) => void>()
export const BEFORE_SESSION_REDIRECT = 'sudothink:before-session-redirect'

export function readSession(): Session {
  if (memory) return memory
  try {
    const token = window.localStorage.getItem('access_token') || ''
    const user = JSON.parse(window.localStorage.getItem('user') || 'null')
    if (typeof user?.id === 'number' && typeof user?.is_admin === 'boolean' && token) {
      return { token, user }
    }
  } catch { /* A browser may deny storage or contain a damaged old session. */ }
  return { token: '', user: null }
}

export function setSession(token: string, user: User | null) {
  memory = { token, user }
  try {
    if (token && user) {
      window.localStorage.setItem('access_token', token)
      window.localStorage.setItem('user', JSON.stringify(user))
    } else {
      window.localStorage.removeItem('access_token')
      window.localStorage.removeItem('user')
    }
  } catch {
    // Never leave a new token paired with a previous account after a partial write.
    for (const key of ['access_token', 'user']) {
      try { window.localStorage.removeItem(key) } catch { /* Storage can be denied entirely. */ }
    }
  }
  for (const listener of listeners) listener(memory)
}
export function onSessionChange(listener: (session: Session) => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export function expireSession(requestToken: string): boolean {
  if (!requestToken || readSession().token !== requestToken) return false
  // Synchronous notification lets editors persist their final keystrokes first.
  window.dispatchEvent(new window.Event(BEFORE_SESSION_REDIRECT))
  setSession('', null)
  return true
}
