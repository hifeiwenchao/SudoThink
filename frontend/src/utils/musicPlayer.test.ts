import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { MusicSettings } from '../api/music'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://blog.example.com/' })
Object.assign(globalThis, {
  window: dom.window, document: dom.window.document,
  Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement,
  Node: dom.window.Node,
})
const { createApp, nextTick } = await import('vue')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.music-player-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })

function compile(source: string) {
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
}
const { descriptor } = parse(readFileSync(new URL('../components/MusicPlayer.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'music-player-test' })
const target = `${folder}/MusicPlayer.mjs`
writeFileSync(target, compile(script.content.replace(/import\s*\{[^}]+\}\s*from\s*['"]@\/api\/music['"]/g,
  'const musicApi = { get: (...args) => globalThis.__musicGet(...args) }')))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'MusicPlayer.vue', id: 'music-player-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const MusicPlayer = (await import(pathToFileURL(target).href)).default
MusicPlayer.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render

const settings: MusicSettings = { enabled: true, tracks: [
  { title: '第一首', artist: '歌手甲', url: 'https://cdn.example.com/first.mp3' },
  { title: '第二首', artist: '', url: 'https://cdn.example.com/second.mp3' },
] }

const paused = new WeakMap<HTMLMediaElement, boolean>()
let playCalls: HTMLMediaElement[] = []
let playImplementation: (() => Promise<void>) | undefined
let loads = 0
Object.defineProperty(dom.window.HTMLMediaElement.prototype, 'paused', { get() { return paused.get(this) ?? true } })
dom.window.HTMLMediaElement.prototype.play = function () {
  playCalls.push(this)
  paused.set(this, false)
  this.dispatchEvent(new dom.window.Event('play'))
  return playImplementation?.() ?? Promise.resolve()
}
dom.window.HTMLMediaElement.prototype.pause = function () {
  paused.set(this, true)
  this.dispatchEvent(new dom.window.Event('pause'))
}
dom.window.HTMLMediaElement.prototype.load = function () { loads++ }

async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
async function mount(load: (signal: AbortSignal) => Promise<MusicSettings> = async () => settings) {
  playCalls = []
  playImplementation = undefined
  loads = 0
  let signal!: AbortSignal
  Object.assign(globalThis, { __musicGet: (value: AbortSignal) => { signal = value; return load(value) } })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(MusicPlayer)
  app.mount(container)
  await settle()
  const click = async (label: string) => {
    const button = container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)
    assert.ok(button, label)
    button.click()
    await settle()
  }
  return { container, click, signal, unmount: () => { app.unmount(); container.remove() } }
}

test('empty, disabled, and failed settings keep the entire player hidden', async () => {
  for (const load of [async () => ({ enabled: true, tracks: [] }), async () => ({ ...settings, enabled: false }), async () => { throw new Error('offline') }]) {
    const view = await mount(load)
    assert.equal(view.container.querySelector('section'), null)
    assert.equal(view.container.querySelector('audio'), null)
    view.unmount()
  }
})

test('music starts only after visitor intent and retains its audio node while opening the list', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  const element = view.container.querySelector('audio')!
  assert.equal(element.preload, 'none')
  assert.equal(element.hasAttribute('autoplay'), false)
  assert.equal(playCalls.length, 0)
  await view.click('播放音乐')
  assert.equal(playCalls.length, 1)
  assert.equal(element.volume, .5)
  await view.click('展开音乐列表')
  assert.equal(view.container.querySelector('audio'), element)
  assert.match(view.container.textContent!, /歌手甲/)
  await view.click('暂停音乐')
  assert.equal(element.paused, true)
})

test('next, previous, playlist selection and ended follow the saved order and wrap around', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  await view.click('下一首')
  assert.match(view.container.querySelector('audio')!.src, /second.mp3$/)
  await view.click('展开音乐列表')
  await view.click('上一首')
  assert.match(view.container.querySelector('audio')!.src, /first.mp3$/)
  await view.click('播放 第二首')
  const second = view.container.querySelector('audio')!
  second.dispatchEvent(new dom.window.Event('ended'))
  await settle()
  assert.match(view.container.querySelector('audio')!.src, /first.mp3$/)
  assert.ok(playCalls.length >= 4)
})

test('single-track lists loop on ended while track navigation stays disabled', async (t) => {
  const view = await mount(async () => ({ ...settings, tracks: settings.tracks.slice(0, 1) }))
  t.after(view.unmount)
  assert.equal(view.container.querySelector<HTMLButtonElement>('[aria-label="下一首"]')!.disabled, true)
  const element = view.container.querySelector('audio')!
  element.currentTime = 20
  element.dispatchEvent(new dom.window.Event('ended'))
  await settle()
  assert.equal(element.currentTime, 0)
  assert.equal(playCalls.length, 1)
})

test('failed play promises show retry, reload the audio on retry and never automatically skip', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  playImplementation = async () => { throw new Error('blocked') }
  await view.click('播放音乐')
  await view.click('展开音乐列表')
  assert.match(view.container.querySelector('[role="alert"]')!.textContent!, /无法播放/)
  assert.match(view.container.querySelector('audio')!.src, /first.mp3$/)
  playImplementation = undefined
  const retry = Array.from(view.container.querySelectorAll('button')).find(button => button.textContent === '重试')!
  retry.click()
  await settle()
  assert.equal(loads, 1)
  assert.equal(view.container.querySelector('[role="alert"]'), null)
})

test('stale failures from a previous track cannot replace the current playback state', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  let reject!: (error: Error) => void
  playImplementation = () => new Promise<void>((_, fail) => { reject = fail })
  await view.click('播放音乐')
  playImplementation = undefined
  await view.click('下一首')
  reject(new Error('old track failed'))
  await settle()
  assert.match(view.container.querySelector('audio')!.src, /second.mp3$/)
  assert.ok(view.container.querySelector('[aria-label="暂停音乐"]'))
  await view.click('展开音乐列表')
  assert.equal(view.container.querySelector('[role="alert"]'), null)
})

test('progress and volume controls update the media element; unmount pauses and releases it', async () => {
  const view = await mount()
  await view.click('展开音乐列表')
  const element = view.container.querySelector('audio')!
  Object.defineProperty(element, 'duration', { value: 120, configurable: true })
  element.dispatchEvent(new dom.window.Event('loadedmetadata'))
  await settle()
  const seek = view.container.querySelector<HTMLInputElement>('[aria-label="播放进度"]')!
  seek.value = '30'
  seek.dispatchEvent(new dom.window.Event('input'))
  assert.equal(element.currentTime, 30)
  const volume = view.container.querySelector<HTMLInputElement>('[aria-label="音量"]')!
  volume.value = '.25'
  volume.dispatchEvent(new dom.window.Event('input'))
  assert.equal(element.volume, .25)
  await view.click('播放音乐')
  view.unmount()
  assert.equal(view.signal.aborted, true)
  assert.equal(element.paused, true)
  assert.equal(element.getAttribute('src'), null)
  assert.equal(loads, 1)
})
