import assert from 'node:assert/strict'
import { test } from 'node:test'
import { cdnOperationLimit, parseCdnUrls, validateCdnUrls } from './cdnOperations'

const limits = { refresh_file: 1000, refresh_directory: 100, refresh_regex: 1, preload: 100, max_url_length: 1024 }

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
