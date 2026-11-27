import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { AdminComment, AdminArticleBrief, PageResp } from '../api/admin'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, {
  window: dom.window, document: dom.window.document, Document: dom.window.Document,
  Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement,
  Node: dom.window.Node, MutationObserver: dom.window.MutationObserver,
  MouseEvent: dom.window.MouseEvent,
  Event: dom.window.Event, CustomEvent: dom.window.CustomEvent, KeyboardEvent: dom.window.KeyboardEvent, FocusEvent: dom.window.FocusEvent,
  HTMLInputElement: dom.window.HTMLInputElement, HTMLButtonElement: dom.window.HTMLButtonElement,
  getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame,
  cancelAnimationFrame: dom.window.cancelAnimationFrame,
  ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
})
const { createApp, nextTick } = await import('vue')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.admin-comments-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })

function compile(source: string) {
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
}
const httpBridge = 'const http = { get: (...args) => globalThis.__adminCommentHttp.get(...args), post: (...args) => globalThis.__adminCommentHttp.post(...args) }'
const apiTarget = `${folder}/admin.mjs`
writeFileSync(apiTarget, compile(readFileSync(new URL('../api/admin.ts', import.meta.url), 'utf8').replace("import http from './http'", httpBridge)))
const { descriptor } = parse(readFileSync(new URL('../views/AdminComments.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'admin-comments-test' })
const source = script.content
  .replace("import { ElMessage, ElMessageBox } from 'element-plus'", "import { ElMessageBox as ActualMessageBox } from 'element-plus'; const ElMessage = { success() {} }; const ElMessageBox = { confirm: (...args) => globalThis.__commentConfirm ? globalThis.__commentConfirm(...args) : ActualMessageBox.confirm(...args) }")
  .replace(/(['"])@\/api\/admin\1/g, JSON.stringify(pathToFileURL(apiTarget).href))
  .replace("import http from '@/api/http'", httpBridge)
  .replace("import { PUBLIC_SITE_URL } from '@/site'", "const PUBLIC_SITE_URL = 'https://public.example.net/'")
const target = `${folder}/AdminComments.mjs`
writeFileSync(target, compile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'AdminComments.vue', id: 'admin-comments-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const AdminComments = (await import(pathToFileURL(target).href)).default
AdminComments.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render

type Request = { url: string; params: Record<string, unknown> }
type State = {
  page: number; articleId: number; status: string; list: AdminComment[]; total: number; loading: boolean
  actingId: number | null; articleOptions: AdminArticleBrief[]; articlesLoading: boolean
  load: () => Promise<void>; searchArticles: (query: string) => Promise<void>
  handleApprove: (id: number) => Promise<void>; handleReject: (id: number) => Promise<void>
  selectedIds: number[]; batchBusy: boolean; reviewBatch(action: 'approve' | 'reject'): Promise<void>
}
const article = { deleted_at: null, id: 42, title: '相关文章', slug: 'article', is_published: true, view_count: 0, created_at: '2026-11-12T08:00:00Z', author: { id: 1, username: 'admin' } }
function comment(id: number, status: AdminComment['status'] = 'pending'): AdminComment {
  return {
    id, status, is_approved: status === 'approved', content: `评论 ${id}`, nickname: '访客',
    email: 'private@example.com', ip_address: '203.0.113.7', location: '浙江省杭州市',
    location_detail: '浙江省杭州市西湖区',
    user_agent: id === 3 ? '' : 'TestBrowser/1.0 (Linux)',
    created_at: '2026-11-12T08:00:00Z', article, author: null,
  }
}
function page(items: AdminComment[], total = items.length, number = 1): PageResp<AdminComment> {
  return { items, total, page: number, size: 10 }
}
function deferred<T>() {
  let resolve!: (data: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
async function mount(options: {
  comments?: (params: Request['params']) => Promise<PageResp<AdminComment>>
  articles?: (params: Request['params']) => Promise<PageResp<AdminArticleBrief>>
  post?: (url: string, body?: unknown) => Promise<unknown>
  confirm?: () => Promise<unknown>
  realConfirm?: boolean
} = {}) {
  const requests: Request[] = []
  const posts: string[] = []
  const bodies: unknown[] = []
  Object.assign(globalThis, { __commentConfirm: options.realConfirm ? null : options.confirm ?? (() => Promise.resolve()) })
  Object.assign(globalThis, { __adminCommentHttp: {
    async get(url: string, { params }: { params: Request['params'] }) {
      requests.push({ url, params })
      if (url === '/admin/articles') return options.articles?.(params) ?? { items: [article], total: 1, page: 1, size: 100 }
      return options.comments?.(params) ?? page([comment(1)])
    },
    async post(url: string, body?: unknown) { posts.push(url); bodies.push(body); return options.post?.(url, body) },
  } })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(AdminComments)
  app.use(ElementPlus)
  const instance = app.mount(container) as unknown as { $: { setupState: State } }
  await settle()
  return { container, state: instance.$.setupState, requests, posts, bodies, unmount: () => { app.unmount(); container.remove() } }
}
function commentRequests(requests: Request[]) { return requests.filter((request) => request.url.startsWith('/admin/comments')) }

test('batch review uses current-page selection and retains it after failure for retry', async t => {
  let fail = true
  const view = await mount({ comments: async () => page([comment(1), comment(2)]), post: async () => { if (fail) throw new Error('offline') } })
  t.after(view.unmount)
  const checkbox = view.container.querySelector<HTMLInputElement>('tr.el-table__row input[type="checkbox"]')
  assert.ok(checkbox, 'desktop rows offer selection')
  checkbox.click()
  await settle()
  assert.deepEqual(view.state.selectedIds, [1])
  await view.state.reviewBatch('approve')
  assert.deepEqual(view.state.selectedIds, [1])
  assert.ok(view.container.querySelector('[role="alert"]'))
  fail = false
  await view.state.reviewBatch('reject')
  assert.deepEqual(view.bodies, [{ ids: [1], action: 'approve' }, { ids: [1], action: 'reject' }])
  assert.deepEqual(view.state.selectedIds, [])
})

test('batch confirmation is exclusive, cancellation posts nothing, and filters clear selection', async t => {
  const gate = deferred<void>()
  const view = await mount({ confirm: () => gate.promise })
  t.after(view.unmount)
  view.state.selectedIds = [1]
  const pending = view.state.reviewBatch('approve')
  await view.state.reviewBatch('reject')
  await view.state.handleApprove(1)
  assert.equal(view.state.batchBusy, true)
  assert.deepEqual(view.posts, [])
  gate.reject(new Error('cancel'))
  await pending
  assert.deepEqual(view.state.selectedIds, [1])
  view.state.status = 'pending'
  await settle()
  assert.deepEqual(view.state.selectedIds, [])
})

test('mobile comments open private context in an accessible details drawer', async t => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
  const view = await mount()
  t.after(() => { view.unmount(); Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 }) })
  const card = view.container.querySelector('.comment-card')
  assert.ok(card)
  assert.equal(view.container.querySelector('.el-table'), null)
  assert.ok(card.querySelector('input[type="checkbox"]'))
  assert.equal(card.textContent?.includes('203.0.113.7'), false)
  card.querySelector<HTMLButtonElement>('button[aria-label="查看评论 1 详情"]')!.click()
  await settle()
  const drawer = document.body.querySelector('.comment-detail-drawer')
  assert.ok(drawer)
  assert.ok(drawer.textContent?.includes('203.0.113.7'))
  drawer.querySelector<HTMLButtonElement>('.el-drawer__close-btn')!.click()
  await settle()
  assert.ok(card.textContent?.includes('评论 1'))
})

test('the real bulk confirmation posts only after explicit confirmation', async t => {
  const view = await mount({ realConfirm: true })
  t.after(view.unmount)
  view.container.querySelector<HTMLInputElement>('tr.el-table__row input[type="checkbox"]')!.click()
  await settle()
  const bulk = [...view.container.querySelectorAll<HTMLButtonElement>('button')].find(item => item.textContent?.trim() === '批量通过')!
  bulk.click()
  await settle()
  assert.deepEqual(view.posts, [])
  const box = document.body.querySelector('.el-message-box')!
  assert.match(box.textContent ?? '', /选中的 1 条评论/)
  ;[...box.querySelectorAll<HTMLButtonElement>('button')].find(item => item.textContent?.trim() === '确认')!.click()
  await settle()
  assert.deepEqual(view.posts, ['/admin/comments/batch-review'])
  assert.deepEqual(view.bodies, [{ ids: [1], action: 'approve' }])
})

test('details remain available during a batch and show its completed moderation state', async t => {
  const gate = deferred<void>()
  const view = await mount({ post: () => gate.promise })
  t.after(view.unmount)
  view.state.status = 'pending'
  await settle()
  view.state.selectedIds = [1]
  const pending = view.state.reviewBatch('approve')
  await settle()
  const more = view.container.querySelector<HTMLButtonElement>('button[aria-label="查看评论 1 详情"]')!
  assert.equal(more.disabled, false)
  more.click()
  await settle()
  const drawer = [...document.body.querySelectorAll('.comment-detail-drawer')].at(-1)!
  assert.ok(drawer.textContent?.includes('待审核'))
  gate.resolve()
  await pending
  await settle()
  assert.ok(drawer.textContent?.includes('已通过'))
})

test('a completed batch refreshes the current filter while retaining its valid selection', async t => {
  const gate = deferred<void>()
  let reviewed = false
  const view = await mount({ comments: async params => page(params.status === 'approved' ? (reviewed ? [comment(1, 'approved'), comment(2, 'approved')] : [comment(2, 'approved')]) : [comment(1)]), post: async () => { await gate.promise; reviewed = true } })
  t.after(view.unmount)
  view.state.selectedIds = [1]
  const pending = view.state.reviewBatch('approve')
  await settle()
  view.state.status = 'approved'
  await settle()
  const requests = view.requests.length
  view.state.selectedIds = [2]
  gate.resolve()
  await pending
  assert.deepEqual(view.state.selectedIds, [2])
  assert.equal(view.requests.length, requests + 1)
  assert.deepEqual(view.state.list.map(item => item.id), [1, 2])
  assert.equal(commentRequests(view.requests).at(-1)?.params.status, 'approved')
  assert.equal(view.container.querySelector<HTMLInputElement>('tr.el-table__row:nth-child(2) input[type="checkbox"]')?.checked, true)
})

test('switching mobile and desktop clears selection so rendered checkboxes match the count', async t => {
  const view = await mount()
  t.after(() => { view.unmount(); Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 }) })
  view.container.querySelector<HTMLInputElement>('tr.el-table__row input[type="checkbox"]')!.click()
  await settle()
  assert.deepEqual(view.state.selectedIds, [1])
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
  window.dispatchEvent(new dom.window.Event('resize'))
  await settle()
  assert.deepEqual(view.state.selectedIds, [])
  view.container.querySelector<HTMLInputElement>('.comment-card input[type="checkbox"]')!.click()
  await settle()
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 })
  window.dispatchEvent(new dom.window.Event('resize'))
  await settle()
  assert.deepEqual(view.state.selectedIds, [])
  assert.equal(view.container.querySelector<HTMLInputElement>('tr.el-table__row input[type="checkbox"]')?.checked, false)
})

test('article and status filters combine on the unified endpoint and reset the page', async (t) => {
  const view = await mount({ comments: async (params) => page([comment(Number(params.page))], 31, Number(params.page)) })
  t.after(view.unmount)
  assert.deepEqual(commentRequests(view.requests), [{ url: '/admin/comments', params: { page: 1, size: 10 } }])
  assert.ok(view.container.textContent?.includes('评论管理'))
  view.state.page = 3
  await view.state.load()
  view.state.articleId = 42
  view.state.status = 'rejected'
  await settle()
  assert.equal(view.state.page, 1)
  assert.deepEqual(commentRequests(view.requests).at(-1), { url: '/admin/comments', params: { page: 1, size: 10, article_id: 42, status: 'rejected' } })
  view.state.articleId = 0
  view.state.status = 'all'
  await settle()
  assert.deepEqual(commentRequests(view.requests).at(-1), { url: '/admin/comments', params: { page: 1, size: 10 } })
})

test('status tags and available review actions match each row, with public links only for published articles', async (t) => {
  const view = await mount({ comments: async () => page([
    comment(1), { ...comment(2, 'approved'), location_detail: '' },
    { ...comment(3, 'rejected'), location: '', location_detail: '', article: { ...article, id: 43, title: '草稿文章', is_published: false } },
  ]) })
  t.after(view.unmount)
  const rows = [...view.container.querySelectorAll<HTMLElement>('tr.el-table__row')]
  assert.equal(rows.length, 3)
  assert.ok(rows[0].textContent?.includes('待审核'))
  assert.ok(rows[1].textContent?.includes('已通过'))
  assert.ok(rows[2].textContent?.includes('已驳回'))
  assert.deepEqual(rows.map((row) => [...row.querySelectorAll('button')].map((button) => button.textContent?.trim())), [['通过', '驳回', '更多'], ['驳回', '更多'], ['通过', '更多']])
  assert.equal(rows[0].querySelector('a')?.href, 'https://public.example.net/articles/42')
  assert.equal(rows[2].querySelector('a'), null)
  assert.ok(rows[2].textContent?.includes('草稿'))
  assert.equal(rows[0].textContent?.includes('private@example.com'), false)
  assert.equal(rows[0].textContent?.includes('203.0.113.7'), false)
  rows[0].querySelector<HTMLButtonElement>('button[aria-label="查看评论 1 详情"]')!.click()
  await settle()
  const drawer = [...document.body.querySelectorAll('.comment-detail-drawer')].at(-1)!
  assert.ok(drawer.textContent?.includes('private@example.com'))
  assert.ok(drawer.textContent?.includes('浙江省杭州市西湖区'))
  assert.ok(drawer.textContent?.includes('TestBrowser/1.0 (Linux)'))
})

test('reviewing the last item keeps active filters and returns to a valid page without duplicate actions', async (t) => {
  let reviewed = false
  const finish = deferred<void>()
  const view = await mount({
    comments: async (params) => page(Number(params.page) === 2 ? (reviewed ? [] : [comment(11)]) : [comment(1)], reviewed ? 10 : 11, Number(params.page)),
    post: async () => { await finish.promise; reviewed = true },
  })
  t.after(view.unmount)
  view.state.articleId = 42
  view.state.status = 'pending'
  await settle()
  view.state.page = 2
  await view.state.load()
  const action = view.state.handleApprove(11)
  await view.state.handleReject(11)
  assert.equal(view.state.actingId, 11)
  assert.deepEqual(view.posts, ['/comments/11/approve'])
  finish.resolve()
  await action
  await settle()
  assert.equal(view.state.page, 1)
  assert.equal(view.state.list[0].id, 1)
  assert.equal(view.state.actingId, null)
  assert.deepEqual(commentRequests(view.requests).slice(-2), [
    { url: '/admin/comments', params: { page: 2, size: 10, article_id: 42, status: 'pending' } },
    { url: '/admin/comments', params: { page: 1, size: 10, article_id: 42, status: 'pending' } },
  ])
})

test('approved comments can be rejected and rejected comments can be approved again', async (t) => {
  let current = comment(7, 'approved')
  const view = await mount({ comments: async () => page([current]), post: async (url) => { current = comment(7, url.endsWith('/reject') ? 'rejected' : 'approved') } })
  t.after(view.unmount)
  await view.state.handleReject(7)
  assert.equal(view.state.list[0].status, 'rejected')
  await view.state.handleApprove(7)
  assert.equal(view.state.list[0].status, 'approved')
  assert.deepEqual(view.posts, ['/comments/7/reject', '/comments/7/approve'])
})

test('older list responses and failures cannot replace a newer filter result or clear its loading state', async (t) => {
  const first = deferred<PageResp<AdminComment>>()
  const second = deferred<PageResp<AdminComment>>()
  const third = deferred<PageResp<AdminComment>>()
  const view = await mount({ comments: (params) => params.status === 'rejected' ? third.promise : params.status === 'approved' ? second.promise : first.promise })
  t.after(view.unmount)
  view.state.status = 'approved'
  await settle()
  first.resolve(page([comment(1)]))
  await settle()
  assert.equal(view.state.loading, true)
  assert.equal(view.state.list.length, 0)
  view.state.status = 'rejected'
  await settle()
  third.resolve(page([comment(3, 'rejected')]))
  await settle()
  second.reject(new Error('old request failed'))
  await settle()
  assert.equal(view.state.loading, false)
  assert.deepEqual(view.state.list.map((item) => item.id), [3])
  assert.equal(view.container.querySelector('[role="alert"]'), null)
})

test('failed list requests show a retry and failed reviews keep the row available for another attempt', async (t) => {
  let failList = true
  let failReview = true
  const view = await mount({
    comments: async () => { if (failList) throw new Error('offline'); return page([comment(1)]) },
    post: async () => { if (failReview) throw new Error('cannot review') },
  })
  t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('评论加载失败'))
  failList = false
  const retry = [...view.container.querySelectorAll('button')].find((button) => button.textContent?.trim() === '重试')!
  retry.click()
  await settle()
  assert.equal(view.state.list[0].id, 1)
  await view.state.handleReject(1)
  await settle()
  assert.equal(view.state.actingId, null)
  assert.equal(view.state.list[0].id, 1)
  assert.ok(view.container.textContent?.includes('审核失败'))
  failReview = false
  await view.state.handleReject(1)
  assert.deepEqual(view.posts, ['/comments/1/reject', '/comments/1/reject'])
})

test('remote article search includes drafts and only the latest query updates the options', async (t) => {
  const slow = deferred<PageResp<AdminArticleBrief>>()
  const view = await mount({ articles: async (params) => params.q === '旧搜索' ? slow.promise : { items: [{ ...article, id: 43, title: String(params.q || '初始文章'), is_published: false }], total: 1, page: 1, size: 100 } })
  t.after(view.unmount)
  assert.deepEqual(view.requests.find((request) => request.url === '/admin/articles'), { url: '/admin/articles', params: { page: 1, size: 100, q: undefined, status: 'all' } })
  const older = view.state.searchArticles('旧搜索')
  const newer = view.state.searchArticles('  新搜索  ')
  await newer
  slow.resolve({ items: [article], total: 1, page: 1, size: 100 })
  await older
  assert.deepEqual(view.state.articleOptions.map((item) => [item.title, item.is_published]), [['新搜索', false]])
  assert.equal(view.state.articlesLoading, false)
  assert.deepEqual(view.requests.at(-1), { url: '/admin/articles', params: { page: 1, size: 100, q: '新搜索', status: 'all' } })
})
