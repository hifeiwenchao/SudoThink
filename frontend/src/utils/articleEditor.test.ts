import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, Document: dom.window.Document, Element: dom.window.Element,
  HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node, MutationObserver: dom.window.MutationObserver,
  MouseEvent: dom.window.MouseEvent, getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame,
  cancelAnimationFrame: dom.window.cancelAnimationFrame, ResizeObserver: class { observe() {} unobserve() {} disconnect() {} } })
const { createApp, nextTick, reactive } = await import('vue')
const { default: ElementPlus } = await import('element-plus')
const { setSession, expireSession } = await import('./session')
const { readArticleDraft, writeArticleDraft } = await import('./articleDraft')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.article-editor-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const compile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { descriptor } = parse(readFileSync(new URL('../views/ArticleEditView.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'article-editor-test' })
let source = script.content
  .replace("import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'", 'const useRoute = () => globalThis.__editor.route; const useRouter = () => globalThis.__editor.router; const onBeforeRouteLeave = (fn) => globalThis.__editor.leave = fn; const onBeforeRouteUpdate = (fn) => globalThis.__editor.update = fn')
  .replace("import { ElMessage, ElMessageBox } from 'element-plus'", 'const ElMessage = { success() {}, warning(message) { globalThis.__editor.warnings.push(message) } }; const ElMessageBox = { confirm: async () => true }')
  .replace(/import \{ articleApi, type Article \} from ['"]@\/api\/article['"]/, 'const articleApi = { create: (...args) => globalThis.__editor.save(...args), update: (id, ...args) => globalThis.__editor.save(...args) }')
  .replace("import { adminApi } from '@/api/admin'", 'const adminApi = { articleDetail: (...args) => globalThis.__editor.detail(...args) }')
  .replace(/import \{ taxonomyApi, type Category, type TaxonomyItem \} from ['"]@\/api\/taxonomy['"]/, 'const taxonomyApi = { categories: async () => [], tags: async () => [] }')
  .replace(/import (RichTextEditor|MediaUpload|ArticleContent) from ['"]@\/components\/[^'"]+['"]/g, 'const $1 = { template: "<div />" }')
  .replace(/(['"])@\/utils\/([^'"]+)\1/g, (_, _quote, name) => JSON.stringify(pathToFileURL(fileURLToPath(new URL(`./${name}.ts`, import.meta.url))).href))
writeFileSync(`${folder}/editor.mjs`, compile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'ArticleEditView.vue', id: 'article-editor-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const Editor = (await import(pathToFileURL(`${folder}/editor.mjs`).href)).default
Editor.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render
const article = (id: number) => ({ id, title: `服务器${id}`, summary: '', content: '<p>正文</p>', cover: '', category: null, tags: [], is_published: false })
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
async function mount(id: number | null = null, userId = 1, detail: (id: number) => Promise<any> = async (id) => article(id)) {
  setSession(`token-${userId}`, { id: userId, is_admin: true } as any)
  const state = { route: reactive({ params: { id: id ? String(id) : undefined } }), router: { replace: async () => {}, push: async () => {} }, detail,
    save: async (payload: any) => ({ ...article(id || 8), ...payload }), warnings: [] as string[], leave: null as any, update: null as any }
  Object.assign(globalThis, { __editor: state })
  const container = document.createElement('div'); document.body.append(container)
  const app = createApp(Editor); app.use(ElementPlus)
  const view = app.mount(container) as any
  await settle()
  return { ...state, container, state: view.$.setupState, unmount() { app.unmount(); container.remove() } }
}
const form = { title: '本地恢复标题', summary: '摘要', content: '<p>本地正文</p>', cover: '', category_id: null, tag_ids: [3] }
test('first load and untouched blank editor never create drafts', async () => {
  window.localStorage.clear()
  const view = await mount(); await new Promise((r) => setTimeout(r, 650)); view.unmount()
  assert.equal(readArticleDraft(1, null), null)
  const existing = await mount(2); existing.unmount()
  assert.equal(readArticleDraft(1, 2), null)
})
test('recovery requires explicit choice, isolates user, preserves baseline and clears saved draft', async () => {
  window.localStorage.clear(); writeArticleDraft(1, 2, form, 'old-server')
  const other = await mount(2, 9); assert.equal(other.state.recoveryDraft, null); other.unmount()
  const view = await mount(2)
  assert.equal(view.state.form.title, '服务器2')
  assert.match(view.container.textContent || '', /服务器文章已发生变化/)
  const restore = [...view.container.querySelectorAll('button')].find((b) => b.textContent?.includes('恢复本地草稿'))!
  restore.click(); await settle()
  assert.equal(view.state.form.title, form.title)
  assert.equal(view.state.form.summary, form.summary)
  assert.deepEqual([...view.state.form.tag_ids], [3])
  await view.state.submit(false)
  assert.equal(readArticleDraft(1, 2), null)
  view.unmount(); assert.equal(readArticleDraft(1, 2), null)
})
test('final keystrokes flush before session expiry and pending route loads never cross draft keys', async () => {
  window.localStorage.clear()
  let resolve!: (value: any) => void
  const pending = new Promise((r) => { resolve = r })
  const view = await mount(2, 1, async (id) => id === 3 ? pending : article(id))
  const input = view.container.querySelector<HTMLInputElement>('#article-title')!
  input.value = '最后输入'; input.dispatchEvent(new dom.window.Event('input', { bubbles: true })); await nextTick()
  expireSession('token-1')
  assert.equal(readArticleDraft(1, 2)?.form.title, '最后输入')
  view.route.params.id = '3'; await settle()
  view.route.params.id = '4'; await settle()
  resolve(article(3)); await settle()
  assert.equal(view.state.form.title, '服务器4')
  assert.equal(readArticleDraft(1, 3), null)
  view.state.form.summary = '第四篇修改'
  view.unmount()
  assert.equal(readArticleDraft(1, 4)?.form.summary, '第四篇修改')
  assert.equal(readArticleDraft(1, 2)?.form.title, '最后输入')
})
test('discard leaves server form intact; denied storage warns once and still allows server save', async () => {
  window.localStorage.clear(); writeArticleDraft(1, 2, form, 'baseline')
  const view = await mount(2)
  view.state.discardDraft(); assert.equal(view.state.form.title, '服务器2'); assert.equal(readArticleDraft(1, 2), null)
  const storage = window.localStorage
  Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw Error('disabled') } })
  view.state.form.title = '继续编辑'; view.state.flushDraft(); view.state.flushDraft()
  assert.equal(view.warnings.length, 1)
  await view.state.submit(false); assert.equal(view.state.isDirty, false)
  view.unmount(); Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
})
