import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { Todo, TodoHistoryPage } from '../api/todos'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, {
  window: dom.window, document: dom.window.document, Document: dom.window.Document,
  Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement,
  HTMLInputElement: dom.window.HTMLInputElement, HTMLTextAreaElement: dom.window.HTMLTextAreaElement,
  CustomEvent: dom.window.CustomEvent, FocusEvent: dom.window.FocusEvent,
  Node: dom.window.Node, MutationObserver: dom.window.MutationObserver,
  Event: dom.window.Event, MouseEvent: dom.window.MouseEvent, getComputedStyle: dom.window.getComputedStyle,
  requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame,
  ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
})
const { createApp, nextTick } = await import('vue')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.todo-history-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })

function compile(source: string) {
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
}
const apiTarget = `${folder}/todos.mjs`
const httpBridge = 'const http = { get: (...args) => globalThis.__todosHttp.get(...args) }'
writeFileSync(apiTarget, compile(readFileSync(new URL('../api/todos.ts', import.meta.url), 'utf8').replace("import http from './http'", httpBridge)))
const { descriptor } = parse(readFileSync(new URL('../components/TodoHistory.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'todo-history-test' })
const source = script.content.replace(/(['"])@\/api\/todos\1/g, JSON.stringify(pathToFileURL(apiTarget).href))
const target = `${folder}/TodoHistory.mjs`
writeFileSync(target, compile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'TodoHistory.vue', id: 'todo-history-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const TodoHistory = (await import(pathToFileURL(target).href)).default
TodoHistory.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(yes => { resolve = yes })
  return { promise, resolve }
}
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
const todo = { id: 1, title: '证书续期', reminder_timezone: 'Asia/Shanghai' } as Todo
type HistoryState = { items: unknown[]; loading: boolean; error: string; load: (page?: number) => Promise<void> }
type Request = { url: string; params: Record<string, number>; signal: AbortSignal }
async function mount(fetch: (params: Request['params']) => Promise<TodoHistoryPage>) {
  const requests: Request[] = []
  Object.assign(globalThis, { __todosHttp: {
    get: (url: string, settings: Omit<Request, 'url'>) => {
      requests.push({ url, ...settings })
      return fetch(settings.params)
    },
  } })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(TodoHistory, { todo, modelValue: true })
  app.use(ElementPlus)
  const instance = app.mount(container) as unknown as { $: { setupState: HistoryState } }
  await settle()
  return { app, state: instance.$.setupState, requests, unmount: () => { app.unmount(); container.remove() } }
}
const page = (items: TodoHistoryPage['items'] = [], number = 1, total = items.length): TodoHistoryPage => ({ items, total, page: number, size: 10 })

test('history handles empty, error and retry with paginated requests', async t => {
  let fail = false
  const view = await mount(async params => {
    if (fail) throw Error('offline')
    return page([], params.page, 21)
  })
  t.after(view.unmount)
  assert.match(document.body.textContent ?? '', /暂无提醒历史/)
  assert.equal(view.requests[0].url, '/admin/todos/1/history')
  await view.state.load(2)
  assert.deepEqual(view.requests.at(-1)?.params, { page: 2, size: 10 })
  fail = true
  await view.state.load(2)
  await settle()
  assert.match(document.body.textContent ?? '', /历史加载失败/)
  fail = false
  const retry = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === '重试')
  assert.ok(retry)
  retry.click()
  await settle()
  assert.equal(view.state.error, '')
})

test('new pages ignore late responses and closing aborts the pending history request', async t => {
  const first = deferred<TodoHistoryPage>()
  const second = deferred<TodoHistoryPage>()
  const view = await mount(params => params.page === 1 ? first.promise : second.promise)
  t.after(view.unmount)
  const latest = view.state.load(2)
  assert.equal(view.requests[0].signal.aborted, true)
  second.resolve(page([{ id: 2, event: 'skipped', period: 'month', scheduled_at: null,
    created_at: '2026-11-24T01:00:00Z', next_run_at: null, error: '[REDACTED]' }], 2, 21))
  await latest
  first.resolve(page())
  await settle()
  assert.equal(view.state.items.length, 1)
  assert.match(document.body.textContent ?? '', /本月/)
  const pending = deferred<TodoHistoryPage>()
  let signal: AbortSignal | undefined
  Object.assign(globalThis, { __todosHttp: { get: (_url: string, settings: { signal: AbortSignal }) => {
    signal = settings.signal
    return pending.promise
  } } })
  const loading = view.state.load(3)
  await nextTick()
  view.app._instance!.props.modelValue = false
  await settle()
  assert.equal(view.state.loading, false)
  assert.equal(signal?.aborted, true)
  pending.resolve(page())
  await loading
  assert.equal(view.state.items.length, 1)
})
