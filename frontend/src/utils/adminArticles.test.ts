import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
const dom = new JSDOM('<html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, Document: dom.window.Document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node, MutationObserver: dom.window.MutationObserver, getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame, ResizeObserver: class { observe() {} unobserve() {} disconnect() {} } })
const { createApp, nextTick } = await import('vue')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.admin-articles-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const transpile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const bridge = 'const http = { get: (...args) => globalThis.__articleHttp.get(...args), post: (...args) => globalThis.__articleHttp.post(...args), delete: (...args) => globalThis.__articleHttp.delete(...args) }'
writeFileSync(`${folder}/admin.mjs`, transpile(readFileSync(new URL('../api/admin.ts', import.meta.url), 'utf8').replace("import http from './http'", bridge)))
const { descriptor } = parse(readFileSync(new URL('../views/AdminArticles.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'admin-articles-test' })
writeFileSync(`${folder}/component.mjs`, transpile(script.content.replace("import { ElMessage, ElMessageBox } from 'element-plus'", 'const ElMessage = { success() {} }; const ElMessageBox = { confirm: async () => {} }').replace(/(['"])@\/api\/admin\1/g, JSON.stringify(pathToFileURL(`${folder}/admin.mjs`).href))))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'AdminArticles.vue', id: 'admin-articles-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, transpile(template.code))
const Component = (await import(pathToFileURL(`${folder}/component.mjs`).href)).default
Component.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render
const row = { id: 1, title: '文章', slug: 'a', deleted_at: null, is_published: true, view_count: 0, created_at: '', author: { id: 1, username: 'a' } }
async function settle() { await flush(); await nextTick(); await flush(); await nextTick() }
async function mount(get: (params: any) => Promise<any> = async () => ({ items: [row], total: 1 })) {
  const requests: any[] = [], posts: string[] = []
  Object.assign(globalThis, { __articleHttp: { get: async (_: string, { params }: any) => { requests.push(params); return get(params) }, post: async (url: string) => { posts.push(url) }, delete: async () => {} } })
  const container = document.createElement('div'); document.body.append(container)
  const app = createApp(Component); app.use(ElementPlus)
  const vm = app.mount(container) as any; await settle()
  return { container, state: vm.$.setupState, requests, posts, close() { app.unmount(); container.remove() } }
}
test('search and recycle filter reset pagination and offer recoverable deletion', async () => {
  const view = await mount(); try {
    view.state.page = 4; view.state.keyword = 'vue'; await view.state.search(); await settle()
    assert.equal(view.requests.at(-1).page, 1)
    view.state.status = 'trash'; await settle()
    assert.equal(view.requests.at(-1).status, 'trash')
    assert.match(view.container.textContent!, /恢复/)
    assert.doesNotMatch(view.container.textContent!, /永久删除|不可恢复/)
    await view.state.handleRestore(1); assert.deepEqual(view.posts, ['/admin/articles/1/restore'])
  } finally { view.close() }
})
test('errors display retry and an empty removed last page moves backward', async () => {
  let fail = true
  const view = await mount(async (params) => { if (fail) throw new Error('network'); return { items: params.page > 1 ? [] : [row], total: 1 } })
  try {
    assert.match(view.container.textContent!, /重新加载/)
    fail = false; view.state.page = 2; await view.state.load(); await settle()
    assert.equal(view.state.page, 1); assert.equal(view.state.list.length, 1)
  } finally { view.close() }
})
test('a slow old response cannot overwrite a newer article search', async () => {
  let finish!: (data: any) => void
  const view = await mount(async (params) => params.q === 'old' ? new Promise(resolve => { finish = resolve }) : { items: [{ ...row, title: params.q || 'initial' }], total: 1 })
  try {
    view.state.keyword = 'old'; view.state.search(); await settle()
    view.state.keyword = 'new'; view.state.search(); await settle()
    finish({ items: [{ ...row, title: 'old' }], total: 1 }); await settle()
    assert.match(view.container.textContent!, /new/)
    assert.doesNotMatch(view.container.textContent!, /old/)
  } finally { view.close() }
})
