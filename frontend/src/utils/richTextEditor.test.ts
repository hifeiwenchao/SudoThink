import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flush } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
const dom = new JSDOM('<html><body></body></html>', { pretendToBeVisual: true })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, DOMParser: dom.window.DOMParser, Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement, Node: dom.window.Node, getComputedStyle: dom.window.getComputedStyle, requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame })
const { createApp, h, reactive, nextTick } = await import('vue')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.rich-editor-test-', import.meta.url)))
after(() => { rmSync(folder, { recursive: true, force: true }); dom.window.close() })
const { descriptor } = parse(readFileSync(new URL('../components/RichTextEditor.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'rich-editor-test' })
const source = script.content.replace(/(['"])@\/utils\/([^'"]+)\1/g, (_, _quote, name) => JSON.stringify(new URL(`./${name}.ts`, import.meta.url).href)).replace(/import MediaUpload from [^\n]+/, 'const MediaUpload = {}').replace(/import '@\/styles\/article.css'/, '')
writeFileSync(`${folder}/component.mjs`, ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText)
const Component = (await import(pathToFileURL(`${folder}/component.mjs`).href)).default
// Exercise production setup/watchers with real Tiptap, without unrelated dialog UI.
Component.render = () => null
async function settle() { await flush(); await nextTick(); await flush() }
test('v-model echoes preserve table selection and media while changed external content still loads', async () => {
  const state = reactive({ value: '<p>前言</p><img src="/safe.png" width="640" height="480"><table><thead><tr><th>表头</th></tr></thead><tbody><tr><td>内容</td></tr></tbody></table>' })
  const host = document.createElement('div'); document.body.append(host)
  let instance: any
  const app = createApp({ render: () => h(Component, { ref: (value: any) => { instance = value }, modelValue: state.value, 'onUpdate:modelValue': (value: string) => { state.value = value } }) })
  app.mount(host); await settle()
  try {
    const editor = instance.$.setupState.editor
    assert.match(state.value, /<thead>/, 'loading normalized table nodes must not rewrite the parent model')
    let position = 0
    editor.state.doc.descendants((node: any, offset: number) => { if (!position && node.type.name === 'tableCell') position = offset + 2 })
    editor.commands.setTextSelection(position)
    editor.commands.insertContent('新增')
    const editedDocument = editor.state.doc, selection = editor.state.selection.toJSON()
    await settle()
    assert.equal(editor.state.doc, editedDocument, 'echo must not replace the editor document')
    assert.deepEqual(editor.state.selection.toJSON(), selection)
    assert.equal(editor.isActive('table'), true)
    editor.commands.addRowAfter()
    const rowSelection = editor.state.selection.toJSON()
    await settle()
    assert.equal(editor.isActive('table'), true)
    assert.deepEqual(editor.state.selection.toJSON(), rowSelection)
    assert.equal(new DOMParser().parseFromString(editor.getHTML(), 'text/html').querySelectorAll('tr').length, 3)
    assert.match(editor.getHTML(), /width="640"/)
    assert.match(state.value, /新增/)
    state.value = '<p>另一篇文章</p>'; await settle()
    assert.equal(editor.getText(), '另一篇文章')
  } finally { app.unmount(); host.remove() }
})
