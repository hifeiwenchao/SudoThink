import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { test, after } from 'node:test'
import { setImmediate as flushPromises, setTimeout as waitForValidation } from 'node:timers/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import ts from 'typescript'
import type { Todo, TodoInput, TodoPage, TodoCronPreview, TodoSkipPeriod, TodoSkipPreview } from '../api/todos'
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
  .replace(/(['"])@\/utils\/todoCron\1/g, JSON.stringify(new URL('./todoCron.ts', import.meta.url).href))
  .replace(/import TodoHistory from ['"]@\/components\/TodoHistory.vue['"]/, 'const TodoHistory = { template: "<div />", props: ["todo", "modelValue"] }')
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
  reminder_cron: '',
  reminder_attempts: 0, reminder_error: '', created_at: '2026-11-17T00:00:00Z', updated_at: '2026-11-17T00:00:00Z',
})
type State = {
  form: TodoForm; list: Todo[]; dialogVisible: boolean; saveError: string; loading: boolean; canManage: boolean
  openCreate(): void; openEdit(item: Todo): void; load(): Promise<void>; save(): Promise<void>; toggleCompletion(item: Todo): Promise<void>
  configureCron(): void; fetchCronPreview(): Promise<boolean>; cronPreview: TodoCronPreview | null; previewError: string
  builder: { preset: string; time: string; weekdays: number[]; day: number; month: number; interval: number }
  applyCronBuilder(): void
}
async function settle() { await flushPromises(); await nextTick(); await flushPromises(); await nextTick() }
async function mount(options: {
  items?: Todo[]; list?: () => Promise<TodoPage>; create?: (input: TodoInput) => Promise<Todo>
  preview?: (input: { reminder_cron: string; reminder_timezone: string }) => Promise<TodoCronPreview>
  previewSkipPeriod?: (id: number, period: TodoSkipPeriod, signal?: AbortSignal) => Promise<TodoSkipPreview>
  skipPeriod?: (id: number, period: TodoSkipPeriod, preview: TodoSkipPreview) => Promise<Todo>
} = {}) {
  let items = options.items ?? [todo()]
  const saves: TodoInput[] = []
  const completions: { id: number; completed: boolean }[] = []
  const updates: { id: number; input: TodoInput }[] = []
  const skipPreviews: { id: number; period: TodoSkipPeriod; signal?: AbortSignal }[] = []
  const skips: { id: number; period: TodoSkipPeriod; preview: TodoSkipPreview }[] = []
  const requests = { list: 0 }
  Object.assign(globalThis, { __todoAdmin: {
    async preview(input: { reminder_cron: string; reminder_timezone: string }) {
      return options.preview?.(input) ?? { expression: input.reminder_cron, timezone: input.reminder_timezone,
        times: ['2099-01-01T01:00:00Z', '2099-01-02T01:00:00Z', '2099-01-03T01:00:00Z', '2099-01-04T01:00:00Z', '2099-01-05T01:00:00Z'] }
    },
    async list() { requests.list++; return options.list?.() ?? { items, total: items.length, page: 1, size: 10, email_configured: true } },
    async previewSkipPeriod(id: number, period: TodoSkipPeriod, signal?: AbortSignal) {
      skipPreviews.push({ id, period, signal })
      return options.previewSkipPeriod?.(id, period, signal) ?? skipPreview(period)
    },
    async skipPeriod(id: number, period: TodoSkipPeriod, preview: TodoSkipPreview) {
      skips.push({ id, period, preview })
      const updated = options.skipPeriod ? await options.skipPeriod(id, period, preview) : { ...items.find(item => item.id === id)!, reminder_next_run_at: '2099-12-01T01:00:00Z' }
      items = items.map(item => item.id === id ? updated : item)
      return updated
    },
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
  return { container, state: instance.$.setupState, saves, updates, completions, skipPreviews, skips, requests, unmount: () => { app.unmount(); container.remove() } }
}

const monthlyTodo = (): Todo => ({ ...todo(), reminder_repeat: 'cron', reminder_cron: '0 9 1,2,3 * *' })
const skipPreview = (period: TodoSkipPeriod, next = '2099-12-01T01:00:00Z'): TodoSkipPreview => ({
  period, timezone: 'Asia/Shanghai', period_ends_at: '2099-12-01T00:00:00+08:00', next_run_at: next, reminder_revision: 4,
})
function button(root: ParentNode, text: string) {
  const found = [...root.querySelectorAll<HTMLButtonElement>('button')].find(item => item.textContent?.trim() === text)
  assert.ok(found, `应显示“${text}”按钮`)
  return found
}
function skipDialog() {
  const dialog = document.body.querySelector<HTMLElement>('.skip-period-dialog')
  assert.ok(dialog, '应打开本周期不再提醒对话框')
  return dialog
}
async function chooseSkipPeriod(period: TodoSkipPeriod) {
  const input = skipDialog().querySelector<HTMLInputElement>(`input[type="radio"][value="${period}"]`)
  assert.ok(input, `应提供 ${period} 周期选项`)
  input.click()
  await settle()
}

test('only active recurring todos offer skip and the month-first-three-days rule defaults to this month', async t => {
  const view = await mount({ items: [monthlyTodo(), { ...todo(), id: 2 }, { ...monthlyTodo(), id: 3, reminder_enabled: false }, { ...monthlyTodo(), id: 4, is_completed: true }] })
  t.after(view.unmount)
  const buttons = [...view.container.querySelectorAll('button')].filter(item => item.textContent?.trim() === '不再提醒')
  assert.equal(buttons.length, 1)
  buttons[0]!.click()
  await settle()
  const dialog = skipDialog()
  assert.equal(dialog.querySelector<HTMLInputElement>('input[value="month"]')?.checked, true)
  assert.equal(view.skipPreviews[0]?.period, 'month')
  assert.match(dialog.textContent ?? '', /0 9 1,2,3 \* \*/)
  assert.match(dialog.textContent ?? '', /Asia\/Shanghai/)
  assert.deepEqual([...dialog.querySelectorAll('time')].map(item => item.dateTime), ['2099-12-01T00:00:00+08:00', '2099-12-01T01:00:00Z'])
  assert.equal(button(dialog, '确认跳过').disabled, false)
})

test('changing skip period aborts and ignores old previews, and closing aborts the current preview', async t => {
  const pending: ((value: TodoSkipPreview) => void)[] = []
  const view = await mount({ items: [monthlyTodo()], previewSkipPeriod: () => new Promise(resolve => pending.push(resolve)) })
  t.after(view.unmount)
  button(view.container, '不再提醒').click()
  await settle()
  assert.equal(button(skipDialog(), '确认跳过').disabled, true)
  await chooseSkipPeriod('day')
  assert.equal(view.skipPreviews[0]?.signal?.aborted, true)
  assert.equal(button(skipDialog(), '确认跳过').disabled, true)
  pending[1]!(skipPreview('day', '2099-11-24T01:00:00Z'))
  await settle()
  assert.equal(button(skipDialog(), '确认跳过').disabled, false)
  pending[0]!(skipPreview('month'))
  await settle()
  assert.equal(skipDialog().querySelectorAll('time')[1]?.dateTime, '2099-11-24T01:00:00Z')
  await chooseSkipPeriod('week')
  button(skipDialog(), '取消').click()
  await settle()
  assert.equal(view.skipPreviews[2]?.signal?.aborted, true)
  pending[2]!(skipPreview('week'))
  await settle()
  assert.equal(view.skips.length, 0)
})

test('failed skip previews keep the selection and retry before enabling confirmation', async t => {
  let failing = true
  const view = await mount({ items: [monthlyTodo()], previewSkipPeriod: async (_id, period) => {
    if (failing) throw new Error('offline')
    return skipPreview(period)
  } })
  t.after(view.unmount)
  button(view.container, '不再提醒').click()
  await settle()
  await chooseSkipPeriod('year')
  assert.equal(button(skipDialog(), '确认跳过').disabled, true)
  assert.ok(skipDialog().querySelector('[role="alert"]'))
  assert.equal(skipDialog().querySelector<HTMLInputElement>('input[value="year"]')?.checked, true)
  failing = false
  button(skipDialog(), '重新预览').click()
  await settle()
  assert.equal(button(skipDialog(), '确认跳过').disabled, false)
  assert.equal(view.skips.length, 0)
})

test('an incomplete preview snapshot cannot enable skip confirmation', async t => {
  const view = await mount({ items: [monthlyTodo()], previewSkipPeriod: async (_id, period) => {
    const result = { ...skipPreview(period) }
    delete (result as Partial<TodoSkipPreview>).reminder_revision
    return result
  } })
  t.after(view.unmount)
  button(view.container, '不再提醒').click()
  await settle()
  assert.equal(button(skipDialog(), '确认跳过').disabled, true)
  assert.ok(skipDialog().querySelector('[role="alert"]'))
  assert.equal(view.skips.length, 0)
})

test('failed skips retain the dialog and success refreshes while preserving the reminder switch', async t => {
  let failing = true
  let release!: () => void
  let releasePreview!: () => void
  let previewCalls = 0
  const gate = new Promise<void>(resolve => { release = resolve })
  const previewGate = new Promise<void>(resolve => { releasePreview = resolve })
  const view = await mount({ items: [monthlyTodo()], previewSkipPeriod: async (_id, period) => {
    previewCalls++
    if (previewCalls === 3) {
      await previewGate
      return { ...skipPreview(period), period_ends_at: '2100-01-01T00:00:00+08:00', next_run_at: '2100-01-01T01:00:00Z', reminder_revision: 5 }
    }
    return skipPreview(period)
  }, skipPeriod: async () => {
    await gate
    if (failing) throw new Error('offline')
    return { ...monthlyTodo(), reminder_next_run_at: '2099-12-01T01:00:00Z' }
  } })
  t.after(view.unmount)
  button(view.container, '不再提醒').click()
  await settle()
  await chooseSkipPeriod('year')
  button(skipDialog(), '确认跳过').click()
  await settle()
  assert.equal(button(skipDialog(), '取消').disabled, true)
  assert.equal(skipDialog().querySelector<HTMLInputElement>('input[value="month"]')?.disabled, true)
  assert.equal(view.skips.length, 1)
  assert.equal(view.state.canManage, false)
  release()
  await settle()
  assert.ok(skipDialog().querySelector('[role="alert"]'))
  assert.equal(skipDialog().querySelector<HTMLInputElement>('input[value="year"]')?.checked, true)
  assert.equal(view.requests.list, 1)
  assert.equal(button(skipDialog(), '重试跳过').disabled, true)
  assert.equal(view.skipPreviews.length, 3, '失败后应重新预览，旧预览不能直接再次提交')
  releasePreview()
  await settle()
  assert.equal(button(skipDialog(), '重试跳过').disabled, false)
  failing = false
  button(skipDialog(), '重试跳过').click()
  await settle()
  assert.deepEqual(view.skips, [
    { id: 1, period: 'year', preview: { period: 'year', timezone: 'Asia/Shanghai', period_ends_at: '2099-12-01T00:00:00+08:00', next_run_at: '2099-12-01T01:00:00Z', reminder_revision: 4 } },
    { id: 1, period: 'year', preview: { period: 'year', timezone: 'Asia/Shanghai', period_ends_at: '2100-01-01T00:00:00+08:00', next_run_at: '2100-01-01T01:00:00Z', reminder_revision: 5 } },
  ])
  assert.equal(view.requests.list, 2)
  assert.equal(view.state.list[0]?.reminder_next_run_at, '2099-12-01T01:00:00Z')
  assert.equal(view.state.list[0]?.reminder_enabled, true)
  assert.equal(view.state.list[0]?.is_completed, false)
})

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
  Object.assign(view.state.form, { title: ' 新提醒 ', content: '内容', reminder_enabled: true, reminder_email: ' friend@example.com ' })
  const first = view.state.save()
  await view.state.save()
  await settle()
  assert.equal(view.saves.length, 1)
  release()
  await first
  assert.equal(view.state.dialogVisible, true)
  assert.equal(view.state.form.title, ' 新提醒 ')
  assert.match(view.state.saveError, /已保留/)
  failing = false
  await view.state.save()
  assert.equal(view.state.dialogVisible, false)
  assert.deepEqual(view.saves.at(-1), { title: '新提醒', content: '内容', due_at: null, reminder_enabled: true, reminder_email: 'friend@example.com', reminder_repeat: 'cron', reminder_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, reminder_cron: '0 9 * * *' })
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
  assert.equal(document.body.querySelector('input[aria-label="提醒重复频率"]'), null)
  assert.ok(document.body.textContent?.includes('已保留原提醒计划'))
  await view.state.save()
  assert.equal(view.updates[0]?.input.reminder_repeat, 'monthly')
  assert.equal(view.updates[0]?.input.reminder_timezone, 'Asia/Shanghai')
})

test('cron reminders use an explicit saved time zone and a new todo starts with crontab', async t => {
  const view = await mount()
  t.after(view.unmount)
  view.state.openCreate()
  assert.equal(view.state.form.reminder_repeat, 'cron')
  assert.equal(view.state.form.reminder_timezone, Intl.DateTimeFormat().resolvedOptions().timeZone)
  const item = { ...todo(), reminder_repeat: 'yearly', reminder_timezone: 'America/New_York' } as Todo
  view.state.openEdit(item)
  view.state.form.content = '只修改说明'
  await view.state.save()
  assert.equal(view.updates[0]?.input.reminder_timezone, 'America/New_York')
  view.state.openEdit(item)
  view.state.configureCron()
  view.state.form.reminder_timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  await view.state.save()
  assert.equal(view.updates[1]?.input.reminder_timezone, Intl.DateTimeFormat().resolvedOptions().timeZone)
})

test('new todos expose a friendly crontab schedule and omit the previous date and repeat controls', async t => {
  const view = await mount()
  t.after(view.unmount)
  view.state.openCreate()
  assert.equal(view.state.form.reminder_repeat, 'cron')
  view.state.form.reminder_enabled = true
  Object.assign(view.state.builder, { preset: 'weekly', time: '08:45', weekdays: [5, 1] })
  view.state.applyCronBuilder()
  assert.equal(view.state.form.reminder_cron, '45 8 * * 1,5')
  await view.state.fetchCronPreview()
  await settle()
  assert.equal(document.body.querySelector('input[aria-label="待办到期时间"]'), null)
  assert.equal(document.body.querySelector('input[aria-label="提醒重复频率"]'), null)
  assert.ok(document.body.querySelector('input[aria-label="Crontab 表达式"]'))
  assert.equal(document.body.querySelectorAll('.cron-preview-list li').length, 5)
})

test('legacy reminders retain their original plan until an explicit conversion to crontab', async t => {
  const view = await mount()
  t.after(view.unmount)
  const item = { ...todo(), reminder_status: 'sent', reminder_sent_at: '2026-11-18T01:30:00Z' } as Todo
  view.state.openEdit(item)
  view.state.form.title = '只改标题'
  await view.state.save()
  assert.equal(view.updates[0]?.input.reminder_repeat, 'once')
  assert.equal(view.updates[0]?.input.due_at, item.due_at!.replace('Z', '.000Z'))
  view.state.openEdit(item)
  view.state.configureCron()
  await view.state.save()
  assert.equal(view.updates[1]?.input.reminder_repeat, 'cron')
  assert.equal(view.updates[1]?.input.due_at, null)
  assert.equal(view.updates[1]?.input.reminder_cron, '0 9 * * *')
})

test('failed server schedule validation retains the form and prevents saving a cron reminder', async t => {
  const view = await mount({ preview: async () => { throw new Error('invalid schedule') } })
  t.after(view.unmount)
  view.state.openCreate()
  Object.assign(view.state.form, { title: '提醒', reminder_enabled: true, reminder_email: 'owner@example.com' })
  await view.state.save()
  assert.equal(view.saves.length, 0)
  assert.equal(view.state.dialogVisible, true)
  assert.ok(view.state.previewError)
})

test('a stale preview result cannot replace the result for a newer expression', async t => {
  const pending: ((result: TodoCronPreview) => void)[] = []
  const view = await mount({ preview: () => new Promise(resolve => pending.push(resolve)) })
  t.after(view.unmount)
  view.state.openCreate()
  view.state.form.reminder_enabled = true
  view.state.form.reminder_cron = '0 8 * * *'
  const first = view.state.fetchCronPreview()
  view.state.form.reminder_cron = '0 10 * * *'
  const second = view.state.fetchCronPreview()
  pending[1]!({ expression: '0 10 * * *', timezone: view.state.form.reminder_timezone, times: ['2099-01-01T02:00:00Z', '2099-01-02T02:00:00Z', '2099-01-03T02:00:00Z', '2099-01-04T02:00:00Z', '2099-01-05T02:00:00Z'] })
  await second
  pending[0]!({ expression: '0 8 * * *', timezone: view.state.form.reminder_timezone, times: ['2099-01-01T00:00:00Z', '2099-01-02T00:00:00Z', '2099-01-03T00:00:00Z', '2099-01-04T00:00:00Z', '2099-01-05T00:00:00Z'] })
  await first
  assert.equal(view.state.cronPreview?.expression, '0 10 * * *')
})
