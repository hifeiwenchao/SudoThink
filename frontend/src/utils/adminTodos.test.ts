import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises, setTimeout as waitForValidation } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { Todo, TodoInput, TodoPage } from '../api/todos'
import type { TodoForm } from './todos'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://admin.example.com/', pretendToBeVisual: true })
Object.assign(globalThis, {
  window: dom.window, document: dom.window.document, Document: dom.window.Document,
  Element: dom.window.Element, HTMLElement: dom.window.HTMLElement, SVGElement: dom.window.SVGElement,
  HTMLInputElement: dom.window.HTMLInputElement, HTMLTextAreaElement: dom.window.HTMLTextAreaElement,
  HTMLButtonElement: dom.window.HTMLButtonElement, HTMLSelectElement: dom.window.HTMLSelectElement,
  Node: dom.window.Node, MutationObserver: dom.window.MutationObserver,
  Event: dom.window.Event, CustomEvent: dom.window.CustomEvent, FocusEvent: dom.window.FocusEvent,
  KeyboardEvent: dom.window.KeyboardEvent, MouseEvent: dom.window.MouseEvent, getComputedStyle: dom.window.getComputedStyle,
  requestAnimationFrame: dom.window.requestAnimationFrame, cancelAnimationFrame: dom.window.cancelAnimationFrame,
  ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
})
const { createApp, nextTick } = await import('vue')
const { default: ElementPlus, ElMessage } = await import('element-plus')
const folder = mkdtempSync(fileURLToPath(new URL('../../node_modules/.admin-todos-test-', import.meta.url)))
after(() => { ElMessage.closeAll(); rmSync(folder, { recursive: true, force: true }); dom.window.close() })
function compile(source: string) {
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
}
const apiTarget = `${folder}/api.mjs`
writeFileSync(apiTarget, `export const todosApi = new Proxy({}, { get: (_, name) => (...args) => globalThis.__todoAdmin[name](...args) });`)
const { descriptor } = parse(readFileSync(new URL('../views/AdminTodos.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'admin-todos-test' })
const source = script.content
  .replace(/(['"])@\/api\/todos\1/g, JSON.stringify(pathToFileURL(apiTarget).href))
  .replace(/(['"])@\/utils\/todos\1/g, JSON.stringify(new URL('./todos.ts', import.meta.url).href))
const target = `${folder}/AdminTodos.mjs`
writeFileSync(target, compile(source))
const template = compileTemplate({ source: descriptor.template!.content, filename: 'AdminTodos.vue', id: 'admin-todos-test', compilerOptions: { bindingMetadata: script.bindings, expressionPlugins: ['typescript'] } })
writeFileSync(`${folder}/template.mjs`, compile(template.code))
const AdminTodos = (await import(pathToFileURL(target).href)).default
AdminTodos.render = (await import(pathToFileURL(`${folder}/template.mjs`).href)).render

const todo = (): Todo => ({
  id: 1, title: '证书续期', content: '检查证书', due_at: '2026-11-18T01:30:00Z',
  is_completed: false, reminder_enabled: true, reminder_status: 'pending', reminder_sent_at: null,
  reminder_email: 'owner@example.com',
  reminder_repeat: 'once', reminder_timezone: 'Asia/Shanghai', reminder_next_run_at: '2026-11-18T01:30:00Z',
  reminder_attempts: 0, reminder_error: '', created_at: '2026-11-17T00:00:00Z', updated_at: '2026-11-17T00:00:00Z',
})
type State = {
  form: TodoForm; list: Todo[]; dialogVisible: boolean; saveError: string; loading: boolean; canManage: boolean
  openCreate(): void; openEdit(item: Todo): void; load(): Promise<void>; save(): Promise<void>; toggleCompletion(item: Todo): Promise<void>
}
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
async function mount(options: { list?: () => Promise<TodoPage>; create?: (input: TodoInput) => Promise<Todo> } = {}) {
  let items = [todo()]
  const saves: TodoInput[] = []
  const completions: { id: number; completed: boolean }[] = []
  const updates: { id: number; input: TodoInput }[] = []
  Object.assign(globalThis, { __todoAdmin: {
    async list() { return options.list?.() ?? { items, total: items.length, page: 1, size: 10, email_configured: true } },
    async create(input: TodoInput) {
      saves.push(input)
      const created = options.create ? await options.create(input) : { ...todo(), ...input, id: 2 }
      items = [...items, created]
      return created
    },
    async update(id: number, input: TodoInput) {
      updates.push({ id, input })
      items = items.map(item => item.id === id ? { ...item, ...input } : item)
      return items.find(item => item.id === id)
    },
    async complete(id: number, completed: boolean) {
      completions.push({ id, completed })
      items = items.map(item => item.id === id ? { ...item, is_completed: completed, reminder_enabled: false, reminder_status: 'disabled' as const } : item)
      return items.find(item => item.id === id)
    },
  } })
  const container = document.createElement('div')
  document.body.append(container)
  const app = createApp(AdminTodos)
  app.use(ElementPlus)
  const instance = app.mount(container) as unknown as { $: { setupState: State } }
  await settle()
  return { container, state: instance.$.setupState, saves, updates, completions, unmount: () => { app.unmount(); container.remove() } }
}

test('a failed list load disables edits until a successful retry', async t => {
  let failing = true
  const view = await mount({ list: async () => {
    if (failing) throw new Error('offline')
    return { items: [todo()], total: 1, page: 1, size: 10, email_configured: true }
  } })
  t.after(view.unmount)
  assert.equal(view.state.canManage, false)
  view.state.openCreate()
  assert.equal(view.state.dialogVisible, false)
  assert.ok(view.container.textContent?.includes('待办事项加载失败'))
  failing = false
  await view.state.load()
  assert.equal(view.state.canManage, true)
  assert.equal(view.state.list[0]?.title, '证书续期')
})

test('failed saves preserve the editor and concurrent saves do not create duplicate reminders', async t => {
  let failing = true
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const view = await mount({ create: async input => {
    await gate
    if (failing) throw new Error('offline')
    return { ...todo(), ...input, id: 2 }
  } })
  t.after(view.unmount)
  view.state.openCreate()
  Object.assign(view.state.form, { title: ' 新提醒 ', content: '内容', due_at: new Date('2026-11-18T09:30:00+08:00'), reminder_enabled: true, reminder_email: ' friend@example.com ' })
  const first = view.state.save()
  await view.state.save()
  assert.equal(view.saves.length, 1)
  release()
  await first
  assert.equal(view.state.dialogVisible, true)
  assert.equal(view.state.form.title, ' 新提醒 ')
  assert.match(view.state.saveError, /已保留/)
  failing = false
  await view.state.save()
  assert.equal(view.state.dialogVisible, false)
  assert.deepEqual(view.saves.at(-1), { title: '新提醒', content: '内容', due_at: '2026-11-18T01:30:00.000Z', reminder_enabled: true, reminder_email: 'friend@example.com', reminder_repeat: 'once', reminder_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
})

test('completion updates the list and reopening keeps email reminders off', async t => {
  const view = await mount()
  t.after(view.unmount)
  await view.state.toggleCompletion(view.state.list[0]!)
  assert.equal(view.state.list[0]?.is_completed, true)
  assert.equal(view.state.list[0]?.reminder_enabled, false)
  assert.equal(view.state.list[0]?.reminder_email, 'owner@example.com')
  await view.state.toggleCompletion(view.state.list[0]!)
  assert.deepEqual(view.completions, [{ id: 1, completed: true }, { id: 1, completed: false }])
  assert.equal(view.state.list[0]?.is_completed, false)
  assert.equal(view.state.list[0]?.reminder_enabled, false)
  assert.equal(view.state.list[0]?.reminder_email, 'owner@example.com')
})

test('editing uses the recipient stored on the todo and saving preserves a changed address', async t => {
  const view = await mount()
  t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('owner@example.com'))
  view.state.openCreate()
  assert.equal(view.state.form.reminder_email, '')
  view.state.openEdit(view.state.list[0]!)
  assert.equal(view.state.form.reminder_email, 'owner@example.com')
  view.state.form.reminder_email = ' second@example.com '
  await view.state.save()
  assert.equal(view.updates[0]?.id, 1)
  assert.equal(view.updates[0]?.input.reminder_email, 'second@example.com')
  assert.equal(view.state.list[0]?.reminder_email, 'second@example.com')
})

test('enabling email without a recipient keeps the editor open and does not submit', async t => {
  const view = await mount()
  t.after(view.unmount)
  view.state.openCreate()
  Object.assign(view.state.form, { title: '提醒', due_at: new Date('2026-11-18T01:30:00Z'), reminder_enabled: true })
  await view.state.save()
  assert.equal(view.saves.length, 0)
  assert.equal(view.state.dialogVisible, true)
})

test('turning reminders off keeps an invalid recipient visible so its validation can be corrected', async t => {
  const view = await mount()
  t.after(view.unmount)
  view.state.openCreate()
  Object.assign(view.state.form, { title: '普通待办', reminder_enabled: true, reminder_email: 'invalid-address' })
  await settle()
  view.state.form.reminder_enabled = false
  await view.state.save()
  await settle()
  assert.equal(view.saves.length, 0)
  const input = document.body.querySelector<HTMLInputElement>('input[aria-label="提醒收件邮箱"]')
  assert.ok(input, '邮箱输入框关闭提醒后仍应可见')
  assert.equal(input.disabled, false)
  assert.equal(input.value, 'invalid-address')
  const field = input.closest('.el-form-item')
  // Element Plus debounces its visible validation state by 100 ms.
  await waitForValidation(120)
  await settle()
  assert.ok(field?.querySelector('.el-form-item__error')?.textContent?.includes('有效'))
  input.value = ''
  input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  await settle()
  await view.state.save()
  assert.equal(view.saves.length, 1)
  assert.equal(view.saves[0]?.reminder_enabled, false)
  assert.equal(view.saves[0]?.reminder_email, '')
  assert.equal(view.state.dialogVisible, false)
})

test('recurring reminders show their next occurrence instead of an overdue original date', async t => {
  const recurring = {
    ...todo(), due_at: '2020-01-31T01:30:00Z', reminder_repeat: 'monthly',
    reminder_timezone: 'Asia/Shanghai', reminder_next_run_at: '2099-02-28T01:30:00Z',
    reminder_sent_at: '2026-10-31T01:30:00Z',
  } as Todo
  const view = await mount({ list: async () => ({ items: [recurring], total: 1, page: 1, size: 10, email_configured: true }) })
  t.after(view.unmount)
  assert.ok(view.container.textContent?.includes('每月 31 日 09:30'))
  assert.ok(view.container.textContent?.includes('下次'))
  assert.ok(view.container.textContent?.includes('最近发送'))
  assert.equal(view.container.querySelector('.overdue-label'), null)
  view.state.openEdit(recurring)
  await settle()
  assert.ok(document.body.querySelector('input[aria-label="提醒重复频率"]'))
  await view.state.save()
  assert.equal(view.updates[0]?.input.reminder_repeat, 'monthly')
  assert.equal(view.updates[0]?.input.reminder_timezone, 'Asia/Shanghai')
})

test('changing a recurring schedule uses the device time zone and a new todo starts with a single reminder', async t => {
  const view = await mount()
  t.after(view.unmount)
  view.state.openCreate()
  assert.equal(view.state.form.reminder_repeat, 'once')
  assert.equal(view.state.form.reminder_timezone, Intl.DateTimeFormat().resolvedOptions().timeZone)
  const item = { ...todo(), reminder_repeat: 'yearly', reminder_timezone: 'America/New_York' } as Todo
  view.state.openEdit(item)
  view.state.form.content = '只修改说明'
  await view.state.save()
  assert.equal(view.updates[0]?.input.reminder_timezone, 'America/New_York')
  view.state.openEdit(item)
  view.state.form.due_at = new Date('2027-02-28T10:00:00Z')
  await view.state.save()
  assert.equal(view.updates[1]?.input.reminder_timezone, Intl.DateTimeFormat().resolvedOptions().timeZone)
})
