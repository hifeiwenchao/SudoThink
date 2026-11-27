import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
const dom = new JSDOM('<html><body></body></html>', { url: 'https://example.com/', pretendToBeVisual: true })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, Document: dom.window.Document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node, MutationObserver: dom.window.MutationObserver, getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame, history: dom.window.history, location: dom.window.location, ResizeObserver: class { observe() {} unobserve() {} disconnect() {} } })
const { createApp, nextTick, ref } = await import('vue')
const { createRouter, createMemoryHistory } = await import('vue-router')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.home-navigation-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const transpile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { descriptor } = parse(readFileSync(new URL('../views/HomeView.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'home-test' })
let source = script.content.replace("import { storeToRefs } from 'pinia'", 'const storeToRefs = (store) => store')
  .replace(/import .* from '@\/api\/about'/, 'const aboutApi = { contacts: () => globalThis.__homeContacts() }')
  .replace("import HomeDiscovery from '@/components/HomeDiscovery.vue'", 'const HomeDiscovery = { template: "<div />" }')
  .replace("import ContactLinks from '@/components/ContactLinks.vue'", 'const ContactLinks = { props: ["contacts"], template: \'<a v-if="contacts.github_url" :href="contacts.github_url">GitHub</a>\' }')
  .replace(/import .* from '@\/api\/article'/, 'const articleApi = { list: (...args) => globalThis.__homeList(...args) }')
  .replace(/import .* from '@\/api\/taxonomy'/, 'const taxonomyApi = { tags: async () => [] }')
  .replace("import { useTaxonomyStore } from '@/stores/taxonomy'", 'const useTaxonomyStore = () => globalThis.__homeTaxonomy')
  .replace(/(['"])@\/utils\/publicNavigation\1/g, JSON.stringify(new URL('./publicNavigation.ts', import.meta.url).href))
writeFileSync(`${folder}/component.mjs`, transpile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'HomeView.vue', id: 'home-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, transpile(template.code))
const Component = (await import(pathToFileURL(`${folder}/component.mjs`).href)).default
Component.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render
async function settle() { await flush(); await nextTick(); await flush(); await nextTick() }
test('unavailable contact settings do not interrupt the article archive', async () => {
  Object.assign(globalThis, {
    __homeContacts: async () => { throw new Error('offline') },
    __homeList: async () => ({ items: [], total: 0 }),
    __homeTaxonomy: { categories: ref([]), loaded: true },
  })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', name: 'home', component: Component }] })
  await router.push('/'); await router.isReady()
  const container = document.createElement('div')
  const app = createApp(Component); app.use(router); app.use(ElementPlus)
  const vm = app.mount(container) as any
  try {
    await settle()
    assert.equal(vm.$.setupState.hasLoaded, true)
    assert.equal(vm.$.setupState.loadError, false)
    assert.equal(container.querySelector('a[href="https://github.com/example"]'), null)
    assert.match(container.textContent || '', /最近的文字/)
  } finally { app.unmount() }
})
test('homepage URL restores and normalizes filters, search resets page, and browser back restores them', async () => {
  const requests: any[] = []
  Object.assign(globalThis, { __homeContacts: async () => ({ github_url: 'https://github.com/example' }), __homeList: async (params: any) => { requests.push(params); return { items: [], total: 0 } }, __homeTaxonomy: { categories: ref([]), loaded: true } })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', name: 'home', component: Component }, { path: '/articles/:id', component: { template: '<p>article</p>' } }] })
  await router.push('/?q=%20vue%20&category=2&tag=3&page=4&unknown=bad'); await router.isReady()
  const container = document.createElement('div'); document.body.append(container)
  const app = createApp(Component); app.use(router); app.use(ElementPlus)
  const vm = app.mount(container) as any
  try {
    await settle()
    assert.equal(container.querySelector('a[href="https://github.com/example"]')?.textContent, 'GitHub')
    assert.equal(router.currentRoute.value.query.q, 'vue'); assert.equal(router.currentRoute.value.query.unknown, undefined)
    assert.deepEqual(requests.at(-1), { page: 4, size: 10, q: 'vue', category_id: 2, tag_id: 3 })
    const input = container.querySelector('input[type=search]') as HTMLInputElement
    input.value = 'sanic'; input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    container.querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })); await settle()
    assert.equal(requests.at(-1).page, 1); assert.equal(requests.at(-1).q, 'sanic')
    router.back(); await settle()
    assert.equal((container.querySelector('input[type=search]') as HTMLInputElement).value, 'vue')
    assert.equal(vm.$.setupState.page, 4)
    await router.push('/?page=2&tag=3&category=2&q=ordered'); await settle()
    assert.equal(requests.at(-1).q, 'ordered')
    await router.push('/articles/1?from=%2F%3Fq%3Dordered'); await settle()
    assert.equal(router.currentRoute.value.path, '/articles/1')
  } finally { app.unmount(); container.remove() }
})
