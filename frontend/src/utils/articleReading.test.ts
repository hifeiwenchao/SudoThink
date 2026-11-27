import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush, setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'

const dom = new JSDOM('<html><body></body></html>', { url: 'https://example.com/', pretendToBeVisual: true })
Object.assign(globalThis, { window: dom.window, Event: dom.window.Event, CustomEvent: dom.window.CustomEvent, document: dom.window.document, Document: dom.window.Document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, HTMLInputElement: dom.window.HTMLInputElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node, MutationObserver: dom.window.MutationObserver, getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame, history: dom.window.history, location: dom.window.location, ResizeObserver: class { observe() {} unobserve() {} disconnect() {} } })
dom.window.matchMedia = (() => ({ matches: true, addEventListener() {}, removeEventListener() {} })) as any
dom.window.HTMLElement.prototype.scrollIntoView = function () {}
const { createApp, nextTick } = await import('vue')
const { createRouter, createMemoryHistory } = await import('vue-router')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.article-reading-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const transpile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { descriptor } = parse(readFileSync(new URL('../views/ArticleDetailView.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'reading-test' })
const source = script.content
  .replace(/import .* from '@\/api\/article'/, `const articleApi = { detail: async (id) => ({ id, title: '阅读测试', content: '<h2>第一节</h2><p>正文</p><h3>第二节</h3>', summary: '', cover: '', tags: [], author: { username: 'author' }, view_count: 5, is_published: true, created_at: '2026-11-26' }) }`)
  .replace(/import ArticleContent from .*/, `const ArticleContent = { props: ['content'], template: '<div class="article-prose" v-html="content" />' }`)
  .replace(/import ArticleComments from .*/, `const ArticleComments = { template: '<div />' }`)
  .replace(/import WechatShare from .*/, `const WechatShare = { template: '<div />' }`)
  .replace(/import .* from '@\/utils\/articleContent'/, `const getArticleText = (value) => value.replace(/<[^>]*>/g, '')`)
  .replace(/(['"])@\/utils\/publicNavigation\1/g, JSON.stringify(new URL('./publicNavigation.ts', import.meta.url).href))
  .replace(/import .* from '@\/utils\/seo'/, 'const setPageSeo = () => {}')
  .replace(/import .* from '@\/site'/, 'const isAdminSite = () => false')
writeFileSync(`${folder}/component.mjs`, transpile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'ArticleDetailView.vue', id: 'reading-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, transpile(template.code))
const Component = (await import(pathToFileURL(`${folder}/component.mjs`).href)).default
Component.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render
async function settle() { await flush(); await nextTick(); await delay(60); await nextTick() }

test('mobile contents opens, closes with Escape and selects a heading without losing the list return', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/articles/:id', component: Component }] })
  await router.push('/articles/1?from=%2F%3Fpage%3D2'); await router.isReady()
  const container = document.createElement('div'); document.body.append(container)
  const app = createApp(Component); app.use(router); app.use(ElementPlus)
  app.mount(container)
  try {
    await settle()
    const trigger = container.querySelector<HTMLButtonElement>('.mobile-contents-trigger')
    assert.ok(trigger, 'a floating contents button is available for long articles')
    trigger.focus(); trigger.click(); await settle()
    assert.equal(trigger.getAttribute('aria-expanded'), 'true')
    assert.ok(document.querySelector('.el-drawer .contents-link'))
    document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await settle()
    assert.equal(trigger.getAttribute('aria-expanded'), 'false')
    assert.equal(document.activeElement, trigger, 'Escape returns keyboard focus to the contents button')
    trigger.click(); await settle()
    document.querySelector<HTMLButtonElement>('.el-drawer__close-btn')!.click(); await settle()
    assert.equal(trigger.getAttribute('aria-expanded'), 'false', 'the visible close button dismisses the drawer')
    trigger.click(); await settle()
    const link = document.querySelector<HTMLAnchorElement>('.el-drawer .contents-link')!
    link.click(); await settle()
    assert.equal(trigger.getAttribute('aria-expanded'), 'false')
    assert.equal(router.currentRoute.value.hash, '#article-1-第一节')
    assert.equal(router.currentRoute.value.query.from, '/?page=2')
    assert.equal(document.activeElement?.id, 'article-1-第一节')
    trigger.click(); await settle()
    await router.push('/articles/2'); await settle()
    assert.equal(container.querySelector('.mobile-contents-trigger')?.getAttribute('aria-expanded'), 'false')
  } finally { app.unmount(); container.remove(); await settle() }
})
