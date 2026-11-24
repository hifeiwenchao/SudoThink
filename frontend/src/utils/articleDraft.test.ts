import assert from 'node:assert/strict'
import { test } from 'node:test'
import { JSDOM } from 'jsdom'
import { readArticleDraft, writeArticleDraft, removeArticleDraft } from './articleDraft'
const dom = new JSDOM('', { url: 'https://admin.example.com' })
Object.assign(globalThis, { window: dom.window })
const form = { title: '标题', summary: '', content: '<p>正文</p>', cover: '', category_id: null, tag_ids: [1] }
test('drafts isolate users and article identities and clear only saved identity', () => {
  assert.equal(writeArticleDraft(1, null, form, 'server'), true)
  assert.deepEqual(readArticleDraft(1, null)?.form, form)
  assert.equal(readArticleDraft(2, null), null)
  assert.equal(readArticleDraft(1, 1), null)
  assert.equal(readArticleDraft(1, null)?.baseline, 'server')
  removeArticleDraft(1, null)
  assert.equal(readArticleDraft(1, null), null)
})
test('broken storage and invalid draft are safe and report failure', () => {
  window.localStorage.setItem('sudothink:article-draft:1:new', '{bad')
  assert.equal(readArticleDraft(1, null), null)
  Object.defineProperty(window, 'localStorage', { get() { throw Error('denied') } })
  assert.equal(readArticleDraft(1, null), null)
  assert.equal(writeArticleDraft(1, null, form, ''), false)
})
