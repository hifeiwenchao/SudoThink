import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it, type TestContext } from 'node:test'
import { JSDOM } from 'jsdom'
import { createThemeController, THEME_STORAGE_KEY } from './theme'

function browser(t: TestContext, dark = false, saved?: string) {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'https://blog.example.com', runScripts: 'outside-only',
  })
  const target = dom.window as unknown as Window
  let systemDark = dark
  const listeners = new Set<() => void>()
  const media = {
    get matches() { return systemDark },
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  }
  target.matchMedia = (() => media) as unknown as typeof target.matchMedia
  if (saved !== undefined) target.localStorage.setItem(THEME_STORAGE_KEY, saved)
  t.after(() => dom.window.close())
  return {
    dom, target,
    root: target.document.documentElement,
    changeSystem(value: boolean) {
      systemDark = value
      listeners.forEach((listener) => listener())
    },
    storage(value: string | null, key: string | null = THEME_STORAGE_KEY) {
      target.dispatchEvent(new dom.window.StorageEvent('storage', { key, newValue: value }))
    },
  }
}

describe('site theme', () => {
  for (const dark of [false, true]) {
    it(`defaults to the ${dark ? 'dark' : 'light'} system appearance`, (t) => {
      const env = browser(t, dark)
      const controller = createThemeController(env.target)
      t.after(controller.dispose)
      assert.equal(controller.preference, 'system')
      assert.equal(env.root.classList.contains('dark'), dark)
      assert.equal(env.root.style.colorScheme, dark ? 'dark' : 'light')
    })
  }

  it('updates immediately with the system and resumes following after a manual choice', (t) => {
    const env = browser(t)
    const changes: string[] = []
    const controller = createThemeController(env.target, (mode, theme) => changes.push(`${mode}:${theme}`))
    t.after(controller.dispose)
    env.changeSystem(true)
    assert.equal(env.root.classList.contains('dark'), true)
    controller.setPreference('light')
    env.changeSystem(false)
    env.changeSystem(true)
    assert.equal(env.root.classList.contains('dark'), false)
    assert.equal(env.target.localStorage.getItem(THEME_STORAGE_KEY), 'light')
    controller.setPreference('system')
    assert.equal(env.root.classList.contains('dark'), true)
    assert.equal(changes.at(-1), 'system:dark')
  })

  for (const preference of ['light', 'dark'] as const) {
    it(`restores an explicit ${preference} preference instead of the opposite system appearance`, (t) => {
      const env = browser(t, preference === 'light', preference)
      const controller = createThemeController(env.target)
      t.after(controller.dispose)
      assert.equal(controller.preference, preference)
      assert.equal(controller.resolvedTheme, preference)
      assert.equal(env.root.classList.contains('dark'), preference === 'dark')
    })
  }

  it('treats an invalid stored value as system', (t) => {
    const env = browser(t, true, 'invalid')
    const controller = createThemeController(env.target)
    t.after(controller.dispose)
    assert.equal(controller.preference, 'system')
    assert.equal(env.root.classList.contains('dark'), true)
  })

  it('still follows the system and allows switching when browser storage is unavailable', (t) => {
    const env = browser(t, true)
    Object.defineProperty(env.target, 'localStorage', { get() { throw new Error('Storage blocked') } })
    const controller = createThemeController(env.target)
    t.after(controller.dispose)
    assert.equal(env.root.classList.contains('dark'), true)
    assert.doesNotThrow(() => controller.setPreference('light'))
    assert.equal(env.root.classList.contains('dark'), false)
  })

  it('syncs another tab and returns to system when storage is cleared', (t) => {
    const env = browser(t, true)
    const controller = createThemeController(env.target)
    t.after(controller.dispose)
    env.storage('light')
    assert.equal(controller.preference, 'light')
    assert.equal(env.root.classList.contains('dark'), false)
    env.storage('dark', 'unrelated-key')
    assert.equal(controller.preference, 'light')
    env.storage(null, null)
    assert.equal(controller.preference, 'system')
    assert.equal(env.root.classList.contains('dark'), true)
  })

  it('removes listeners when disposed', (t) => {
    const env = browser(t)
    const controller = createThemeController(env.target)
    controller.dispose()
    env.changeSystem(true)
    env.storage('dark')
    assert.equal(env.root.classList.contains('dark'), false)
  })
})

describe('theme before the first paint', () => {
  for (const [dark, saved] of [[true, undefined], [false, 'dark'], [true, 'light'], [true, 'invalid']] as const) {
    it(`applies saved=${saved ?? 'none'} with systemDark=${dark} before loading the application`, (t) => {
      const env = browser(t, dark, saved)
      const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
      const script = Array.from(html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))
        .find((match) => match[1].includes(THEME_STORAGE_KEY))
      assert.ok(script, 'Theme initialization must run in the document head')
      assert.ok(html.indexOf(script[0]) < html.indexOf('</head>'))
      env.dom.window.eval(script[1])
      assert.equal(env.root.classList.contains('dark'), saved === 'dark' || (saved !== 'light' && dark))
    })
  }
})
