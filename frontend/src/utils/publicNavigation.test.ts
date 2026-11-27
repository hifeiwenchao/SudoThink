import assert from 'node:assert/strict'
import { test } from 'node:test'
import { JSDOM } from 'jsdom'
import { parseArticleQuery, articleQuery, safeListReturn, canReturnToListHistory } from './publicNavigation'
import { setPageSeo, routeSeo } from './seo'

test('admin and editor tabs show their actual page names while remaining private', () => {
  for (const [path, title] of [['/admin', '后台概览'], ['/admin/todos', '待办事项'], ['/admin/comments', '评论管理'], ['/login', '管理员登录'], ['/articles/new', '创作新文章'], ['/articles/12/edit', '编辑文章']]) {
    assert.equal(routeSeo(path!, true).title, title)
    assert.equal(routeSeo(path!, true).noindex, true)
  }
  assert.equal(routeSeo('/admin/unknown', true).title, '页面未找到')
})

test('article query normalizes all filters and omits invalid values', () => {
  assert.deepEqual(parseArticleQuery({ q: '  vue  ', category: '02', tag: '3', page: '-1' }), { q: 'vue', tag: 3, category: undefined, page: 1 })
  assert.deepEqual(articleQuery({ q: 'vue', tag: 3, category: undefined, page: 2 }), { q: 'vue', tag: '3', page: '2' })
  assert.equal(parseArticleQuery({ page: ['2', '3'], tag: '9007199254740992' }).page, 1)
})
test('list return accepts only local homepage query locations', () => {
  assert.equal(safeListReturn('/?q=vue&page=2#articles'), '/?q=vue&page=2#articles')
  for (const value of ['//evil.test', 'https://evil.test', '/admin', '/\\evil.test', '/articles/2']) assert.equal(safeListReturn(value), '/')
})
test('SEO updates existing DOM nodes and clears article metadata on navigation', () => {
  const dom = new JSDOM('<head><meta name="description" content="old"><meta property="og:image" content="old"></head>')
  const doc = dom.window.document
  setPageSeo({ title: '文章', description: '摘要', path: '/articles/2', image: '/cover.png', type: 'article' }, doc)
  assert.equal(doc.title, '文章 | SudoThink')
  assert.equal(doc.querySelector('link[rel=canonical]')?.getAttribute('href'), 'https://www.feiwenchao.com/articles/2')
  assert.equal(doc.querySelector('meta[property="og:image"]')?.getAttribute('content'), 'https://www.feiwenchao.com/cover.png')
  setPageSeo(routeSeo('/login', true), doc)
  assert.equal(doc.querySelector('meta[name=robots]')?.getAttribute('content'), 'noindex, nofollow')
  assert.equal(doc.querySelector('meta[property="og:image"]'), null)
  assert.equal(doc.querySelectorAll('meta[name=description]').length, 1)
  dom.window.close()
})

test('list back navigation uses history only for the matching safe homepage', () => {
  const target = '/?q=vue&page=2#articles'
  assert.equal(canReturnToListHistory('/?page=2&q=vue#articles', target), true)
  assert.equal(canReturnToListHistory('/?q=vue&page=2', '/?q=vue&page=2'), true)
  for (const previous of ['/about', '/articles/1', '/?q=other', '/', null, undefined, '//evil.test/', '/\\evil.test', 'https://www.feiwenchao.com/']) {
    assert.equal(canReturnToListHistory(previous, target), false)
  }
  assert.equal(canReturnToListHistory('/about', '/'), false)
  assert.equal(canReturnToListHistory('//evil.test', '/'), false)
  assert.equal(canReturnToListHistory(undefined, safeListReturn('https://evil.test')), false)
  assert.equal(canReturnToListHistory('/', safeListReturn('https://evil.test')), true)
})
