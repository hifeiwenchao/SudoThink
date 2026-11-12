import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'

const dom = new JSDOM('<!doctype html><html><body></body></html>')
Object.assign(globalThis, { window: dom.window, document: dom.window.document, Element: dom.window.Element, SVGElement: dom.window.SVGElement })
const { createApp, nextTick } = await import('vue')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.admin-comments-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const { descriptor } = parse(readFileSync(new URL('../views/AdminComments.vue', import.meta.url), 'utf8'))
const source = compileScript(descriptor, { id: 'admin-comments-test' }).content
  .replace("import { ElMessage } from 'element-plus'", 'const ElMessage = { success() {} }')
  .replace("import { adminApi, type PendingComment } from '@/api/admin'", 'const adminApi = { pendingComments: (...args) => globalThis.__commentReviewApi.pendingComments(...args) }')
  .replace("import http from '@/api/http'", 'const http = { post: (...args) => globalThis.__commentReviewHttp.post(...args) }')
const target = `${folder}/AdminComments.mjs`
writeFileSync(target, ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText)
const AdminComments = (await import(pathToFileURL(target).href)).default

test('approving the last pending item on a removed page returns to the previous page', async (t) => {
  const remaining = { id: 1, content: '第一页', nickname: '访客', email: '', ip_address: '', location: '未知', created_at: '2026-11-12T08:00:00Z', article: { id: 42, title: '文章' }, author: null }
  let reviewed = false
  let finish!: () => void
  const requests: number[] = []
  Object.assign(globalThis, {
    __commentReviewApi: { async pendingComments(page: number) {
      requests.push(page)
      if (page === 2) return { items: reviewed ? [] : [{ ...remaining, id: 11 }], total: reviewed ? 10 : 11, page, size: 10 }
      return { items: [remaining], total: reviewed ? 10 : 11, page, size: 10 }
    } },
    __commentReviewHttp: { async post() { await new Promise<void>((done) => { finish = done }); reviewed = true } },
  })
  const container = document.createElement('div')
  const app = createApp({ ...AdminComments, render: () => null })
  const instance = app.mount(container) as unknown as { $: { setupState: { page: number; list: typeof remaining[]; actingId: number | null; load: () => Promise<void>; handleApprove: (id: number) => Promise<void> } } }
  t.after(() => app.unmount())
  await flushPromises(); await nextTick()
  const state = instance.$.setupState
  state.page = 2
  await state.load()
  assert.equal(state.list[0].id, 11)
  const action = state.handleApprove(11)
  assert.equal(state.actingId, 11)
  finish()
  await action
  assert.equal(state.page, 1)
  assert.equal(state.list[0].id, 1)
  assert.equal(state.actingId, null)
  assert.deepEqual(requests, [1, 2, 2, 1])
})
