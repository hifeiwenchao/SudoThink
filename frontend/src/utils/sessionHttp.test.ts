import assert from 'node:assert/strict'
import { test, after } from 'node:test'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'
import { createPinia, setActivePinia } from 'pinia'
import { JSDOM } from 'jsdom'
const dom = new JSDOM('', { url: 'https://admin.example.com' })
const redirects: string[] = [], errors: string[] = []
const events = new dom.window.EventTarget()
const location = { pathname: '/articles/42/edit', search: '?source=list', hash: '#body', replace: (url: string) => redirects.push(url) }
Object.assign(globalThis, { window: { localStorage: dom.window.localStorage, location, Event: dom.window.Event,
  dispatchEvent: events.dispatchEvent.bind(events), addEventListener: events.addEventListener.bind(events) }, __sessionMessages: errors })
const session = await import('./session')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.session-http-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const helper = JSON.stringify(pathToFileURL(fileURLToPath(new URL('./session.ts', import.meta.url))).href)
const compile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const httpSource = readFileSync(new URL('../api/http.ts', import.meta.url), 'utf8')
  .replace("import { ElMessage } from 'element-plus'", 'const ElMessage = { error(message) { globalThis.__sessionMessages.push(message) } }')
  .replace("'@/utils/session'", helper).replace('import.meta.env.VITE_API_BASE_URL', 'undefined')
writeFileSync(`${folder}/http.mjs`, compile(httpSource))
const storeSource = readFileSync(new URL('../stores/user.ts', import.meta.url), 'utf8')
  .replace("import { authApi, type User } from '@/api/auth'", 'const authApi = {}')
  .replace("'@/utils/session'", helper)
writeFileSync(`${folder}/store.mjs`, compile(storeSource))
const { http } = await import(pathToFileURL(`${folder}/http.mjs`).href)
const { useUserStore } = await import(pathToFileURL(`${folder}/store.mjs`).href)
function fail(url: string, message = 'invalid credentials') {
  return http.get(url, { adapter: async (config: any) => { throw { config, response: { status: 401, data: { message } } } } }).catch(() => {})
}
test('concurrent protected 401 clears memory/store/storage once and retains exact return path', async () => {
  setActivePinia(createPinia()); session.setSession('live-token', { id: 1, is_admin: true } as any)
  const store = useUserStore()
  let flushed = false
  window.addEventListener(session.BEFORE_SESSION_REDIRECT, () => { flushed = true; assert.equal(store.token, 'live-token') })
  await Promise.all([fail('/admin/articles'), fail('/admin/todos')])
  assert.equal(flushed, true); assert.equal(store.token, ''); assert.equal(store.user, null)
  assert.equal(window.localStorage.getItem('access_token'), null); assert.equal(window.localStorage.getItem('user'), null)
  assert.deepEqual(errors, ['登录已失效，请重新登录'])
  assert.deepEqual(redirects, ['/login?redirect=%2Farticles%2F42%2Fedit%3Fsource%3Dlist%23body'])
})
test('login 401 displays credentials error without expiry/redirect or destroying newer session', async () => {
  session.setSession('new-token', { id: 2, is_admin: true } as any)
  await fail('/auth/login')
  assert.equal(session.readSession().token, 'new-token')
  assert.equal(errors.at(-1), 'invalid credentials'); assert.equal(redirects.length, 1)
  assert.equal(session.expireSession('old-token'), false)
  assert.equal(session.readSession().token, 'new-token')
})
