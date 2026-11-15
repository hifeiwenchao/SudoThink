import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after, beforeEach } from 'node:test'
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
beforeEach(() => { window.localStorage.clear() })

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
async function finishTrack(element: HTMLMediaElement) {
  paused.set(element, true)
  element.dispatchEvent(new dom.window.Event('ended'))
  await settle()
}
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

test('playing music shows an animated wave indicator and hides it when paused', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  assert.equal(view.container.querySelector('.music-wave'), null)
  await view.click('播放音乐')
  assert.equal(view.container.querySelectorAll('.music-wave i').length, 4)
  await view.click('暂停音乐')
  assert.equal(view.container.querySelector('.music-wave'), null)
})

test('clicking outside the player closes the expanded playlist while clicks inside keep it open', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  await view.click('展开音乐列表')
  assert.ok(view.container.querySelector('.music-panel'))

  const inside = view.container.querySelector('.music-panel')!
  inside.dispatchEvent(new dom.window.Event('pointerdown', { bubbles: true }))
  await settle()
  assert.ok(view.container.querySelector('.music-panel'))

  document.body.dispatchEvent(new dom.window.Event('pointerdown', { bubbles: true }))
  await settle()
  assert.equal(view.container.querySelector('.music-panel'), null)
  assert.equal(view.container.querySelector<HTMLButtonElement>('.music-mini-info')?.getAttribute('aria-expanded'), 'false')
})

test('manual navigation wraps in saved order and playlist selection plays the chosen track', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  await view.click('下一首')
  assert.match(view.container.querySelector('audio')!.src, /second.mp3$/)
  await view.click('展开音乐列表')
  await view.click('上一首')
  assert.match(view.container.querySelector('audio')!.src, /first.mp3$/)
  await view.click('播放 第二首')
  assert.match(view.container.querySelector('audio')!.src, /second.mp3$/)
  await view.click('下一首')
  assert.match(view.container.querySelector('audio')!.src, /first.mp3$/)
  assert.ok(playCalls.length >= 4)
})

test('sequence mode advances automatically and stops after the final track', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  await view.click('展开音乐列表')
  assert.equal(view.container.querySelector('[aria-label="顺序播放"]')?.getAttribute('aria-pressed'), 'true')
  await view.click('播放音乐')
  await finishTrack(view.container.querySelector('audio')!)
  const last = view.container.querySelector('audio')!
  assert.match(last.src, /second.mp3$/)
  const calls = playCalls.length
  await finishTrack(last)
  assert.equal(view.container.querySelector('audio'), last)
  assert.equal(playCalls.length, calls)
  assert.ok(view.container.querySelector('[aria-label="播放音乐"]'))
  assert.equal(view.container.querySelector('.music-wave'), null)
})

test('single repeat restarts the current track while manual next still changes the song', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  await view.click('展开音乐列表')
  await view.click('单曲循环')
  assert.equal(playCalls.length, 0, 'changing modes must not start playback')
  await view.click('播放音乐')
  const element = view.container.querySelector('audio')!
  element.currentTime = 120
  await finishTrack(element)
  assert.equal(view.container.querySelector('audio'), element)
  assert.equal(element.currentTime, 0)
  assert.equal(element.paused, false)
  assert.equal(playCalls.length, 2)
  await view.click('下一首')
  assert.match(view.container.querySelector('audio')!.src, /second.mp3$/)
})

test('single-track navigation stays disabled and ending follows the selected mode', async (t) => {
  const view = await mount(async () => ({ ...settings, tracks: settings.tracks.slice(0, 1) }))
  t.after(view.unmount)
  assert.equal(view.container.querySelector<HTMLButtonElement>('[aria-label="下一首"]')!.disabled, true)
  await view.click('展开音乐列表')
  const element = view.container.querySelector('audio')!
  await view.click('播放音乐')
  await finishTrack(element)
  assert.equal(playCalls.length, 1, 'a one-song sequence ends after that song')
  await view.click('单曲循环')
  element.currentTime = 20
  await finishTrack(element)
  assert.equal(element.currentTime, 0)
  assert.equal(playCalls.length, 2)
  await view.click('随机播放')
  element.currentTime = 20
  await finishTrack(element)
  assert.equal(element.currentTime, 0)
  assert.equal(playCalls.length, 3)
})

test('random playback skips the current song and previous returns to an actually played song', async (t) => {
  const view = await mount(async () => ({ ...settings, tracks: [
    ...settings.tracks, { title: '第三首', artist: '', url: 'https://cdn.example.com/third.mp3' },
  ] }))
  t.after(view.unmount)
  await view.click('展开音乐列表')
  await view.click('随机播放')
  const originalRandom = Math.random
  t.after(() => { Math.random = originalRandom })
  Math.random = () => .99
  await view.click('下一首')
  assert.match(view.container.querySelector('audio')!.src, /third.mp3$/)
  Math.random = () => 0
  await finishTrack(view.container.querySelector('audio')!)
  assert.match(view.container.querySelector('audio')!.src, /first.mp3$/)
  await view.click('上一首')
  assert.match(view.container.querySelector('audio')!.src, /third.mp3$/)
  for (let index = 0; index < 6; index++) {
    const previous = view.container.querySelector('audio')!.src
    await view.click('下一首')
    assert.notEqual(view.container.querySelector('audio')!.src, previous)
  }
})

