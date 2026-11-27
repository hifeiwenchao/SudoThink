import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush, setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'

const dom = new JSDOM('<html><body></body></html>', { url: 'https://example.com/' })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node })
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; this.querySelector<HTMLButtonElement>('button')?.focus() }
dom.window.HTMLDialogElement.prototype.close = function () { this.open = false }
const { createApp, nextTick, reactive, h } = await import('vue')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.article-reader-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const transpile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { descriptor } = parse(readFileSync(new URL('../components/ArticleContent.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'reader-test' })
const source = script.content.replace(/(['"])@\/utils\/articleContent\1/g, JSON.stringify(new URL('./articleContent.ts', import.meta.url).href)).replace(/(['"])@\/utils\/articleReader\1/g, JSON.stringify(new URL('./articleReader.ts', import.meta.url).href)).replace(/import '@\/styles\/article.css'/, '')
writeFileSync(`${folder}/component.mjs`, transpile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'ArticleContent.vue', id: 'reader-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, transpile(template.code))
const Component = (await import(pathToFileURL(`${folder}/component.mjs`).href)).default
Component.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render
async function settle() { await flush(); await nextTick() }
async function mount(content: string) {
  const props = reactive({ content })
  const host = document.createElement('div'); document.body.append(host)
  const app = createApp({ setup: () => () => h(Component, props) }); app.mount(host); await settle()
  return { host, props, dispose() { app.unmount(); host.remove() } }
}

test('code copy preserves literal text, reports success for two seconds and supports clipboard fallback', async () => {
  const writes: string[] = []
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { async writeText(text: string) { writes.push(text) } } })
  const content = '<pre><code>  a &lt; b &amp;&amp; c\n\tlast\n</code></pre>'
  const view = await mount(content)
  try {
    const button = view.host.querySelector<HTMLButtonElement>('.article-code-copy')!
    button.click(); await settle()
    assert.deepEqual(writes, ['  a < b && c\n\tlast\n'])
    assert.equal(button.textContent, '已复制')
    await delay(2050)
    assert.equal(button.textContent, '复制代码')
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { async writeText() { throw new Error('blocked') } } })
    let fallback = ''
    document.execCommand = (() => { fallback = document.querySelector('textarea')!.value; return true }) as typeof document.execCommand
    button.focus(); button.click(); await settle()
    assert.equal(fallback, writes[0]); assert.equal(document.activeElement, button)
    assert.equal(document.querySelector('textarea'), null)
    assert.equal(button.textContent, '已复制')
  } finally { view.dispose() }
})

test('copy failure is visible and unmounted pending clipboard work cannot create fallback DOM', async () => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
  document.execCommand = (() => false) as typeof document.execCommand
  const view = await mount('<pre><code>text</code></pre>')
  const button = view.host.querySelector<HTMLButtonElement>('button')!
  button.click(); await settle()
  assert.equal(button.textContent, '复制失败，请手动复制')
  assert.equal(document.querySelector('textarea'), null)
  view.dispose()
  let rejectCopy!: (reason: Error) => void
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => new Promise<void>((_, reject) => { rejectCopy = reject }) } })
  let fallbackCalls = 0
  document.execCommand = (() => { fallbackCalls++; return true }) as typeof document.execCommand
  const pending = await mount('<pre><code>pending</code></pre>')
  const staleButton = pending.host.querySelector<HTMLButtonElement>('button')!
  staleButton.click(); pending.dispose(); rejectCopy(new Error('blocked')); await settle()
  assert.equal(fallbackCalls, 0)
  staleButton.click(); await settle(); assert.equal(fallbackCalls, 0)
})

test('image preview supports keyboard, Escape, focus return and leaves linked images alone', async () => {
  const view = await mount('<p><img src="/safe.png" alt="图示"><a href="/download"><img src="/linked.png"></a><img src="javascript:alert(1)"></p>')
  try {
    const images = view.host.querySelectorAll<HTMLImageElement>('.article-prose img')
    assert.equal(images.length, 2)
    assert.equal(images[0]!.getAttribute('role'), 'button')
    assert.equal(images[1]!.hasAttribute('tabindex'), false)
    images[0]!.focus()
    images[0]!.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await settle()
    const dialog = view.host.querySelector('dialog')!
    assert.equal(dialog.open, true)
    assert.equal(dialog.querySelector('img')!.getAttribute('src'), '/safe.png')
    assert.equal(document.activeElement, dialog.querySelector('button'))
    dialog.dispatchEvent(new dom.window.Event('cancel', { cancelable: true })); await settle()
    assert.equal(dialog.open, false); assert.equal(document.activeElement, images[0])
    images[0]!.click(); await settle()
    dialog.querySelector<HTMLButtonElement>('button')!.click(); await settle()
    assert.equal(dialog.open, false)
    images[0]!.click(); await settle()
    view.props.content = '<p>新文章</p>'; await settle()
    assert.equal(dialog.open, false)
    assert.equal(view.host.querySelector('.article-code-copy'), null)
  } finally { view.dispose() }
})
