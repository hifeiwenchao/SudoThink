import assert from 'node:assert/strict'
import { test } from 'node:test'
import { JSDOM } from 'jsdom'
const dom = new JSDOM('', { url: 'https://admin.example.com' })
Object.assign(globalThis, { window: dom.window })
const session = await import('./session')
test('corrupt or inaccessible storage cannot break session reads; session stays usable in memory', () => {
  window.localStorage.setItem('user', '{bad')
  window.localStorage.setItem('access_token', 'bad')
  assert.equal(session.readSession().user, null)
  Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw Error('disabled') } })
  assert.doesNotThrow(() => session.readSession())
  session.setSession('token', { id: 7, is_admin: true } as any)
  assert.equal(session.readSession().token, 'token')
  let events = 0
  const stop = session.onSessionChange(() => events++)
  assert.equal(session.expireSession('token'), true)
  assert.equal(session.expireSession('token'), false)
  assert.equal(events, 1)
  assert.deepEqual(session.readSession(), { token: '', user: null })
  stop()
})
