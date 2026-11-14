import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { MusicSettingsInput } from '../api/music'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, {
  window: dom.window, document: dom.window.document, Document: dom.window.Document,
  Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement,
  Node: dom.window.Node, MutationObserver: dom.window.MutationObserver,
  MouseEvent: dom.window.MouseEvent, getComputedStyle: dom.window.getComputedStyle,
  requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame,
  ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
})
dom.window.HTMLMediaElement.prototype.pause = () => {}
const { createApp, nextTick } = await import('vue')
const { default: ElementPlus } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.admin-music-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })

function compile(source: string) {
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
}
const apiTarget = `${folder}/api.mjs`
writeFileSync(apiTarget, `export const musicApi = { adminGet: (...args) => globalThis.__musicAdmin.get(...args), save: (...args) => globalThis.__musicAdmin.save(...args) }; export const uploadsApi = { config: () => globalThis.__musicAdmin.config(), policy: () => { throw new Error('unexpected policy'); } }; export const uploadMedia = (...args) => globalThis.__musicAdmin.upload(...args);`)
const { descriptor } = parse(readFileSync(new URL('../views/AdminMusic.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'admin-music-test' })
const source = script.content
  .replace(/import \{ onBeforeRouteLeave \} from 'vue-router'/, 'const onBeforeRouteLeave = () => {}')
  .replace(/(['"])@\/(?:api\/music|api\/uploads|utils\/mediaUpload)\1/g, JSON.stringify(pathToFileURL(apiTarget).href))
const target = `${folder}/AdminMusic.mjs`
writeFileSync(target, compile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'AdminMusic.vue', id: 'admin-music-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const AdminMusic = (await import(pathToFileURL(target).href)).default
AdminMusic.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render

type State = {
  form: MusicSettingsInput; uploadErrors: string[]; saveError: string; validationError: string; uploading: boolean; isDirty: boolean
  selectFiles: (event: Event) => Promise<void>; save: () => Promise<void>; move: (index: number, delta: number) => void; remove: (index: number) => void; cancelUpload: () => void
}
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
function selection(...names: string[]) { return { target: { files: names.map(name => new File(['music'], name, { type: 'audio/mpeg' })), value: 'selected' } } as unknown as Event }
async function mount(options: {
  settings?: MusicSettingsInput; get?: () => Promise<MusicSettingsInput>; save?: (input: MusicSettingsInput) => Promise<MusicSettingsInput>
  upload?: (file: File, options: { signal: AbortSignal }) => Promise<{ url: string; key: string; kind: string }>
} = {}) {
  const saves: MusicSettingsInput[] = []
  Object.assign(globalThis, { __musicAdmin: {
    async get() { return options.get?.() ?? options.settings ?? { enabled: false, tracks: [] } },
    async save(input: MusicSettingsInput) { saves.push(input); return options.save?.(input) ?? input },
    async config() { return { enabled: true, audio_types: { 'audio/mpeg': ['.mp3'] }, audio_max_bytes: 52428800 } },
    async upload(file: File, uploadOptions: { signal: AbortSignal }) { return options.upload?.(file, uploadOptions) ?? { url: `https://cdn.example.com/media/audios/${file.name}`, key: file.name, kind: 'audio' } },
  } })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(AdminMusic)
  app.use(ElementPlus)
  const instance = app.mount(container) as unknown as { $: { setupState: State } }
  await settle()
  return { container, state: instance.$.setupState, saves, unmount: () => { app.unmount(); container.remove() } }
}

test('multiple uploads preserve successful songs when another upload fails, and save their edited order', async t => {
  const view = await mount({ upload: async file => {
    if (file.name === 'failed.mp3') throw new Error('network failed')
    return { url: `https://cdn.example.com/media/audios/${file.name}`, key: file.name, kind: 'audio' }
  } })
  t.after(view.unmount)
  await view.state.selectFiles(selection('first.mp3', 'failed.mp3', 'last.mp3'))
  assert.deepEqual(view.state.form.tracks.map(track => track.title), ['first', 'last'])
  assert.match(view.state.uploadErrors[0]!, /failed.mp3.*network failed/)
  assert.equal(view.state.isDirty, true)
  view.state.form.enabled = true
  view.state.form.tracks[1]!.title = ' Last song '
  view.state.form.tracks[1]!.artist = ' Artist '
  view.state.move(1, -1)
  await view.state.save()
  assert.deepEqual(view.saves[0], { enabled: true, tracks: [
    { title: 'Last song', artist: 'Artist', url: 'https://cdn.example.com/media/audios/last.mp3' },
    { title: 'first', artist: '', url: 'https://cdn.example.com/media/audios/first.mp3' },
  ] })
  assert.equal(view.state.isDirty, false)
})

test('canceling a batch preserves completed uploads and prevents pending files from entering the playlist', async t => {
  let started!: () => void
  const secondStarted = new Promise<void>(resolve => { started = resolve })
  const view = await mount({ upload: async (file, { signal }) => {
    if (file.name === 'second.mp3') {
      started()
      await new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError')), { once: true }))
    }
    return { url: `https://cdn.example.com/media/audios/${file.name}`, key: file.name, kind: 'audio' }
  } })
  t.after(view.unmount)
  const batch = view.state.selectFiles(selection('first.mp3', 'second.mp3', 'third.mp3'))
  await secondStarted
  await view.state.save()
  assert.equal(view.saves.length, 0)
  view.state.cancelUpload()
  await batch
  assert.deepEqual(view.state.form.tracks.map(track => track.title), ['first'])
  assert.equal(view.state.uploading, false)
})

test('song validation and failed saves retain current edits; empty playlists can be saved', async t => {
  let fail = true
  const view = await mount({ save: async input => { if (fail) throw new Error('offline'); return input } })
  t.after(view.unmount)
  await view.state.selectFiles(selection('song.mp3'))
  view.state.form.tracks[0]!.title = ' '
  await view.state.save()
  assert.equal(view.saves.length, 0)
  assert.match(view.state.validationError, /曲名/)
  view.state.form.tracks[0]!.title = 'Retained'
  await view.state.save()
  assert.equal(view.state.form.tracks[0]!.title, 'Retained')
  assert.equal(view.state.isDirty, true)
  assert.match(view.state.saveError, /已保留/)
  fail = false
  view.state.remove(0)
  await view.state.save()
  assert.deepEqual(view.saves.at(-1), { enabled: false, tracks: [] })
})

test('failed initial loading disables saving and the playlist cap rejects oversized batches', async t => {
  const failed = await mount({ get: async () => { throw new Error('offline') } })
  await failed.state.selectFiles(selection('song.mp3'))
  await failed.state.save()
  assert.equal(failed.saves.length, 0)
  assert.equal(failed.state.form.tracks.length, 0)
  assert.ok(failed.container.textContent?.includes('音乐设置加载失败'))
  failed.unmount()
  const capped = await mount()
  t.after(capped.unmount)
  await capped.state.selectFiles(selection(...Array.from({ length: 101 }, (_, index) => `${index}.mp3`)))
  assert.equal(capped.state.form.tracks.length, 0)
  assert.match(capped.state.uploadErrors[0]!, /最多保留 100 首/)
})
