import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, beforeEach, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import axios, { type InternalAxiosRequestConfig } from 'axios'
import { readCommenter, saveCommenter } from './commenter'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://blog.example.com/' })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, Document: dom.window.Document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement })
const { createApp, nextTick } = await import('vue')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.comments-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })

async function component() {
  const filename = new URL('../components/ArticleComments.vue', import.meta.url)
  const { descriptor } = parse(readFileSync(filename, 'utf8'))
  const source = compileScript(descriptor, { id: 'article-comments-test', inlineTemplate: true }).content
    .replace(/(['"])@\/([^'"]+)\1/g, (_match, _quote, path: string) => JSON.stringify(new URL(`../${path}.ts`, import.meta.url).href))
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  const target = `${folder}/ArticleComments.mjs`
  writeFileSync(target, compiled)
  return (await import(pathToFileURL(target).href)).default
}

let ArticleComments: Awaited<ReturnType<typeof component>>
beforeEach(() => { window.localStorage.clear() })

function response(config: InternalAxiosRequestConfig, data: unknown) {
  return { data: { code: 0, data }, status: 200, statusText: 'OK', headers: {}, config }
}
const firstPage = { items: [{ id: 7, nickname: '读者_A', location: '浙江省杭州市', content: '<img src=x onerror=alert(1)>\n谢谢分享', created_at: '2026-11-12T08:00:00+08:00', parent_id: null }], total: 1, page: 1, size: 10 }
async function settle() { await flushPromises(); await nextTick() }
async function mount() {
  ArticleComments ??= await component()
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(ArticleComments, { articleId: 42 })
  app.mount(container)
  await settle()
  return { container, unmount: () => { app.unmount(); container.remove() } }
}
function input(container: HTMLElement, name: string, value: string) {
  const field = container.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[name="${name}"]`)!
  field.value = value
  field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
}
function submit(container: HTMLElement) {
  container.querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
}

test('approved comments render as plain text with nickname and location, without private data', async (t) => {
  axios.defaults.adapter = async (config) => response(config, firstPage)
  const view = await mount(); t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('读者_A'))
  assert.ok(view.container.textContent?.includes('浙江省杭州市'))
  assert.ok(view.container.textContent?.includes('<img src=x onerror=alert(1)>\n谢谢分享'))
  assert.equal(view.container.querySelector('img'), null)
})

test('successful submissions stay pending and remember the edited identity for another visit', async (t) => {
  const submissions: unknown[] = []
  axios.defaults.adapter = async (config) => {
    assert.equal(config.url, '/articles/42/comments')
    if (config.method === 'post') {
      submissions.push(JSON.parse(config.data))
      return response(config, { id: 8, is_approved: false })
    }
    return response(config, firstPage)
  }
  saveCommenter({ nickname: '原昵称', email: 'old@example.com' })
  const view = await mount(); t.after(view.unmount)
  assert.equal(view.container.querySelector('[name="nickname"]'), null)
  view.container.querySelector<HTMLButtonElement>('[data-action="edit-identity"]')!.click(); await settle()
  assert.equal(view.container.querySelector<HTMLInputElement>('[name="nickname"]')?.value, '原昵称')
  input(view.container, 'nickname', ' 新昵称_2 ')
  input(view.container, 'email', ' reader@example.com ')
  input(view.container, 'content', ' 新的评论内容 ')
  submit(view.container); await settle()
  assert.deepEqual(submissions, [{ nickname: '新昵称_2', email: 'reader@example.com', content: '新的评论内容' }])
  assert.equal(view.container.querySelector<HTMLTextAreaElement>('textarea')?.value, '')
  assert.ok(view.container.textContent?.includes('等待审核'))
  assert.equal(view.container.querySelectorAll('.comment-item').length, 1)
  assert.equal(view.container.querySelector('[name="nickname"]'), null)
  assert.ok(view.container.querySelector('.comment-identity-summary')?.textContent?.includes('新昵称_2'))
  assert.deepEqual(readCommenter(), { nickname: '新昵称_2', email: 'reader@example.com' })
  const another = await mount(); t.after(another.unmount)
  assert.equal(another.container.querySelector('[name="nickname"]'), null)
  assert.equal(another.container.querySelector('[name="email"]'), null)
  assert.ok(!another.container.textContent?.includes('reader@example.com'))
  input(another.container, 'content', '再次评论')
  submit(another.container); await settle()
  assert.deepEqual(submissions[1], { nickname: '新昵称_2', email: 'reader@example.com', content: '再次评论' })
})

test('invalid nickname blocks submission and an optional blank email is omitted', async (t) => {
  const submissions: unknown[] = []
  axios.defaults.adapter = async (config) => {
    if (config.method === 'post') { submissions.push(JSON.parse(config.data)); return response(config, { id: 8, is_approved: false }) }
    return response(config, firstPage)
  }
  const view = await mount(); t.after(view.unmount)
  input(view.container, 'nickname', 'a-b')
  input(view.container, 'content', '正文')
  submit(view.container); await settle()
  assert.deepEqual(submissions, [])
  assert.ok(view.container.querySelector('[role="alert"]'))
  input(view.container, 'nickname', '读者')
  submit(view.container); await settle()
  assert.deepEqual(submissions, [{ nickname: '读者', content: '正文' }])
  assert.equal(view.container.querySelector('[name="nickname"]'), null)
  assert.equal(view.container.querySelector('[name="email"]'), null)
  assert.ok(view.container.querySelector('.comment-identity-summary')?.textContent?.includes('读者'))
  const another = await mount(); t.after(another.unmount)
  assert.equal(another.container.querySelector('[name="nickname"]'), null)
  assert.ok(another.container.querySelector('.comment-identity-summary')?.textContent?.includes('读者'))
})

test('canceling identity changes restores saved details without losing the comment draft', async (t) => {
  saveCommenter({ nickname: '原昵称', email: 'old@example.com' })
  const submissions: unknown[] = []
  axios.defaults.adapter = async (config) => {
    if (config.method === 'post') { submissions.push(JSON.parse(config.data)); return response(config, { id: 8, is_approved: false }) }
    return response(config, firstPage)
  }
  const view = await mount(); t.after(view.unmount)
  input(view.container, 'content', '保留这段正文')
  const edit = view.container.querySelector<HTMLButtonElement>('[data-action="edit-identity"]')!
  assert.equal(edit.getAttribute('aria-expanded'), 'false')
  edit.click(); await settle()
  assert.equal(document.activeElement, view.container.querySelector('[name="nickname"]'))
  input(view.container, 'nickname', '临时昵称')
  input(view.container, 'email', 'invalid')
  view.container.querySelector<HTMLButtonElement>('[data-action="cancel-identity"]')!.click(); await settle()
  assert.equal(view.container.querySelector('[name="nickname"]'), null)
  assert.equal(document.activeElement, view.container.querySelector('[data-action="edit-identity"]'))
  assert.equal(view.container.querySelector<HTMLTextAreaElement>('textarea')?.value, '保留这段正文')
  submit(view.container); await settle()
  assert.deepEqual(submissions, [{ nickname: '原昵称', email: 'old@example.com', content: '保留这段正文' }])
})

test('invalid saved identity stays editable instead of blocking submission behind hidden fields', async (t) => {
  axios.defaults.adapter = async (config) => response(config, firstPage)
  for (const identity of [{ nickname: 'a-b', email: '' }, { nickname: '读者', email: 'invalid' }]) {
    saveCommenter(identity)
    const view = await mount(); t.after(view.unmount)
    assert.ok(view.container.querySelector('[name="nickname"]'))
    assert.ok(view.container.querySelector('[name="email"]'))
    assert.equal(view.container.querySelector('[data-action="edit-identity"]'), null)
  }
})

test('failed submission preserves the draft and does not replace the saved identity', async (t) => {
  saveCommenter({ nickname: '原昵称', email: 'old@example.com' })
  axios.defaults.adapter = async (config) => {
    if (config.method === 'post') throw new Error('连接失败')
    return response(config, firstPage)
  }
  const view = await mount(); t.after(view.unmount)
  view.container.querySelector<HTMLButtonElement>('[data-action="edit-identity"]')!.click(); await settle()
  input(view.container, 'nickname', '新昵称')
  input(view.container, 'content', '不要丢失这段文字')
  submit(view.container); await settle()
  assert.equal(view.container.querySelector<HTMLTextAreaElement>('textarea')?.value, '不要丢失这段文字')
  assert.ok(view.container.querySelector('[role="alert"]'))
  assert.equal(view.container.querySelector<HTMLInputElement>('[name="nickname"]')?.value, '新昵称')
  assert.deepEqual(readCommenter(), { nickname: '原昵称', email: 'old@example.com' })
})

test('identity controls stay disabled during submission and collapse only after success', async (t) => {
  saveCommenter({ nickname: '原昵称', email: '' })
  let complete!: () => void
  axios.defaults.adapter = async (config) => {
    if (config.method === 'post') {
      await new Promise<void>((resolve) => { complete = resolve })
      return response(config, { id: 8, is_approved: false })
    }
    return response(config, firstPage)
  }
  const view = await mount(); t.after(view.unmount)
  view.container.querySelector<HTMLButtonElement>('[data-action="edit-identity"]')!.click(); await settle()
  input(view.container, 'nickname', '新昵称')
  input(view.container, 'content', '等待中的评论')
  submit(view.container); await settle()
  assert.equal(view.container.querySelector<HTMLButtonElement>('[data-action="cancel-identity"]')?.disabled, true)
  assert.equal(view.container.querySelector<HTMLInputElement>('[name="nickname"]')?.disabled, true)
  assert.deepEqual(readCommenter(), { nickname: '原昵称', email: '' })
  complete(); await settle()
  assert.equal(view.container.querySelector('[name="nickname"]'), null)
  assert.equal(view.container.querySelector<HTMLButtonElement>('[data-action="edit-identity"]')?.disabled, false)
  assert.deepEqual(readCommenter(), { nickname: '新昵称', email: '' })
})

test('unavailable storage still allows a successful comment and hides identity for this page', async (t) => {
  t.mock.method(dom.window.Storage.prototype, 'setItem', () => { throw new Error('blocked') })
  axios.defaults.adapter = async (config) => response(config, config.method === 'post' ? { id: 8, is_approved: false } : firstPage)
  const view = await mount(); t.after(view.unmount)
  input(view.container, 'nickname', '读者')
  input(view.container, 'content', '浏览器不允许存储也能评论')
  submit(view.container); await settle()
  assert.ok(view.container.querySelector('.comment-message.success'))
  assert.equal(view.container.querySelector('[name="nickname"]'), null)
  assert.ok(view.container.querySelector('.comment-identity-summary')?.textContent?.includes('读者'))
})

test('a failed list can be retried and pagination displays the requested page', async (t) => {
  let fail = true
  axios.defaults.adapter = async (config) => {
    if (fail) { fail = false; throw new Error('offline') }
    assert.equal(config.params.size, 10)
    const page = config.params.page
    return response(config, { items: [{ ...firstPage.items[0], nickname: page === 2 ? '第二页读者' : '第一页读者' }], total: 11, page, size: 10 })
  }
  const view = await mount(); t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('评论加载失败'))
  view.container.querySelector<HTMLButtonElement>('[data-action="retry"]')!.click(); await settle()
  assert.ok(view.container.textContent?.includes('第一页读者'))
  view.container.querySelector<HTMLButtonElement>('[aria-label="下一页评论"]')!.click(); await settle()
  assert.ok(view.container.textContent?.includes('第二页读者'))
  assert.ok(!view.container.textContent?.includes('第一页读者'))
  assert.equal(view.container.querySelector<HTMLButtonElement>('[aria-label="下一页评论"]')?.disabled, true)
})
