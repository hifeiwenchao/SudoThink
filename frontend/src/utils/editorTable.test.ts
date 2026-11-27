import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { JSDOM } from 'jsdom'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { articleTableExtensions } from './editorTable'

const { window } = new JSDOM('')
Object.assign(globalThis, { window, document: window.document, DOMParser: window.DOMParser, ClipboardEvent: window.Event, Element: window.Element, HTMLElement: window.HTMLElement, Node: window.Node, getComputedStyle: window.getComputedStyle })
const { sanitizeArticleHtml, toArticleHtml } = await import('./articleContent')
function createEditor() {
  return new Editor({ element: document.createElement('div'), extensions: [StarterKit, ...articleTableExtensions],
    editorProps: { transformPastedHTML: sanitizeArticleHtml }, content: '<p>前言</p>' })
}
function body(editor: Editor) { return new DOMParser().parseFromString(editor.getHTML(), 'text/html').body }

describe('editor tables', () => {
  it('inserts a 3 × 3 table with headers and supports row, column, undo and deletion commands', () => {
    const editor = createEditor()
    try {
      assert.equal(editor.can().deleteTable(), false)
      assert.equal(editor.commands.insertTable({ rows: 3, cols: 3, withHeaderRow: true }), true)
      assert.equal(body(editor).querySelectorAll('tr').length, 3)
      assert.equal(body(editor).querySelectorAll('th').length, 3)
      assert.equal(body(editor).querySelectorAll('td').length, 6)
      assert.equal(editor.isActive('table'), true)
      assert.equal(editor.commands.addRowAfter(), true)
      assert.equal(body(editor).querySelectorAll('tr').length, 4)
      assert.equal(editor.commands.addColumnAfter(), true)
      assert.equal(body(editor).querySelector('tr')!.children.length, 4)
      assert.equal(editor.commands.deleteColumn(), true)
      assert.equal(body(editor).querySelector('tr')!.children.length, 3)
      assert.equal(editor.commands.deleteRow(), true)
      assert.equal(body(editor).querySelectorAll('tr').length, 3)
      assert.equal(editor.commands.deleteTable(), true)
      assert.equal(body(editor).querySelector('table'), null)
      assert.equal(editor.commands.undo(), true)
      assert.ok(body(editor).querySelector('table'))
    } finally { editor.destroy() }
  })

  it('pastes an HTML table through the editor clipboard pipeline and round trips merged cells', () => {
    const editor = createEditor()
    try {
      editor.view.pasteHTML('<table style="width:9000px" onclick="alert(1)"><thead><tr><th colspan="2">表头</th></tr></thead><tbody><tr><td rowspan="2"><strong>甲</strong></td><td>乙</td></tr><tr><td>丙<script>alert(1)</script></td></tr></tbody></table>')
      let html = editor.getHTML()
      editor.commands.setContent(toArticleHtml(html))
      html = editor.getHTML()
      assert.equal(body(editor).querySelectorAll('table').length, 1)
      assert.equal(body(editor).querySelector('th')?.getAttribute('colspan'), '2')
      assert.equal(body(editor).querySelector('td')?.getAttribute('rowspan'), '2')
      assert.equal(body(editor).querySelector('strong')?.textContent, '甲')
      assert.equal(body(editor).querySelector('script, [onclick], [style]'), null)
      assert.equal(toArticleHtml(html).includes('丙'), true)
    } finally { editor.destroy() }
  })

  it('bounds table spans even when HTML is loaded directly without the sanitizer', () => {
    const editor = createEditor()
    try {
      editor.commands.setContent('<table><tr><td colspan="999999999" rowspan="-5" colwidth="9999" style="background:red">内容</td></tr></table>')
      const cell = body(editor).querySelector('td')!
      assert.equal(cell.getAttribute('colspan'), null)
      assert.equal(cell.getAttribute('rowspan'), null)
      assert.equal(cell.hasAttribute('colwidth'), false)
      assert.equal(cell.hasAttribute('style'), false)
    } finally { editor.destroy() }
  })
})
