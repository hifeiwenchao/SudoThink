import assert from 'node:assert/strict'
import { test } from 'node:test'
import { JSDOM } from 'jsdom'
import { readCommenter, saveCommenter, validateComment } from './commenter'

test('accepts Han, ASCII letters, digits and underscores within the nickname code point limit', () => {
  for (const nickname of ['张三_A9', '𠮷'.repeat(32)]) {
    assert.equal(validateComment({ nickname, email: '', content: '有帮助，谢谢分享。' }), null)
  }
  for (const nickname of ['', ' ', 'a'.repeat(33), '张 三', 'a-b', 'a@b', 'é', 'ひらがな', '😀']) {
    assert.ok(validateComment({ nickname, email: '', content: 'comment' }), nickname)
  }
})

test('rejects empty or oversized comment text and malformed optional email', () => {
  for (const content of ['  \n ', '文'.repeat(1001)]) {
    assert.ok(validateComment({ nickname: '读者', email: '', content }))
  }
  assert.equal(validateComment({ nickname: '读者', email: '', content: '😀'.repeat(1000) }), null)
  assert.equal(validateComment({ nickname: '读者', email: 'reader@example.com', content: '正文' }), null)
  assert.ok(validateComment({ nickname: '读者', email: 'not-an-email', content: '正文' }))
})

test('remembers editable identity without storing comment text', () => {
  const dom = new JSDOM('', { url: 'https://blog.example.com/' })
  try {
    const storage = dom.window.localStorage
    assert.deepEqual(readCommenter(storage), { nickname: '', email: '' })
    saveCommenter({ nickname: '  读者_A  ', email: ' reader@example.com ' }, storage)
    assert.deepEqual(readCommenter(storage), { nickname: '读者_A', email: 'reader@example.com' })
    saveCommenter({ nickname: '新昵称', email: '' }, storage)
    assert.deepEqual(readCommenter(storage), { nickname: '新昵称', email: '' })
  } finally { dom.window.close() }
})

test('corrupt or blocked browser storage does not break commenting', () => {
  assert.deepEqual(readCommenter({ getItem: () => '{bad json' }), { nickname: '', email: '' })
  assert.deepEqual(readCommenter({ getItem: () => '{"nickname":42,"email":[]}' }), { nickname: '', email: '' })
  assert.deepEqual(readCommenter({ getItem: () => { throw new Error('blocked') } }), { nickname: '', email: '' })
  assert.doesNotThrow(() => saveCommenter({ nickname: '读者', email: '' }, { setItem: () => { throw new Error('full') } }))
})