test('mode changes preserve playback and the selected preference survives a remount', async (t) => {
  let view = await mount()
  t.after(() => view.unmount())
  await view.click('播放音乐')
  const element = view.container.querySelector('audio')!
  element.currentTime = 37
  await view.click('展开音乐列表')
  await view.click('随机播放')
  assert.equal(view.container.querySelector('audio'), element)
  assert.equal(element.currentTime, 37)
  assert.equal(element.paused, false)
  assert.equal(playCalls.length, 1)
  assert.equal(window.localStorage.getItem('sudothink:music-play-mode'), 'random')
  view.unmount()
  view = await mount()
  await view.click('展开音乐列表')
  assert.equal(view.container.querySelector('[aria-label="随机播放"]')?.getAttribute('aria-pressed'), 'true')
  assert.equal(playCalls.length, 0, 'restoring a mode must not start playback')
})

test('the collapsed player cycles modes with one button without opening the list or interrupting audio', async (t) => {
  const view = await mount()
  t.after(view.unmount)
  const modeButton = view.container.querySelector<HTMLButtonElement>('.music-mini-mode')
  assert.ok(modeButton, 'the collapsed player must expose its own mode switch')
  const sequenceLabel = '播放模式：顺序播放，点击切换为单曲循环'
  const singleLabel = '播放模式：单曲循环，点击切换为随机播放'
  const randomLabel = '播放模式：随机播放，点击切换为顺序播放'
  assert.equal(modeButton.getAttribute('aria-label'), sequenceLabel)
  assert.equal(modeButton.title, sequenceLabel)
  await view.click(sequenceLabel)
  assert.equal(modeButton.getAttribute('aria-label'), singleLabel)
  assert.equal(modeButton.title, singleLabel)
  assert.equal(playCalls.length, 0, 'mode switching must not autoplay')

  await view.click('播放音乐')
  const element = view.container.querySelector('audio')!
  element.currentTime = 37
  for (const [label, nextLabel, mode] of [
    [singleLabel, randomLabel, 'random'],
    [randomLabel, sequenceLabel, 'sequence'],
    [sequenceLabel, singleLabel, 'single'],
  ] as const) {
    await view.click(label)
    assert.equal(modeButton.getAttribute('aria-label'), nextLabel)
    assert.equal(modeButton.title, nextLabel)
    assert.equal(window.localStorage.getItem('sudothink:music-play-mode'), mode)
    assert.equal(view.container.querySelector('.music-panel'), null)
    assert.equal(view.container.querySelector('audio'), element)
    assert.equal(element.currentTime, 37)
    assert.equal(element.paused, false)
    assert.equal(playCalls.length, 1)
  }
})

test('the mini mode button stays synchronized with the expanded choices and restores its saved mode', async (t) => {
  let view = await mount()
  t.after(() => view.unmount())
  await view.click('展开音乐列表')
  await view.click('随机播放')
  const modeButton = view.container.querySelector<HTMLButtonElement>('.music-mini-mode')!
  assert.equal(modeButton.getAttribute('aria-label'), '播放模式：随机播放，点击切换为顺序播放')
  await view.click('播放模式：随机播放，点击切换为顺序播放')
  assert.ok(view.container.querySelector('.music-panel'), 'the mode button must not close the open list')
  assert.equal(view.container.querySelector('[aria-label="顺序播放"]')?.getAttribute('aria-pressed'), 'true')
  assert.equal(view.container.querySelector('[aria-label="随机播放"]')?.getAttribute('aria-pressed'), 'false')
  await view.click('播放模式：顺序播放，点击切换为单曲循环')
  assert.equal(view.container.querySelector('[aria-label="单曲循环"]')?.getAttribute('aria-pressed'), 'true')
  view.unmount()
  view = await mount()
  assert.equal(view.container.querySelector('.music-mini-mode')?.getAttribute('aria-label'), '播放模式：单曲循环，点击切换为随机播放')
  assert.equal(view.container.querySelector('.music-panel'), null)
  assert.equal(playCalls.length, 0)
})

test('invalid or unavailable saved modes fall back safely and mode switching remains usable', async () => {
  window.localStorage.setItem('sudothink:music-play-mode', 'invalid-mode')
  const invalid = await mount()
  try {
    await invalid.click('展开音乐列表')
    assert.equal(invalid.container.querySelector('[aria-label="顺序播放"]')?.getAttribute('aria-pressed'), 'true')
  } finally { invalid.unmount() }

  const descriptor = Object.getOwnPropertyDescriptor(window, 'localStorage')!
  Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new Error('Storage unavailable') } })
  let blocked: Awaited<ReturnType<typeof mount>> | undefined
  try {
    blocked = await mount()
    await blocked.click('展开音乐列表')
    assert.equal(blocked.container.querySelector('[aria-label="顺序播放"]')?.getAttribute('aria-pressed'), 'true')
    await blocked.click('单曲循环')
    assert.equal(blocked.container.querySelector('[aria-label="单曲循环"]')?.getAttribute('aria-pressed'), 'true')
    await blocked.click('播放音乐')
    assert.equal(blocked.container.querySelector('audio')!.paused, false)
  } finally {
    blocked?.unmount()
    Object.defineProperty(window, 'localStorage', descriptor)
  }
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
