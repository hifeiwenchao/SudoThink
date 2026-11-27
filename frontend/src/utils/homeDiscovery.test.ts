import assert from 'node:assert/strict'
import { readFileSync, existsSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
const dom = new JSDOM('<html><body></body></html>', { url: 'https://example.com/' })
Object.assign(globalThis, { window: dom.window, history: dom.window.history, location: dom.window.location, document: dom.window.document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node })
const { createApp, nextTick } = await import('vue')
const { createRouter, createMemoryHistory } = await import('vue-router')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.home-discovery-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
let Component: any
async function component() {
  if (Component) return Component
  const path = new URL('../components/HomeDiscovery.vue', import.meta.url)
  assert.ok(existsSync(path), 'homepage discovery component is available')
  const { descriptor } = parse(readFileSync(path, 'utf8'))
  const script = compileScript(descriptor, { id: 'discovery-test' })
  const source = script.content
    .replace(/import .* from '@\/api\/about'/, 'const aboutApi = { sidebar: () => globalThis.__homeSidebar() }')
    .replace(/(['"])@\/utils\/aboutContacts\1/g, JSON.stringify(new URL('./aboutContacts.ts', import.meta.url).href))
  const transpile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  writeFileSync(`${folder}/component.mjs`, transpile(source))
  const template = compileTemplate({ source: descriptor.template!.content, filename: 'HomeDiscovery.vue', id: 'discovery-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
  writeFileSync(`${folder}/template.mjs`, transpile(template.code))
  Component = (await import(pathToFileURL(`${folder}/component.mjs`).href)).default
  Component.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render
  return Component
}
async function settle() { await flush(); await nextTick() }
async function mount(sidebar: () => Promise<any>) {
  Object.assign(globalThis, { __homeSidebar: sidebar })
  const value = await component()
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: value }, { path: '/articles/:id', component: { template: '<div />' } }] })
  await router.push('/?q=vue&page=2#articles'); await router.isReady()
  const container = document.createElement('div')
  const app = createApp(value); app.use(router)
  const vm = app.mount(container) as any
  return { container, router, vm, unmount: () => app.unmount() }
}
const article = (id: number) => ({ id, title: `文章 ${id}`, summary: '', category: { id: 1, name: '技术', slug: 'tech' } })
test('featured articles preserve configured order, category and homepage return context', async () => {
  const view = await mount(async () => ({ featured_articles: [article(9), { ...article(3), category: null }, article(4), article(5), article(6), article(7)], current_projects: [] }))
  try {
    await settle()
    const links = [...view.container.querySelectorAll('a')]
    assert.equal(links.length, 5)
    assert.doesNotMatch(view.container.textContent!, /文章 7/)
    assert.match(links[0]!.textContent!, /文章 9/)
    assert.match(view.container.textContent!, /技术/)
    const target = view.router.resolve(links[0]!.getAttribute('href')!)
    assert.equal(target.path, '/articles/9')
    assert.equal(target.query.from, '/?q=vue&page=2#articles')
    assert.doesNotMatch(view.container.textContent!, /正在折腾/)
  } finally { view.unmount() }
})
test('projects cap at three and unsafe or absent URLs remain readable without links', async () => {
  for (const unsafe of ['', 'javascript:alert(1)', '//evil.example', 'https://user:pass@example.com', 'https://exa\nmple.com', 'https://exa\u200bmple.com']) {
    const view = await mount(async () => ({ featured_articles: [], current_projects: [
      { name: '安全项目', description: '一个构建中的工具', url: 'https://example.com/project' },
      { name: '无链接项目', description: '仍然展示说明', url: unsafe },
      { name: '第三项', description: '保留', url: '' },
      { name: '超额项目', description: '不应展示', url: 'https://example.com/four' },
    ] }))
    try {
      await settle()
      assert.match(view.container.textContent!, /无链接项目/)
      assert.match(view.container.textContent!, /仍然展示说明/)
      assert.doesNotMatch(view.container.textContent!, /超额项目|精选文章/)
      const links = [...view.container.querySelectorAll('a')]
      assert.equal(links.length, 1)
      assert.equal(links[0]!.href, 'https://example.com/project')
      assert.equal(links[0]!.target, '_blank')
      assert.equal(links[0]!.rel, 'noopener noreferrer')
    } finally { view.unmount() }
  }
})
test('empty or failed optional discovery hides its entire section', async () => {
  for (const response of [async () => ({ featured_articles: [], current_projects: [] }), async () => { throw new Error('offline') }]) {
    const view = await mount(response)
    try { await settle(); assert.equal(view.container.querySelector('section'), null); assert.equal(view.container.textContent, '') } finally { view.unmount() }
  }
})
test('late discovery response does not update an unmounted component', async () => {
  let resolve!: (value: any) => void
  const view = await mount(() => new Promise(done => { resolve = done }))
  view.unmount()
  resolve({ featured_articles: [article(9)], current_projects: [] })
  await settle()
  assert.equal(view.vm.$.setupState.featuredArticles.length, 0)
  assert.equal(view.container.textContent, '')
})
