import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after, beforeEach } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { CdnConfiguration, CdnOperation, CdnSubmission, CdnTaskPage } from '../api/operations'

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
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.admin-operations-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
beforeEach(() => { window.localStorage.clear() })

function compile(source: string) {
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
}
const apiTarget = `${folder}/operations.mjs`
const utilityTarget = `${folder}/cdnOperations.mjs`
const requestLogsTarget = `${folder}/requestLogs.mjs`
const httpBridge = 'const http = { get: (...args) => globalThis.__operationsHttp.get(...args), post: (...args) => globalThis.__operationsHttp.post(...args) }'
writeFileSync(apiTarget, compile(readFileSync(new URL('../api/operations.ts', import.meta.url), 'utf8').replace("import http from './http'", httpBridge)))
writeFileSync(utilityTarget, compile(readFileSync(new URL('./cdnOperations.ts', import.meta.url), 'utf8')))
writeFileSync(requestLogsTarget, compile(readFileSync(new URL('../api/requestLogs.ts', import.meta.url), 'utf8').replace("import http from './http'", httpBridge)))
const requestsDescriptor = parse(readFileSync(new URL('../components/operations/ApiRequestLogs.vue', import.meta.url), 'utf8')).descriptor
const requestsScript = compileScript(requestsDescriptor, { id: 'operations-requests-test' })
const requestsTarget = `${folder}/ApiRequestLogs.mjs`
writeFileSync(requestsTarget, compile(requestsScript.content.replace(/(['"])@\/api\/requestLogs\1/g, JSON.stringify(pathToFileURL(requestLogsTarget).href))))
const requestsTemplate = compileTemplate({ source: requestsDescriptor.template!.content, filename: 'ApiRequestLogs.vue', id: 'operations-requests-test', compilerOptions: { bindingMetadata: requestsScript.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/requests-template.mjs`, compile(requestsTemplate.code))
const ApiRequestLogs = (await import(pathToFileURL(requestsTarget).href)).default
ApiRequestLogs.render = (await import(pathToFileURL(`${folder}/requests-template.mjs`).href)).render
Object.assign(globalThis, { __ApiRequestLogsComponent: ApiRequestLogs })
const { descriptor } = parse(readFileSync(new URL('../views/AdminOperations.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'admin-operations-test' })
const source = script.content
  .replace(/(['"])@\/api\/operations\1/g, JSON.stringify(pathToFileURL(apiTarget).href))
  .replace(/(['"])@\/utils\/cdnOperations\1/g, JSON.stringify(pathToFileURL(utilityTarget).href))
  .replace("import ApiRequestLogs from '@/components/operations/ApiRequestLogs.vue'", 'const ApiRequestLogs = globalThis.__ApiRequestLogsComponent')
const target = `${folder}/AdminOperations.mjs`
writeFileSync(target, compile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'AdminOperations.vue', id: 'admin-operations-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const AdminOperations = (await import(pathToFileURL(target).href)).default
AdminOperations.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render

const config: CdnConfiguration = { enabled: true, cdn_base_url: 'https://cdn.example.com', refresh_types: ['File', 'Directory', 'Regex'], limits: { refresh_file: 1000, refresh_directory: 100, refresh_regex: 1, preload: 100, max_url_length: 1024 } }
const result: CdnSubmission = { task_id: '12345,12346', request_id: 'submit-request' }
function taskPage(id = '12345'): CdnTaskPage {
  return { items: [{ task_id: id, object_path: 'https://cdn.example.com/a.png', object_type: 'file', status: 'Complete', process: '100%', creation_time: '2026-11-12T08:00:00Z' }], total: 1, page: 1, size: 20, request_id: 'query-request' }
}
type State = { input: string; operation: CdnOperation; queryTaskId: string; submitting: boolean; inputError: string; submission: CdnSubmission | null; urlHistory: string[]; submit: () => Promise<void>; loadTasks: (page?: number) => Promise<void>; querySubmittedTask: (id: string) => void }
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
async function mount(options: { config?: CdnConfiguration; configError?: boolean; post?: () => Promise<CdnSubmission>; tasks?: (params: Record<string, unknown>) => Promise<CdnTaskPage> } = {}) {
  const gets: { url: string; params?: Record<string, unknown> }[] = []
  const posts: { url: string; data: unknown }[] = []
  Object.assign(globalThis, { __operationsHttp: {
    async get(url: string, settings: { params?: Record<string, unknown> }) {
      gets.push({ url, params: settings.params })
      if (url.endsWith('/config') && options.configError) throw new Error('CDN unavailable')
      if (url === '/admin/operations/requests') return { items: [], total: 0, page: 1, size: 20 }
      return url.endsWith('/config') ? options.config ?? config : options.tasks?.(settings.params ?? {}) ?? taskPage()
    },
    async post(url: string, data: unknown) { posts.push({ url, data }); return options.post ? options.post() : result },
  } })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(AdminOperations)
  app.use(ElementPlus)
  const instance = app.mount(container) as unknown as { $: { setupState: State } }
  await settle()
  return { container, state: instance.$.setupState, gets, posts, unmount: () => { app.unmount(); container.remove() } }
}

test('refresh submissions preserve regex patterns and query each returned task ID separately', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  view.state.operation = 'Regex'
  view.state.input = 'https://cdn.example.com/images/[^/]*[0-9].*.jpg?size=[0-9]'
  await view.state.submit()
  await settle()
  assert.deepEqual(view.posts, [{ url: '/admin/operations/cdn/refresh', data: { object_type: 'Regex', urls: [view.state.input] } }])
  assert.deepEqual(view.gets.at(-1), { url: '/admin/operations/cdn/tasks', params: { task_id: '12345', page: 1, size: 20 } })
  assert.ok(view.container.textContent?.includes('正则刷新已提交'))
  assert.ok(view.container.textContent?.includes('已完成'))
  view.state.querySubmittedTask('12346')
  await settle()
  assert.equal(view.gets.at(-1)?.params?.task_id, '12346')
})

test('request records remain accessible when CDN configuration fails', async (t) => {
  const view = await mount({ configError: true })
  t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('配置加载失败'))
  const requestsTab = [...view.container.querySelectorAll<HTMLElement>('[role="tab"]')].find((tab) => tab.textContent?.trim() === 'API 请求记录')
  assert.ok(requestsTab, '运维管理应提供独立的 API 请求记录页签')
  requestsTab.click()
  await settle()
  assert.ok(view.gets.some((request) => request.url === '/admin/operations/requests'))
  assert.ok(view.container.textContent?.includes('URL 包含'))
})

test('directory errors prevent submission and preloading uses its own endpoint', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  view.state.operation = 'Directory'
  view.state.input = 'https://cdn.example.com/images'
  await view.state.submit()
  assert.equal(view.posts.length, 0)
  assert.match(view.state.inputError, /以 \/ 结尾/)
  view.state.operation = 'Preload'
  view.state.input = 'https://cdn.example.com/a.png\nhttps://cdn.example.com/a.png'
  await view.state.submit()
  assert.deepEqual(view.posts, [{ url: '/admin/operations/cdn/preload', data: { urls: ['https://cdn.example.com/a.png'] } }])
})

test('unconfigured CDN stays disabled and unsupported operation types are hidden', async (t) => {
  const view = await mount({ config: { ...config, enabled: false, refresh_types: ['File'] } })
  t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('CDN 运维尚未启用'))
  assert.equal(view.container.querySelectorAll('.operation-options .el-radio-button').length, 2)
  view.state.input = 'https://cdn.example.com/a.png'
  await view.state.submit()
  assert.equal(view.posts.length, 0)
  assert.equal(view.gets.length, 1)
  assert.equal(view.container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled, true)
})

test('submission failures retain the address and pending submissions cannot be duplicated', async (t) => {
  let finish!: (value: CdnSubmission) => void
  let fail = true
  const view = await mount({ post: async () => { if (fail) throw new Error('offline'); return new Promise((resolve) => { finish = resolve }) } })
  t.after(view.unmount)
  view.state.input = 'https://cdn.example.com/a.png'
  await view.state.submit()
  await settle()
  assert.ok(view.container.textContent?.includes('任务可能已提交'))
  assert.equal(view.state.input, 'https://cdn.example.com/a.png')
  assert.equal(view.state.submission, null)
  fail = false
  const pending = view.state.submit()
  await view.state.submit()
  assert.equal(view.posts.length, 2)
  finish(result)
  await pending
  assert.equal(view.state.submitting, false)
})

test('explicit API rejections show the server explanation and do not keep an earlier success result', async (t) => {
  let rejected = false
  const view = await mount({ post: async () => {
    if (rejected) throw { response: { data: { message: 'CDN 请求频率或配额已达上限' } } }
    return result
  } })
  t.after(view.unmount)
  view.state.input = 'https://cdn.example.com/a.png'
  await view.state.submit()
  assert.equal(view.state.submission?.task_id, result.task_id)
  rejected = true
  await view.state.submit()
  await settle()
  assert.ok(view.container.textContent?.includes('CDN 请求频率或配额已达上限'))
  assert.equal(view.state.submission, null)
  assert.equal(view.state.input, 'https://cdn.example.com/a.png')
})

test('successful submissions retain thirty unique recent URLs across remounts and history clicks append without submitting', async (t) => {
  let view = await mount()
  t.after(() => view.unmount())
  const batch = Array.from({ length: 32 }, (_, index) => `https://cdn.example.com/${index}.png`)
  view.state.input = `  ${batch[0]}  \n${batch.join('\n')}\n\n${batch[1]}`
  await view.state.submit()
  assert.deepEqual(view.state.urlHistory, batch.slice(0, 30))

  const newest = 'https://cdn.example.com/new.png'
  view.state.operation = 'Preload'
  view.state.input = `${batch[20]}\n${newest}\n${batch[20]}`
  await view.state.submit()
  const expected = [batch[20], newest, ...batch.slice(0, 30).filter((url) => url !== batch[20])].slice(0, 30)
  assert.deepEqual(view.state.urlHistory, expected)
  assert.deepEqual(JSON.parse(window.localStorage.getItem('sudothink:cdn-url-history')!), expected)

  view.unmount()
  view = await mount()
  assert.deepEqual(view.state.urlHistory, expected)
  const history = view.container.querySelector<HTMLDetailsElement>('.url-history')
  assert.ok(history, '已保存的 URL 应提供历史记录入口')
  history.open = true
  const entry = [...history.querySelectorAll<HTMLButtonElement>('button')].find((button) => button.textContent?.trim() === newest)
  assert.ok(entry, '历史地址应可点击回填')
  view.state.input = 'https://cdn.example.com/draft.png'
  await nextTick()
  entry.click()
  entry.click()
  await settle()
  assert.equal(view.state.input, `https://cdn.example.com/draft.png\n${newest}`)
  assert.equal(view.posts.length, 0, '选择历史地址不应提交 CDN 任务')
})

test('invalid input and unsuccessful submissions leave URL history unchanged', async (t) => {
  const saved = ['https://cdn.example.com/saved.png']
  window.localStorage.setItem('sudothink:cdn-url-history', JSON.stringify(saved))
  const view = await mount({ post: async () => { throw new Error('offline') } })
  t.after(view.unmount)
  view.state.input = 'invalid URL'
  await view.state.submit()
  assert.equal(view.posts.length, 0)
  assert.deepEqual(view.state.urlHistory, saved)
  view.state.input = 'https://cdn.example.com/failed.png'
  await view.state.submit()
  assert.equal(view.posts.length, 1)
  assert.deepEqual(view.state.urlHistory, saved)
  assert.deepEqual(JSON.parse(window.localStorage.getItem('sudothink:cdn-url-history')!), saved)
})

test('URL history records the submitted snapshot when the draft changes during a request', async (t) => {
  let finish!: (value: CdnSubmission) => void
  const view = await mount({ post: () => new Promise((resolve) => { finish = resolve }) })
  t.after(view.unmount)
  const submitted = 'https://cdn.example.com/submitted.png'
  view.state.input = submitted
  const pending = view.state.submit()
  view.state.input = 'https://cdn.example.com/later-draft.png'
  assert.deepEqual(view.state.urlHistory, [])
  finish(result)
  await pending
  assert.deepEqual(view.state.urlHistory, [submitted])
  assert.equal(view.state.input, 'https://cdn.example.com/later-draft.png')
})
