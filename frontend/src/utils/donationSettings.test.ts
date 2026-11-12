import assert from 'node:assert/strict'
import { test } from 'node:test'
import { setImmediate as flushPromises } from 'node:timers/promises'
import { JSDOM } from 'jsdom'
import { getDonationChannels, type DonationConfiguration } from './donations'

const dom = new JSDOM('<!doctype html><html><body></body></html>')
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  Element: dom.window.Element,
  SVGElement: dom.window.SVGElement,
})

const { createApp, defineComponent, h, nextTick } = await import('vue')
const { provideDonationSettings, useDonationSettings } = await import('../composables/useDonationSettings')

const enabled: DonationConfiguration = {
  enabled: true,
  wechat_qr_url: 'https://cdn.example.com/wechat.png',
  alipay_qr_url: '',
}

function mountEntries(loadSettings: (signal: AbortSignal) => Promise<DonationConfiguration>) {
  const entry = defineComponent({
    setup() {
      const settings = useDonationSettings()
      return () => getDonationChannels(settings.value).length ? h('button', '打赏') : null
    },
  })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(defineComponent({
    setup() {
      provideDonationSettings(loadSettings)
      return () => [h(entry), h(entry)]
    },
  }))
  app.mount(container)
  return { container, unmount: () => { app.unmount(); container.remove() } }
}

test('two support entries share a single settings request and both become available', async (t) => {
  let calls = 0
  let resolve!: (settings: DonationConfiguration) => void
  const entries = mountEntries(async () => {
    calls++
    return await new Promise<DonationConfiguration>((done) => { resolve = done })
  })
  t.after(entries.unmount)
  assert.equal(entries.container.querySelectorAll('button').length, 0)
  resolve(enabled)
  await flushPromises()
  await nextTick()
  assert.equal(calls, 1)
  assert.equal(entries.container.querySelectorAll('button').length, 2)
})

test('failed public settings requests keep every support entry hidden', async (t) => {
  const entries = mountEntries(async () => { throw new Error('offline') })
  t.after(entries.unmount)
  await flushPromises()
  await nextTick()
  assert.equal(entries.container.querySelectorAll('button').length, 0)
})

test('unmounting the public shell cancels its outstanding settings request', () => {
  let signal: AbortSignal | undefined
  const entries = mountEntries(async (requestSignal) => {
    signal = requestSignal
    return await new Promise<DonationConfiguration>(() => {})
  })
  assert.equal(signal?.aborted, false)
  entries.unmount()
  assert.equal(signal?.aborted, true)
})
