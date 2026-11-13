import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { ApiRequestLog, RequestLogPage } from '../api/requestLogs'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, {
  window: dom.window, document: dom.window.document, Document: dom.window.Document,
  Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement,
  Node: dom.window.Node, MutationObserver: dom.window.MutationObserver,
  Event: dom.window.Event, MouseEvent: dom.window.MouseEvent, getComputedStyle: dom.window.getComputedStyle,
  requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame,
  ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
})
const { createApp, nextTick } = await import('vue')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.request-logs-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })

function compile(source: string) {
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
}
const apiTarget = `${folder}/requestLogs.mjs`
const httpBridge = 'const http = { get: (...args) => globalThis.__requestLogsHttp.get(...args) }'
writeFileSync(apiTarget, compile(readFileSync(new URL('../api/requestLogs.ts', import.meta.url), 'utf8').replace("import http from './http'", httpBridge)))
const { descriptor } = parse(readFileSync(new URL('../components/operations/ApiRequestLogs.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'request-logs-test' })
const source = script.content.replace(/(['"])@\/api\/requestLogs\1/g, JSON.stringify(pathToFileURL(apiTarget).href))
const target = `${folder}/ApiRequestLogs.mjs`
writeFileSync(target, compile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'ApiRequestLogs.vue', id: 'request-logs-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const ApiRequestLogs = (await import(pathToFileURL(target).href)).default
ApiRequestLogs.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render

type State = {
  items: ApiRequestLog[]; page: number; loading: boolean; error: string; filterError: string
  urlFilter: string; methodFilter: string; statusCodeFilter: string
  applyFilters: () => Promise<void>; resetFilters: () => Promise<void>; load: (page?: number) => Promise<void>
  changePage: (page: number) => void
}
type Request = { url: string; params: Record<string, unknown>; signal: AbortSignal }
function log(id: number, extra: Partial<ApiRequestLog> = {}): ApiRequestLog {
  return {
    id, method: 'GET', url: '/api/articles/42?source=home', path: '/api/articles/42',
    query_params: { source: ['home'] }, path_params: { aid: 42 }, body_params: null,
    status_code: 200, duration_ms: 12, created_at: '2026-11-13T08:00:00Z',
    ...extra,
  }
}
function page(items: ApiRequestLog[], total = items.length, number = 1): RequestLogPage {
  return { items, total, page: number, size: 20 }
}
function deferred<T>() {
  let resolve!: (data: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
async function mount(fetch: (params: Request['params']) => Promise<RequestLogPage> = async () => page([log(1)])) {
  const requests: Request[] = []
  Object.assign(globalThis, { __requestLogsHttp: {
    async get(url: string, settings: Omit<Request, 'url'>) {
      requests.push({ url, ...settings })
      return fetch(settings.params)
    },
  } })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(ApiRequestLogs)
  app.use(ElementPlus)
  const instance = app.mount(container) as unknown as { $: { setupState: State } }
  await settle()
  return { container, state: instance.$.setupState, requests, unmount: () => { app.unmount(); container.remove() } }
}

test('submitted URL, method and status filters combine and start from the first page', async (t) => {
  const view = await mount(async (params) => page([log(Number(params.page))], 61, Number(params.page)))
  t.after(view.unmount)
  assert.deepEqual(view.requests.map(({ url, params }) => ({ url, params })), [{ url: '/admin/operations/requests', params: { page: 1, size: 20 } }])
  await view.state.load(3)
  view.state.urlFilter = '  /api/articles/42  '
  view.state.methodFilter = 'GET'
  view.state.statusCodeFilter = '200'
  await settle()
  assert.equal(view.requests.length, 2, 'editing filters waits for explicit submission')
  await view.state.applyFilters()
  assert.equal(view.state.page, 1)
  assert.deepEqual(view.requests.at(-1)?.params, { page: 1, size: 20, url: '/api/articles/42', method: 'GET', status_code: 200 })
  view.state.urlFilter = '/draft-filter'
  view.state.changePage(2)
  await settle()
  assert.deepEqual(view.requests.at(-1)?.params, { page: 2, size: 20, url: '/api/articles/42', method: 'GET', status_code: 200 })
  await view.state.resetFilters()
  assert.deepEqual(view.requests.at(-1)?.params, { page: 1, size: 20 })
  assert.equal(view.state.urlFilter, '')
  assert.equal(view.state.methodFilter, '')
  assert.equal(view.state.statusCodeFilter, '')
})

test('invalid status codes do not send a query and valid full HTTP codes are accepted', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  for (const status of ['2xx', '99', '600', '200.5']) {
    view.state.statusCodeFilter = status
    await view.state.applyFilters()
    assert.match(view.state.filterError, /100.*599/)
  }
  assert.equal(view.requests.length, 1)
  view.state.statusCodeFilter = ' 404 '
  await view.state.applyFilters()
  assert.equal(view.requests.at(-1)?.params.status_code, 404)
  assert.equal(view.state.filterError, '')
})

test('rows show request metadata and expanded details render JSON and explicit empty values safely', async (t) => {
  const view = await mount(async () => page([
    log(1, { body_params: { title: '<script>alert(1)</script>', password: '[REDACTED]' } }),
    log(2, { query_params: {}, path_params: {} }),
    log(3, { status_code: 404 }),
  ]))
  t.after(view.unmount)
  const rows = [...view.container.querySelectorAll<HTMLElement>('tr.el-table__row')]
  assert.equal(rows.length, 3)
  assert.ok(rows[0].textContent?.includes('GET'))
  assert.ok(rows[0].textContent?.includes('/api/articles/42?source=home'))
  assert.ok(rows[0].textContent?.includes('200'))
  assert.ok(rows[2].textContent?.includes('404'))
  assert.ok(rows[0].textContent?.includes('12 ms'))
  rows[0].querySelector<HTMLElement>('.el-table__expand-icon')!.click()
  await settle()
  const firstDetail = view.container.querySelector<HTMLElement>('.request-details')!
  assert.ok(firstDetail.textContent?.includes('查询参数'))
  assert.ok(firstDetail.textContent?.includes('请求 ID：1'))
  assert.ok(firstDetail.textContent?.includes('路径：/api/articles/42'))
  assert.ok(firstDetail.textContent?.includes('"source": [\n    "home"\n  ]'))
  assert.ok(firstDetail.textContent?.includes('"aid": 42'))
  assert.ok(firstDetail.textContent?.includes('<script>alert(1)</script>'))
  assert.ok(firstDetail.textContent?.includes('[REDACTED]'))
  assert.equal(firstDetail.querySelector('script'), null)
  rows[1].querySelector<HTMLElement>('.el-table__expand-icon')!.click()
  await settle()
  const secondDetail = view.container.querySelectorAll<HTMLElement>('.request-details')[1]
  assert.ok(secondDetail.textContent?.includes('无查询参数'))
  assert.ok(secondDetail.textContent?.includes('无路径参数'))
  assert.ok(secondDetail.textContent?.includes('无请求体'))
})

test('the latest query owns rows, errors and loading even when cancelled requests settle later', async (t) => {
  const old = deferred<RequestLogPage>()
  const middle = deferred<RequestLogPage>()
  const latest = deferred<RequestLogPage>()
  const view = await mount((params) => params.method === 'POST' ? latest.promise : params.method === 'GET' ? middle.promise : old.promise)
  t.after(view.unmount)
  view.state.methodFilter = 'GET'
  const middleQuery = view.state.applyFilters()
  assert.equal(view.requests[0].signal.aborted, true)
  old.resolve(page([log(1)]))
  await settle()
  assert.equal(view.state.loading, true)
  assert.equal(view.state.items.length, 0)
  view.state.methodFilter = 'POST'
  const latestQuery = view.state.applyFilters()
  assert.equal(view.requests[1].signal.aborted, true)
  latest.resolve(page([log(3, { method: 'POST' })]))
  await latestQuery
  middle.reject(new Error('late failure'))
  await middleQuery
  await settle()
  assert.deepEqual(view.state.items.map((item) => item.id), [3])
  assert.equal(view.state.loading, false)
  assert.equal(view.state.error, '')
})

test('failed queries expose retry using the applied filters and empty results explain the state', async (t) => {
  let fail = false
  const view = await mount(async () => { if (fail) throw new Error('offline'); return page([]) })
  t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('暂无符合条件的请求记录'))
  fail = true
  view.state.methodFilter = 'DELETE'
  await view.state.applyFilters()
  await settle()
  assert.ok(view.container.querySelector('[role="alert"]')?.textContent?.includes('请求记录加载失败'))
  view.state.methodFilter = 'POST'
  fail = false
  const retry = [...view.container.querySelectorAll('button')].find((button) => button.textContent?.trim() === '重试')!
  retry.click()
  await settle()
  assert.deepEqual(view.requests.at(-1)?.params, { page: 1, size: 20, method: 'DELETE' })
  assert.equal(view.state.error, '')
})

test('unmount aborts the current request and ignores its eventual response', async () => {
  const pending = deferred<RequestLogPage>()
  const view = await mount(() => pending.promise)
  view.unmount()
  assert.equal(view.requests[0].signal.aborted, true)
  pending.resolve(page([log(7)]))
  await settle()
  assert.equal(view.state.items.length, 0)
})
