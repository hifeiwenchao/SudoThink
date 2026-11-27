import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
const dom = new JSDOM('<html><body></body></html>', { url: 'https://example.com/', pretendToBeVisual: true })
Object.assign(globalThis, { MouseEvent: dom.window.MouseEvent, window: dom.window, document: dom.window.document, Document: dom.window.Document, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node, MutationObserver: dom.window.MutationObserver, getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame, history: dom.window.history, location: dom.window.location, ResizeObserver: class { observe() {} unobserve() {} disconnect() {} } })
const { createApp, nextTick } = await import('vue')
const { createRouter, createMemoryHistory } = await import('vue-router')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.about-contacts-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const transpile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
async function component(path: string, name: string) {
  const { descriptor } = parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: name })
  const source = script.content
    .replace(/import .* from '@\/api\/about'/, 'const aboutApi = globalThis.__aboutApi')
    .replace(/import RichTextEditor .*\nimport ArticleContent .*/, 'const RichTextEditor = { template: "<div />" }; const ArticleContent = { template: "<div />" }')
    .replace(/(['"])@\/utils\/([^'"]+)\1/g, (_, _q, file) => JSON.stringify(new URL(`./${file}.ts`, import.meta.url).href))
  writeFileSync(`${folder}/${name}.mjs`, transpile(source))
  const template = compileTemplate({ source: descriptor.template!.content, filename: path, id: name, compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
  writeFileSync(`${folder}/${name}-template.mjs`, transpile(template.code))
  const value = (await import(pathToFileURL(`${folder}/${name}.mjs`).href)).default
  value.render = (await import(pathToFileURL(`${folder}/${name}-template.mjs`).href)).render
  return value
}
async function settle() { await flush(); await nextTick(); await flush(); await nextTick() }
test('public contact links hide blank and unsafe fields and expose secure accessible destinations', async () => {
  const ContactLinks = await component('../components/ContactLinks.vue', 'contacts')
  const container = document.createElement('div')
  const app = createApp(ContactLinks, { contacts: { github_url: 'https://github.com/example', email: 'me@example.com', x_url: 'javascript:alert(1)', facebook_url: '', instagram_url: 'https://instagram.com/example' } })
  app.mount(container)
  try {
    const links = [...container.querySelectorAll('a')]
    assert.equal(links.length, 3)
    assert.equal(links.find(link => link.getAttribute('aria-label') === '邮箱')?.getAttribute('href'), 'mailto:me@example.com')
    for (const link of links.filter(link => link.href.startsWith('https:'))) {
      assert.equal(link.target, '_blank'); assert.equal(link.rel, 'noopener noreferrer'); assert.ok(link.getAttribute('aria-label'))
    }
  } finally { app.unmount() }
  for (const unsafe of ['//evil.com', 'data:text/html,bad', 'https://name:pass@example.com', 'https://exa\nmple.com', 'https://exa\u200bmple.com']) {
    const host = document.createElement('div')
    const entry = createApp(ContactLinks, { contacts: { github_url: unsafe, email: 'a@example.com?subject=bad' } })
    entry.mount(host); assert.equal(host.querySelectorAll('a').length, 0); entry.unmount()
  }
})
test('admin contacts load, track edits, save, reload and clear without losing the about content', async () => {
  let stored: any = { id: 1, title: '关于我', content: '<p>介绍</p>', updated_at: null, github_url: 'https://github.com/old', email: 'old@example.com', x_url: '', facebook_url: '', instagram_url: '' }
  const saves: any[] = []
  Object.assign(globalThis, { __aboutApi: { adminGet: async () => ({ ...stored }), save: async (input: any) => { saves.push(input); stored = { ...stored, ...input }; return { ...stored } } } })
  const AdminAbout = await component('../views/AdminAbout.vue', 'admin-about')
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: AdminAbout }] })
  await router.push('/'); await router.isReady()
  async function mount() {
    const container = document.createElement('div'); document.body.append(container)
    const app = createApp({ template: '<router-view />' }); app.use(router); app.use(ElementPlus); app.mount(container); await settle()
    return { container, unmount() { app.unmount(); container.remove() } }
  }
  let view = await mount()
  function edit(id: string, value: string) {
    const input = view.container.querySelector(`#about-${id}`) as HTMLInputElement
    assert.ok(input, `${id} is editable`)
    input.value = value; input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  }
  async function save() { [...view.container.querySelectorAll('button')].find(button => button.textContent?.includes('保存内容'))!.click(); await settle() }
  try {
    assert.equal((view.container.querySelector('#about-github_url') as HTMLInputElement)?.value, stored.github_url)
    edit('github_url', 'https://github.com/new'); edit('email', 'new@example.com'); edit('x_url', 'https://x.com/new'); edit('facebook_url', 'https://facebook.com/new'); edit('instagram_url', 'https://instagram.com/new')
    await nextTick(); assert.match(view.container.textContent!, /有未保存的修改/)
    await save(); assert.equal(saves.length, 1); assert.equal(saves[0].instagram_url, 'https://instagram.com/new'); assert.equal(saves[0].content, '<p>介绍</p>')
    assert.doesNotMatch(view.container.textContent!, /有未保存的修改/)
    view.unmount(); view = await mount()
    assert.equal((view.container.querySelector('#about-email') as HTMLInputElement).value, 'new@example.com')
    edit('github_url', 'javascript:alert(1)'); await save(); assert.equal(saves.length, 1)
    edit('github_url', ''); edit('email', ''); edit('x_url', ''); edit('facebook_url', ''); edit('instagram_url', '')
    await save(); assert.equal(saves.length, 2)
    for (const key of ['github_url', 'email', 'x_url', 'facebook_url', 'instagram_url']) assert.equal(stored[key], '')
    view.unmount(); view = await mount(); assert.equal((view.container.querySelector('#about-github_url') as HTMLInputElement).value, '')
  } finally { view.unmount() }
})
