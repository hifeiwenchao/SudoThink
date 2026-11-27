import assert from 'node:assert/strict'
import { test } from 'node:test'
import { JSDOM } from 'jsdom'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { ArticleImage, imageDimensions } from './editorImage'
const { window } = new JSDOM('')
Object.assign(globalThis, { window, document: window.document, DOMParser: window.DOMParser, Element: window.Element, HTMLElement: window.HTMLElement, Node: window.Node, getComputedStyle: window.getComputedStyle })
test('image extension round trips safe intrinsic dimensions and discards invalid sizes', () => {
  const editor = new Editor({ element: document.createElement('div'), extensions: [StarterKit, ArticleImage],
    content: '<img src="https://example.com/a.png" width="1200" height="800"><img src="/x.png" width="50000" height="-1">' })
  try {
    const images = new DOMParser().parseFromString(editor.getHTML(), 'text/html').querySelectorAll('img')
    assert.equal(images[0].getAttribute('width'), '1200'); assert.equal(images[0].getAttribute('height'), '800')
    assert.equal(images[1].hasAttribute('width'), false); assert.equal(images[1].hasAttribute('height'), false)
  } finally { editor.destroy() }
})
test('image dimension reads are bounded and failure does not block inserting a valid image', async () => {
  let closed = false
  Object.assign(globalThis, { createImageBitmap: async () => ({ width: 640, height: 480, close() { closed = true } }) })
  assert.deepEqual(await imageDimensions(new Blob(['image'])), { width: 640, height: 480 }); assert.equal(closed, true)
  Object.assign(globalThis, { createImageBitmap: async () => { throw new Error('unsupported') } })
  assert.deepEqual(await imageDimensions(new Blob(['image'])), {})
  delete (globalThis as any).createImageBitmap
})
