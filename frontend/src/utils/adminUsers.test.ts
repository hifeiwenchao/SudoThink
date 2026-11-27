import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
const dom = new JSDOM('<html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, Document: dom.window.Document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node, MutationObserver: dom.window.MutationObserver, MouseEvent: dom.window.MouseEvent, Event: dom.window.Event, CustomEvent: dom.window.CustomEvent, KeyboardEvent: dom.window.KeyboardEvent, FocusEvent: dom.window.FocusEvent, HTMLInputElement: dom.window.HTMLInputElement, HTMLButtonElement: dom.window.HTMLButtonElement, getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame, ResizeObserver: class { observe() {} unobserve() {} disconnect() {} } })
const { createApp, nextTick } = await import('vue')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.admin-users-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const transpile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const bridge = 'const http = { get: (...args) => globalThis.__userHttp.get(...args), post: (...args) => globalThis.__userHttp.post(...args) }'
writeFileSync(`${folder}/admin.mjs`, transpile(readFileSync(new URL('../api/admin.ts', import.meta.url), 'utf8').replace("import http from './http'", bridge)))
const { descriptor } = parse(readFileSync(new URL('../views/AdminUsers.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'admin-users-test' })
writeFileSync(`${folder}/component.mjs`, transpile(script.content
  .replace("import { ElMessage, ElMessageBox } from 'element-plus'", 'const ElMessage = { success() {} }; const ElMessageBox = { confirm: (...args) => globalThis.__userConfirm(...args) }')
  .replace("import { readSession } from '@/utils/session'", 'const readSession = () => ({ user: { id: 1 } })')
  .replace(/(['"])@\/api\/admin\1/g, JSON.stringify(pathToFileURL(`${folder}/admin.mjs`).href))))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'AdminUsers.vue', id: 'admin-users-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, transpile(template.code))
const Component = (await import(pathToFileURL(`${folder}/component.mjs`).href)).default
Component.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render
const user = (id: number, is_admin = false, is_active = true) => ({ id, username: `user${id}`, nickname: '', email: '', is_admin, is_active })
async function settle() { await flush(); await nextTick(); await flush(); await nextTick() }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }
async function mount(options: { get?: (params: any) => Promise<any>; post?: () => Promise<unknown>; confirm?: () => Promise<unknown> } = {}) {
  const requests: any[] = [], posts: string[] = [], confirmations: any[] = []
  Object.assign(globalThis, {
    __userHttp: { get: async (_url: string, { params }: any) => { requests.push(params); return options.get ? options.get(params) : { items: [user(1, true), user(2, true), user(3, false, false)], total: 3 } }, post: async (url: string) => { posts.push(url); return options.post?.() } },
    __userConfirm: async (...args: any[]) => { confirmations.push(args); return options.confirm?.() },
  })
  const container = document.createElement('div'); document.body.append(container)
  const app = createApp(Component); app.use(ElementPlus)
  const vm = app.mount(container) as any; await settle()
  return { container, state: vm.$.setupState, requests, posts, confirmations, close() { app.unmount(); container.remove() } }
}
async function choose(view: Awaited<ReturnType<typeof mount>>, uid: number, text: string) {
  const trigger = view.container.querySelector<HTMLButtonElement>(`button[aria-label="用户 user${uid} 的更多操作"]`)!
  assert.ok(trigger); trigger.click(); await settle()
  const menu = document.getElementById(trigger.getAttribute('aria-controls')!)!
  assert.ok(menu, 'opening more actions must expose its associated menu')
  const item = [...menu.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(item => item.textContent?.includes(text))!
  assert.ok(item, `menu must offer ${text}`); item.click(); await settle()
}
test('failed user loads show retry without claiming the list is empty', async () => {
  let fail = true
  const view = await mount({ get: async () => { if (fail) throw Error('offline'); return { items: [], total: 0 } } })
  try {
    assert.match(view.container.querySelector('[role="alert"]')!.textContent!, /加载失败/)
    assert.doesNotMatch(view.container.textContent!, /暂无用户/)
    fail = false
    const retry = [...view.container.querySelectorAll('button')].find(button => button.textContent?.includes('重新加载'))!
    retry.click(); await settle()
    assert.match(view.container.textContent!, /暂无用户/)
    assert.equal(view.container.querySelector('[role="alert"]'), null)
  } finally { view.close() }
})
test('a slow old page cannot replace the newer user page', async () => {
  const old = deferred<any>()
  const view = await mount({ get: async ({ page }) => page === 2 ? old.promise : { items: [user(page === 3 ? 30 : 10)], total: 30 } })
  try {
    view.state.page = 2; const previous = view.state.load(); await settle()
    view.state.page = 3; await view.state.load(); await settle()
    assert.match(view.container.textContent!, /user30/)
    old.resolve({ items: [user(20)], total: 30 }); await previous; await settle()
    assert.match(view.container.textContent!, /user30/)
    assert.doesNotMatch(view.container.textContent!, /user20/)
    assert.equal(view.state.loading, false)
  } finally { view.close() }
})
test('own account is protected and menus reflect role and status; cancellation makes no request', async () => {
  const view = await mount({ confirm: async () => { throw 'cancel' } })
  try {
    assert.match(view.container.textContent!, /当前账号/)
    assert.equal(view.container.querySelector('button[aria-label="用户 user1 的更多操作"]'), null)
    await view.state.handleToggleAdmin(1); await view.state.handleToggleActive(1)
    assert.equal(view.confirmations.length, 0)
    await choose(view, 2, '取消管理员')
    await choose(view, 2, '禁用账号')
    await choose(view, 3, '启用账号')
    assert.equal(view.confirmations.length, 3)
    assert.deepEqual(view.posts, [])
    assert.equal(view.state.actingId, null)
  } finally { view.close() }
})
test('pending confirmation and API writes prevent duplicate or conflicting user operations', async () => {
  const confirm = deferred<void>(), post = deferred<void>()
  const view = await mount({ confirm: () => confirm.promise, post: () => post.promise })
  try {
    await choose(view, 3, '设为管理员')
    assert.equal(view.state.actingId, 3)
    await view.state.handleToggleAdmin(3); await view.state.handleToggleActive(2)
    assert.equal(view.confirmations.length, 1); assert.deepEqual(view.posts, [])
    confirm.resolve(); await settle()
    assert.deepEqual(view.posts, ['/admin/users/3/toggle-admin'])
    await view.state.handleToggleAdmin(3); await view.state.handleToggleActive(3)
    assert.equal(view.posts.length, 1)
    post.resolve(); await settle()
    assert.equal(view.state.actingId, null)
    assert.equal(view.requests.length, 2)
  } finally { view.close() }
})
