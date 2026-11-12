import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { JSDOM } from 'jsdom'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { Video } from './editorVideo'

const { window } = new JSDOM('')
Object.assign(globalThis, { window, document: window.document, DOMParser: window.DOMParser, Element: window.Element, HTMLElement: window.HTMLElement, Node: window.Node, getComputedStyle: window.getComputedStyle })

describe('editor video', () => {
  it('round-trips video-only HTML through a real Tiptap editor without losing the media node', () => {
    const editor = new Editor({
      element: document.createElement('div'),
      extensions: [StarterKit, Video],
      content: '<video src="https://cdn.example.com/video.mp4" controls preload="metadata" playsinline></video>',
    })
    try {
      assert.equal(editor.isEmpty, false)
      assert.equal(editor.getJSON().content?.[0]?.type, 'video')
      assert.equal(editor.getJSON().content?.[0]?.attrs?.src, 'https://cdn.example.com/video.mp4')
      const html = editor.getHTML()
      editor.commands.setContent(html)
      const video = new DOMParser().parseFromString(editor.getHTML(), 'text/html').querySelector('video')!
      assert.ok(video)
      assert.equal(video.getAttribute('src'), 'https://cdn.example.com/video.mp4')
      assert.equal(video.controls, true)
      assert.equal(video.preload, 'metadata')
      assert.equal(video.hasAttribute('playsinline'), true)
      assert.equal(editor.getText().trim(), '')
    } finally { editor.destroy() }
  })

  it('inserts a selectable block video node and restores it after undo', () => {
    const editor = new Editor({ element: document.createElement('div'), extensions: [StarterKit, Video], content: '<p>前言</p>' })
    try {
      editor.commands.insertContentAt(editor.state.doc.content.size, { type: 'video', attrs: { src: '/media/clip.webm' } })
      assert.equal(editor.getJSON().content?.find((node) => node.type === 'video')?.attrs?.src, '/media/clip.webm')
      assert.equal(editor.schema.nodes.video?.isBlock, true)
      assert.equal(editor.schema.nodes.video?.spec.atom, true)
      editor.commands.undo()
      assert.equal(new DOMParser().parseFromString(editor.getHTML(), 'text/html').querySelector('video'), null)
      editor.commands.redo()
      assert.equal(new DOMParser().parseFromString(editor.getHTML(), 'text/html').querySelector('video')?.getAttribute('src'), '/media/clip.webm')
    } finally { editor.destroy() }
  })
})
