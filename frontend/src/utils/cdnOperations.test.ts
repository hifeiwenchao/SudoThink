import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CDN_URL_HISTORY_LIMIT, cdnOperationLimit, loadCdnUrlHistory, parseCdnUrls, saveCdnUrlHistory, validateCdnUrls } from './cdnOperations'

const limits = { refresh_file: 1000, refresh_directory: 100, refresh_regex: 1, preload: 100, max_url_length: 1024 }

test('URL history persists unique addresses with repeated submissions moved to the front', () => {
  const values = new Map<string, string>()
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
  }
  const first = 'https://cdn.example.com/A.png?v=1&size=2'
  const second = 'https://cdn.example.com/a.png?v=1&size=2'
  const pattern = 'https://cdn.example.com/static/[^/]*[0-9].*.jpg'
  const initial = saveCdnUrlHistory([` ${first} `, second, first, '', '  '], [], storage)
  assert.deepEqual(initial, [first, second])
  assert.deepEqual(loadCdnUrlHistory(storage), initial)
  const updated = saveCdnUrlHistory([pattern, second, pattern], initial, storage)
  assert.deepEqual(updated, [pattern, second, first])
  assert.deepEqual(loadCdnUrlHistory(storage), updated)
})

test('URL history retains at most 30 unique addresses while preserving new batch order', () => {
  const old = Array.from({ length: 35 }, (_, index) => `https://cdn.example.com/${index}.png`)
  const storage = { setItem() {} }
  const updated = saveCdnUrlHistory([old[34]!, old[0]!, old[34]!], old, storage)
  assert.equal(CDN_URL_HISTORY_LIMIT, 30)
  assert.equal(updated.length, 30)
  assert.deepEqual(updated, [old[34], ...old.slice(0, 29)])
  assert.deepEqual(loadCdnUrlHistory({ getItem: () => JSON.stringify(old) }), old.slice(0, 30))
})

test('malformed or blocked history storage does not break CDN operations', () => {
  for (const value of [null, '{broken', '{}', 'null', '123', '"https://cdn.example.com/a.png"']) {
    assert.deepEqual(loadCdnUrlHistory({ getItem: () => value }), [])
  }
  assert.deepEqual(loadCdnUrlHistory({ getItem: () => '[null, 1, "  ", " https://cdn.example.com/a.png ", "https://cdn.example.com/a.png"]' }), ['https://cdn.example.com/a.png'])
  assert.deepEqual(loadCdnUrlHistory({ getItem() { throw new Error('Storage blocked') } }), [])
  assert.deepEqual(saveCdnUrlHistory(['https://cdn.example.com/new.png'], ['https://cdn.example.com/old.png'], { setItem() { throw new Error('Storage full') } }), ['https://cdn.example.com/new.png', 'https://cdn.example.com/old.png'])

  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', { configurable: true, value: Object.defineProperty({}, 'localStorage', { get() { throw new Error('Storage blocked') } }) })
  try {
    assert.deepEqual(loadCdnUrlHistory(), [])
    assert.deepEqual(saveCdnUrlHistory(['https://cdn.example.com/a.png'], []), ['https://cdn.example.com/a.png'])
  } finally {
    if (previousWindow) Object.defineProperty(globalThis, 'window', previousWindow)
    else Reflect.deleteProperty(globalThis, 'window')
  }
})

test('multiline input trims and deduplicates addresses without changing CDN query or matching patterns', () => {
  const pattern = 'https://cdn.example.com/static/[^/]*[0-9][a-z].*.jpg?size=[0-9]'
  assert.deepEqual(parseCdnUrls(`  ${pattern}  \r\n\nhttps://cdn.example.com/a.png?a=1&b=2\n${pattern}`), [pattern, 'https://cdn.example.com/a.png?a=1&b=2'])
  assert.equal(validateCdnUrls([pattern], 'Regex', limits), '')
})

test('operation limits come from server configuration, with single-pattern batches enforced', () => {
  assert.equal(cdnOperationLimit('Regex', limits), 1)
  assert.match(validateCdnUrls(['https://cdn.example.com/a.*', 'https://cdn.example.com/b.*'], 'Regex', limits), /最多提交 1 条/)
  assert.match(validateCdnUrls(['https://cdn.example.com/a', 'https://cdn.example.com/b'], 'File', { ...limits, refresh_file: 1 }), /最多提交 1 条/)
  assert.match(validateCdnUrls([], 'File', limits), /至少输入/)
})

test('directory refresh accepts slash-terminated paths and preloading requires a file address', () => {
  assert.equal(validateCdnUrls(['https://cdn.example.com/images/'], 'Directory', limits), '')
  for (const address of ['https://cdn.example.com/images', 'https://cdn.example.com/images/?v=1']) {
    assert.match(validateCdnUrls([address], 'Directory', limits), /以 \/ 结尾/)
  }
  assert.match(validateCdnUrls(['https://cdn.example.com/'], 'Preload', limits), /仅支持文件地址/)
  assert.equal(validateCdnUrls(['https://another-cdn.example.net/a.png?version=2'], 'Preload', limits), '')
})

test('invalid or excessive URL batches are rejected before submitting to the CDN', () => {
  for (const address of ['file:///tmp/a', '/images/a.png', 'https://user:secret@cdn.example.com/a.png', 'https://cdn.example.com/a#', 'https://cdn.example.com/a b', 'https://cdn.example.com:80/a', 'https://127.0.0.1/a', 'https://*.example.com/a']) {
    assert.notEqual(validateCdnUrls([address], 'File', limits), '', address)
  }
  assert.match(validateCdnUrls(['https://cdn.example.com/' + 'x'.repeat(1024)], 'File', limits), /超过 1024 字符/)
  assert.match(validateCdnUrls(Array.from({ length: 11 }, (_, index) => `https://cdn${index}.example.com/a.png`), 'File', limits), /最多提交 10 个 CDN 域名/)
  assert.match(validateCdnUrls(['https://cdn.example.com/images/\\d+.jpg'], 'Regex', limits), /正则刷新仅支持/)
})
