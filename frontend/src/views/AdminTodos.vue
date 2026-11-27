<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { matchedRouteKey, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import TodoHistory from '@/components/TodoHistory.vue'
import { todosApi, type Todo, type TodoFilter, type TodoCronPreview, type TodoSkipPeriod, type TodoSkipPreview } from '@/api/todos'
import { deviceTimezone, prepareTodoInput, type TodoForm, type TodoFormErrors } from '@/utils/todos'
import { buildTodoCron, describeTodoCron, normalizeTodoCron, recommendedTodoSkipPeriod, type TodoCronBuilder } from '@/utils/todoCron'

const list = ref<Todo[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const status = ref<TodoFilter>('all')
const searchText = ref('')
const query = ref('')
const loading = ref(false)
const loaded = ref(false)
const loadError = ref(false)
const operationError = ref('')
const operationId = ref<number | null>(null)
const emailConfigured = ref(false)
const dialogVisible = ref(false)
const historyVisible = ref(false)
const historyTarget = ref<Todo | null>(null)
const editingId = ref<number | null>(null)
const editingCompleted = ref(false)
const saving = ref(false)
const saveError = ref('')
const skipDialogVisible = ref(false)
const skipTarget = ref<Todo | null>(null)
const skipPeriod = ref<TodoSkipPeriod>('day')
const skipPreview = ref<TodoSkipPreview | null>(null)
const skipPreviewLoading = ref(false)
const skipPreviewError = ref('')
const skipSaving = ref(false)
const skipError = ref('')
const skipPeriods: { value: TodoSkipPeriod; label: string }[] = [
  { value: 'day', label: '本日' }, { value: 'week', label: '本周' },
  { value: 'month', label: '本月' }, { value: 'year', label: '本年' },
]
const skipPreviewValid = computed(() => skipDialogVisible.value && !!skipPreview.value && skipPreview.value.period === skipPeriod.value && !skipPreviewLoading.value && !skipPreviewError.value)
const localTimezone = deviceTimezone()
const form = reactive<TodoForm>({ title: '', content: '', due_at: null, reminder_enabled: false, reminder_email: '', reminder_repeat: 'cron', reminder_timezone: localTimezone, reminder_cron: '0 9 * * *' })
let savedForm = ''
let closeConfirmation: Promise<boolean> | null = null
const editorDirty = computed(() => dialogVisible.value && JSON.stringify(form) !== savedForm)
function beforePageUnload(event: BeforeUnloadEvent) {
  if (!editorDirty.value && !saving.value) return
  event.preventDefault()
  event.returnValue = ''
}

async function confirmEditorLeave(): Promise<boolean> {
  if (saving.value) return false
  if (!editorDirty.value) return true
  if (closeConfirmation) return closeConfirmation
  closeConfirmation = ElMessageBox.confirm('待办有尚未保存的修改，确定放弃吗？', '未保存的修改', {
    confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning',
    closeOnClickModal: false, distinguishCancelAndClose: true,
  }).then(() => true, () => false)
  try { return await closeConfirmation } finally { closeConfirmation = null }
}

async function requestEditorClose() {
  if (await confirmEditorLeave()) dialogVisible.value = false
}

async function beforeEditorClose(done: () => void) {
  if (await confirmEditorLeave()) done()
}

if (inject(matchedRouteKey, null)) onBeforeRouteLeave(() => confirmEditorLeave())
const builder = reactive<TodoCronBuilder>({ preset: 'daily', time: '09:00', weekdays: [1, 2, 3, 4, 5], day: 1, month: 1, interval: 15 })
const cronPreview = ref<TodoCronPreview | null>(null)
const previewLoading = ref(false)
const previewError = ref('')
const previewedKey = ref('')
const cronKey = computed(() => JSON.stringify([form.reminder_cron, form.reminder_timezone]))
const needsPreview = computed(() => dialogVisible.value && form.reminder_enabled && form.reminder_repeat === 'cron')
const previewValid = computed(() => !needsPreview.value || !!cronPreview.value && previewedKey.value === cronKey.value && !previewLoading.value && !previewError.value)
const cronDescription = computed(() => describeTodoCron(form.reminder_cron))
const weekdays = [{ value: 1, label: '周一' }, { value: 2, label: '周二' }, { value: 3, label: '周三' }, { value: 4, label: '周四' }, { value: 5, label: '周五' }, { value: 6, label: '周六' }, { value: 0, label: '周日' }]
const errors = reactive<TodoFormErrors>({})
const now = ref(Date.now())
const busy = computed(() => loading.value || saving.value || operationId.value !== null || skipDialogVisible.value || skipSaving.value)
const canManage = computed(() => loaded.value && !loadError.value && !busy.value)
let active = true
let controller: AbortController | null = null
let refreshTimer: ReturnType<typeof setInterval> | undefined
let previewTimer: ReturnType<typeof setTimeout> | undefined
let previewController: AbortController | null = null
let previewRevision = 0
let skipPreviewController: AbortController | null = null
let skipPreviewRevision = 0

function canSkipPeriod(item: Todo) {
  return item.reminder_enabled && !item.is_completed && item.reminder_repeat !== 'once'
}

function resetSkipPreview() {
  skipPreviewController?.abort()
  skipPreviewController = null
  skipPreviewRevision++
  skipPreview.value = null
  skipPreviewLoading.value = false
  skipPreviewError.value = ''
}

watch([skipDialogVisible, skipPeriod], () => {
  resetSkipPreview()
  skipError.value = ''
  if (skipDialogVisible.value) void fetchSkipPreview()
}, { flush: 'sync' })

function openSkipPeriod(item: Todo) {
  if (!canManage.value || dialogVisible.value || !canSkipPeriod(item)) return
  skipTarget.value = item
  skipPeriod.value = recommendedTodoSkipPeriod(item)
  skipDialogVisible.value = true
}

async function fetchSkipPreview() {
  if (skipSaving.value) return
  resetSkipPreview()
  const target = skipTarget.value
  if (!active || !skipDialogVisible.value || !target) return
  const period = skipPeriod.value
  const revision = skipPreviewRevision
  const request = new AbortController()
  skipPreviewController = request
  skipPreviewLoading.value = true
  try {
    const result = await todosApi.previewSkipPeriod(target.id, period, request.signal)
    if (!active || request.signal.aborted || revision !== skipPreviewRevision || !skipDialogVisible.value || skipTarget.value?.id !== target.id || skipPeriod.value !== period) return
    if (result.period !== period || result.timezone !== target.reminder_timezone || !Number.isSafeInteger(result.reminder_revision) || result.reminder_revision < 0 || ![result.period_ends_at, result.next_run_at].every(value => typeof value === 'string' && Number.isFinite(new Date(value).getTime()))) throw new Error('invalid preview')
    new Intl.DateTimeFormat('zh-CN', { timeZone: result.timezone }).format()
    skipPreview.value = result
  } catch {
    if (active && !request.signal.aborted && revision === skipPreviewRevision) skipPreviewError.value = '无法确认下次提醒时间，请检查网络后重新预览。'
  } finally {
    if (active && revision === skipPreviewRevision) skipPreviewLoading.value = false
    if (skipPreviewController === request) skipPreviewController = null
  }
}

async function submitSkipPeriod() {
  const preview = skipPreview.value
  if (!active || !skipPreviewValid.value || skipSaving.value || !skipTarget.value || !preview) return
  let refreshPreview = false
  skipSaving.value = true
  skipError.value = ''
  try {
    await todosApi.skipPeriod(skipTarget.value.id, skipPeriod.value, preview)
    if (!active) return
    skipDialogVisible.value = false
    operationError.value = ''
    ElMessage.success('已跳过本周期剩余提醒，下周期按原规则恢复')
    await load()
  } catch {
    if (active) {
      resetSkipPreview()
      skipError.value = '操作未完成，已重新检查提醒时间，请确认后重试。'
      refreshPreview = true
    }
  } finally {
    if (active) {
      skipSaving.value = false
      if (refreshPreview) void fetchSkipPreview()
    }
  }
}

function formatSkipTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { timeZone: skipPreview.value?.timezone || skipTarget.value?.reminder_timezone, year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
}

function resetPreview() {
  if (previewTimer !== undefined) clearTimeout(previewTimer)
  previewController?.abort()
  previewRevision++
  cronPreview.value = null
  previewedKey.value = ''
  previewLoading.value = false
  previewError.value = ''
}

watch([needsPreview, cronKey], () => {
  resetPreview()
  if (needsPreview.value) {
    previewLoading.value = true
    previewTimer = setTimeout(() => { void fetchCronPreview() }, 350)
  }
}, { flush: 'sync' })

async function fetchCronPreview(): Promise<boolean> {
  resetPreview()
  if (!needsPreview.value || !active) return false
  let expression: string
  try {
    expression = normalizeTodoCron(form.reminder_cron)
    new Intl.DateTimeFormat('zh-CN', { timeZone: form.reminder_timezone }).format()
  } catch (cause) {
    previewError.value = cause instanceof Error ? cause.message : '请检查表达式和执行时区'
    return false
  }
  const revision = previewRevision
  const key = cronKey.value
  const request = new AbortController()
  previewController = request
  previewLoading.value = true
  try {
    const result = await todosApi.preview({ reminder_cron: expression, reminder_timezone: form.reminder_timezone }, request.signal)
    if (!active || request.signal.aborted || revision !== previewRevision || key !== cronKey.value || !needsPreview.value) return false
    if (result.times.length !== 5 || result.times.some(value => !Number.isFinite(new Date(value).getTime()))) throw new Error('invalid preview')
    cronPreview.value = result
    previewedKey.value = key
    return true
  } catch {
    if (active && !request.signal.aborted && revision === previewRevision && key === cronKey.value) previewError.value = '无法确认提醒时间，请检查表达式、时区或网络后重新预览。'
    return false
  } finally {
    if (active && revision === previewRevision) previewLoading.value = false
    if (previewController === request) previewController = null
  }
}

function applyCronBuilder() {
  if (builder.preset === 'custom') return
  try {
    form.reminder_cron = buildTodoCron(builder)
    errors.reminder_cron = ''
  } catch (cause) {
    form.reminder_cron = ''
    errors.reminder_cron = cause instanceof Error ? cause.message : '请补齐提醒时间'
  }
}

function configureCron() {
  form.reminder_repeat = 'cron'
  form.due_at = null
  form.reminder_cron = '0 9 * * *'
  Object.assign(builder, { preset: 'daily', time: '09:00', weekdays: [1, 2, 3, 4, 5], day: 1, month: 1, interval: 15 })
}

async function load() {
  if (loading.value || !active) return
  const current = new AbortController()
  controller = current
  loading.value = true
  loadError.value = false
  try {
    const result = await todosApi.list({ page: page.value, size: size.value, status: status.value, ...(query.value ? { q: query.value } : {}) }, current.signal)
    if (!active || current.signal.aborted) return
    list.value = result.items
    total.value = result.total
    page.value = result.page
    size.value = result.size
    emailConfigured.value = result.email_configured
    loaded.value = true
    now.value = Date.now()
  } catch {
    if (active && !current.signal.aborted) loadError.value = true
  } finally {
    if (active) loading.value = false
    if (controller === current) controller = null
  }
}

function search() {
  if (busy.value) return
  query.value = searchText.value.trim()
  page.value = 1
  void load()
}

function filterChanged() {
  if (busy.value) return
  page.value = 1
  void load()
}

function pageChanged(value: number) {
  if (busy.value || value === page.value) return
  page.value = value
  void load()
}

function sizeChanged(value: number) {
  if (busy.value) return
  size.value = value
  page.value = 1
  void load()
}

function clearErrors() {
  delete errors.title
  delete errors.content
  delete errors.due_at
  delete errors.reminder_email
  delete errors.reminder_repeat
  delete errors.reminder_timezone
  delete errors.reminder_cron
  saveError.value = ''
}

function openCreate() {
  if (!canManage.value) return
  editingId.value = null
  editingCompleted.value = false
  Object.assign(form, { title: '', content: '', due_at: null, reminder_enabled: false, reminder_email: '', reminder_repeat: 'cron', reminder_timezone: localTimezone, reminder_cron: '0 9 * * *' })
  Object.assign(builder, { preset: 'daily', time: '09:00', weekdays: [1, 2, 3, 4, 5], day: 1, month: 1, interval: 15 })
  clearErrors()
  savedForm = JSON.stringify(form)
  dialogVisible.value = true
}

function openEdit(item: Todo) {
  if (!canManage.value) return
  editingId.value = item.id
  editingCompleted.value = item.is_completed
  Object.assign(form, {
    title: item.title, content: item.content, due_at: item.due_at ? new Date(item.due_at) : null,
    reminder_enabled: item.is_completed ? false : item.reminder_enabled,
    reminder_email: item.reminder_email || '',
    reminder_repeat: item.reminder_repeat,
    reminder_timezone: item.reminder_timezone,
    reminder_cron: item.reminder_cron || '',
  })
  builder.preset = 'custom'
  clearErrors()
  savedForm = JSON.stringify(form)
  dialogVisible.value = true
}

async function save() {
  if (!canManage.value || !dialogVisible.value) return
  clearErrors()
  const result = prepareTodoInput(form)
  Object.assign(errors, result.errors)
  if (!result.input) return
  saving.value = true
  try {
    if (needsPreview.value && !previewValid.value && !await fetchCronPreview()) return
    if (editingId.value === null) await todosApi.create(result.input)
    else await todosApi.update(editingId.value, result.input)
    if (!active) return
    dialogVisible.value = false
    operationError.value = ''
    ElMessage.success(editingId.value === null ? '待办事项已创建' : '待办事项已更新')
    await load()
  } catch {
    if (active) saveError.value = '保存失败，填写的内容已保留，请检查后重试。'
  } finally {
    if (active) saving.value = false
  }
}

async function toggleCompletion(item: Todo) {
  if (!canManage.value) return
  operationId.value = item.id
  operationError.value = ''
  try {
    await todosApi.complete(item.id, !item.is_completed)
    if (!active) return
    ElMessage.success(item.is_completed ? '待办事项已重新打开，需要提醒时请在编辑中开启' : '待办事项已完成，邮件提醒已停止')
    if (list.value.length === 1 && page.value > 1 && status.value !== 'all') page.value--
    await load()
  } catch {
    if (active) operationError.value = '状态更新失败，请重试。'
  } finally {
    if (active) operationId.value = null
  }
}

async function retryReminder(item: Todo) {
  if (!canManage.value) return
  operationId.value = item.id
  operationError.value = ''
  try {
    await todosApi.retry(item.id)
    if (!active) return
    ElMessage.success('提醒已重新安排，将在下一次到期检查时发送')
    await load()
  } catch {
    if (active) operationError.value = '重新安排提醒失败，请检查邮件设置后重试。'
  } finally {
    if (active) operationId.value = null
  }
}

async function remove(item: Todo) {
  if (!canManage.value) return
  operationId.value = item.id
  try {
    try {
      await ElMessageBox.confirm(`确定删除待办“${item.title}”？删除后将停止尚未发送的提醒。`, '删除待办', {
        confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
      })
    } catch { return }
    operationError.value = ''
    await todosApi.remove(item.id)
    if (!active) return
    ElMessage.success('待办事项已删除')
    if (list.value.length === 1 && page.value > 1) page.value--
    await load()
  } catch {
    if (active) operationError.value = '删除失败，请重试。'
  } finally {
    if (active) operationId.value = null
  }
}

function formatTime(value: string | null) {
  if (!value) return '未设置'
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }) : '时间无效'
}

function nextReminder(item: Todo): string | null {
  if (item.is_completed || !item.reminder_enabled) return null
  return item.reminder_next_run_at || (item.reminder_repeat === 'once' ? item.due_at : null)
}

function reminderTimestamp(item: Todo) {
  const value = nextReminder(item)
  return value ? new Date(value).getTime() : NaN
}

function isOverdue(item: Todo) {
  return Number.isFinite(reminderTimestamp(item)) && reminderTimestamp(item) <= now.value
}

function executionDay(timestamp: number, timezone: string) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(timestamp))
}

function todoGroup(item: Todo): string {
  if (item.is_completed) return 'completed'
  const timestamp = reminderTimestamp(item)
  if (!Number.isFinite(timestamp)) return 'unscheduled'
  try {
    const day = executionDay(timestamp, item.reminder_timezone)
    if (timestamp <= now.value) return 'overdue'
    return day === executionDay(now.value, item.reminder_timezone) ? 'today' : 'upcoming'
  } catch { return 'unscheduled' }
}

const todoGroups = computed(() => [
  { key: 'overdue', label: '逾期', hint: '先处理这些未完成的事项' },
  { key: 'today', label: '今天', hint: '按每项提醒的执行时区计算' },
  { key: 'upcoming', label: '接下来', hint: '提前安排，按计划推进' },
  { key: 'unscheduled', label: '无提醒', hint: '按自己的节奏完成' },
  { key: 'completed', label: '已完成', hint: '每一步都有收获' },
].map(group => ({ ...group, items: list.value.filter(item => todoGroup(item) === group.key) })).filter(group => group.items.length))

function nextReminderLabel(item: Todo) {
  const value = nextReminder(item)
  if (!value) return item.is_completed ? '已完成，提醒已停止' : '未设置提醒'
  if (!Number.isFinite(new Date(value).getTime())) return '时间无效，请检查提醒设置'
  try {
    return new Intl.DateTimeFormat('zh-CN', { timeZone: item.reminder_timezone, month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
  } catch { return '时区无效，请检查提醒设置' }
}

function repeatLabel(item: Todo) {
  if (item.reminder_repeat === 'cron') return describeTodoCron(item.reminder_cron)
  if (item.reminder_repeat === 'once') return '仅一次'
  if (!item.due_at) return { daily: '每天', monthly: '每月', yearly: '每年' }[item.reminder_repeat]
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: item.reminder_timezone, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(item.due_at))
    const value = (type: Intl.DateTimeFormatPartTypes) => parts.find(part => part.type === type)?.value ?? ''
    const time = `${value('hour')}:${value('minute')}`
    if (item.reminder_repeat === 'daily') return `每天 ${time}`
    if (item.reminder_repeat === 'monthly') return `每月 ${value('day')} 日 ${time}`
    return `每年 ${value('month')} 月 ${value('day')} 日 ${time}`
  } catch {
    return '重复提醒（请检查时区）'
  }
}

function reminderLabel(item: Todo) {
  if (item.is_completed) return '已停止'
  if (!item.reminder_enabled) return '未开启'
  if (item.reminder_status === 'pending') return item.reminder_attempts > 0 ? '等待重试' : '待提醒'
  return { disabled: '未开启', sending: '发送中', sent: '已发送', failed: '发送失败' }[item.reminder_status]
}

function reminderType(item: Todo): 'info' | 'warning' | 'success' | 'danger' {
  if (item.is_completed || !item.reminder_enabled) return 'info'
  if (item.reminder_status === 'sent') return 'success'
  if (item.reminder_status === 'failed') return 'danger'
  return 'warning'
}

function formatPreviewTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { timeZone: cronPreview.value?.timezone || form.reminder_timezone, year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
}

onMounted(() => {
  window.addEventListener('beforeunload', beforePageUnload)
  void load()
  refreshTimer = setInterval(() => {
    now.value = Date.now()
    if (!document.hidden && loaded.value && !busy.value && !dialogVisible.value && !loadError.value) void load()
  }, 60000)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforePageUnload)
  active = false
  controller?.abort()
  resetPreview()
  resetSkipPreview()
  if (refreshTimer !== undefined) clearInterval(refreshTimer)
})
</script>

<template>
  <div class="todos-admin">
    <header class="page-heading">
      <div>
        <h2>待办事项</h2>
        <p>记录要做的事，用快捷设置或 crontab 自定义邮件提醒时间。完成事项后停止提醒。</p>
      </div>
      <div class="page-actions">
        <el-button :loading="loading" :disabled="busy" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Plus" :disabled="!canManage" @click="openCreate">新建待办</el-button>
      </div>
    </header>

    <el-alert v-if="loaded && !emailConfigured" class="notice" type="warning" :closable="false" show-icon title="邮件服务尚未配置，已开启的提醒会等待邮件服务就绪后发送。" />
    <p v-if="loaded && emailConfigured" class="reminder-destination">到期后约一分钟内发送提醒，收件邮箱可在每条待办中设置。</p>
    <el-alert v-if="operationError" class="notice" type="error" :closable="false" show-icon :title="operationError" />

    <div class="filter-bar">
      <el-select v-model="status" aria-label="待办状态" :disabled="busy" class="status-filter" @change="filterChanged">
        <el-option label="全部事项" value="all" />
        <el-option label="未完成" value="pending" />
        <el-option label="已完成" value="completed" />
        <el-option label="已逾期" value="overdue" />
      </el-select>
      <form class="search-form" @submit.prevent="search">
        <el-input v-model="searchText" maxlength="200" placeholder="搜索标题或内容" clearable :disabled="busy" aria-label="搜索待办事项" @clear="search" />
        <el-button native-type="submit" :disabled="busy">搜索</el-button>
      </form>
    </div>

    <el-result v-if="loadError" icon="error" title="待办事项加载失败" sub-title="请检查网络后重试，已有待办不会受到影响。">
      <template #extra><el-button type="primary" :loading="loading" :disabled="busy" @click="load">重新加载</el-button></template>
    </el-result>
    <div v-else-if="loading && !loaded" class="admin-initial-loading" role="status" aria-label="待办加载中"><p>正在整理待办事项…</p><el-skeleton :rows="6" animated /></div>
    <template v-else>
      <div class="todo-agenda" v-loading="loading" aria-label="当前页待办，按提醒时间分组">
        <el-empty v-if="!list.length && !loading" description="暂无待办事项，记录下一件要做的事吧" />
        <p v-if="total > size" class="group-scope">以下为当前页事项，按各自执行时区分组</p>
        <section v-for="group in todoGroups" :key="group.key" :data-group="group.key" class="todo-group" :aria-labelledby="'todo-group-' + group.key">
          <header class="group-heading">
            <h3 :id="'todo-group-' + group.key">{{ group.label }}<span>{{ group.items.length }}</span></h3>
            <p>{{ group.hint }}</p>
          </header>
          <div class="todo-cards">
            <article v-for="row in group.items" :key="row.id" class="todo-card" :class="{ 'is-overdue': isOverdue(row), 'is-completed': row.is_completed }">
              <div class="todo-card-main">
                <div class="card-heading">
                  <strong class="todo-title" :class="{ completed: row.is_completed }">{{ row.title }}</strong>
                  <el-tag v-if="row.is_completed" size="small" type="success" effect="plain">已完成</el-tag>
                  <el-tag v-else-if="row.reminder_enabled" :type="reminderType(row)" size="small" effect="plain">{{ reminderLabel(row) }}</el-tag>
                </div>
                <p v-if="row.content" class="todo-content">{{ row.content }}</p>
                <div class="next-reminder" :class="{ 'overdue-time': isOverdue(row) }">
                  <span class="next-caption">{{ nextReminder(row) ? '下次提醒' : '提醒' }}</span>
                  <time v-if="Number.isFinite(reminderTimestamp(row))" :datetime="nextReminder(row) || undefined">{{ nextReminderLabel(row) }}</time>
                  <span v-else>{{ nextReminderLabel(row) }}</span>
                  <span v-if="isOverdue(row)" class="overdue-label">已逾期</span>
                </div>
              </div>
              <div class="row-actions card-actions">
                <el-button size="small" :type="row.is_completed ? 'default' : 'success'" plain :disabled="!canManage" :loading="operationId === row.id" @click="toggleCompletion(row)">{{ row.is_completed ? '重新打开' : '完成' }}</el-button>
                <el-button size="small" :disabled="!canManage" @click="openEdit(row)">编辑</el-button>
              </div>
              <details class="todo-secondary">
                <summary>提醒详情与更多操作</summary>
                <div class="todo-details-grid">
                  <div v-if="row.content"><span class="detail-caption">完整说明</span><p class="full-content">{{ row.content }}</p></div>
                  <div><span class="detail-caption">提醒计划</span><p>{{ repeatLabel(row) }} · {{ row.reminder_timezone }}</p><code v-if="row.reminder_repeat === 'cron'">{{ row.reminder_cron }}</code></div>
                  <div v-if="row.reminder_email"><span class="detail-caption">收件邮箱</span><p>{{ row.reminder_email }}</p></div>
                  <div v-if="row.reminder_sent_at"><span class="detail-caption">最近发送</span><p>{{ formatTime(row.reminder_sent_at) }}</p></div>
                  <div v-if="row.reminder_error"><span class="detail-caption">提醒异常</span><p>{{ row.reminder_error }}（已尝试 {{ row.reminder_attempts }} 次）</p></div>
                </div>
                <div class="row-actions">
                  <el-button size="small" @click="historyTarget = row; historyVisible = true">提醒历史</el-button>
                  <el-button v-if="!row.is_completed && row.reminder_enabled && row.reminder_status === 'failed'" size="small" type="warning" plain :disabled="!canManage" @click="retryReminder(row)">重试提醒</el-button>
                  <el-button v-if="canSkipPeriod(row)" size="small" :disabled="!canManage" @click="openSkipPeriod(row)">不再提醒</el-button>
                  <el-button size="small" type="danger" text :disabled="!canManage" @click="remove(row)">删除</el-button>
                </div>
              </details>
            </article>
          </div>
        </section>
      </div>
      <div class="pagination">
        <el-pagination :current-page="page" :page-size="size" :page-sizes="[10, 20, 50]" :total="total" :disabled="busy" layout="total, sizes, prev, pager, next" @current-change="pageChanged" @size-change="sizeChanged" />
      </div>
    </template>

    <TodoHistory v-model="historyVisible" :todo="historyTarget" />

    <el-dialog v-model="skipDialogVisible" title="本周期不再提醒" class="skip-period-dialog" width="min(560px, calc(100vw - 28px))" :close-on-click-modal="!skipSaving" :close-on-press-escape="!skipSaving" :show-close="!skipSaving" append-to-body>
      <template v-if="skipTarget">
        <p class="skip-title">{{ skipTarget.title }}</p>
        <p class="field-hint">跳过所选周期剩余的提醒，下周期按原规则自动恢复。</p>
        <el-radio-group v-model="skipPeriod" class="skip-period-options" :disabled="skipSaving" aria-label="跳过提醒周期">
          <el-radio-button v-for="period in skipPeriods" :key="period.value" :value="period.value">{{ period.label }}</el-radio-button>
        </el-radio-group>
        <dl class="skip-details">
          <div><dt>提醒规则</dt><dd>{{ repeatLabel(skipTarget) }}<code v-if="skipTarget.reminder_repeat === 'cron'" class="cron-expression">{{ skipTarget.reminder_cron }}</code></dd></div>
          <div><dt>执行时区</dt><dd>{{ skipPreview?.timezone || skipTarget.reminder_timezone }}</dd></div>
          <template v-if="skipPreview">
            <div><dt>本周期结束</dt><dd><time :datetime="skipPreview.period_ends_at">{{ formatSkipTime(skipPreview.period_ends_at) }}</time></dd></div>
            <div><dt>下次提醒</dt><dd><time :datetime="skipPreview.next_run_at">{{ formatSkipTime(skipPreview.next_run_at) }}</time></dd></div>
          </template>
        </dl>
        <div aria-live="polite">
          <p v-if="skipPreviewLoading" class="field-hint">正在确认下次提醒时间…</p>
          <p v-else-if="skipPreviewError" class="save-error" role="alert">{{ skipPreviewError }}</p>
          <el-button v-if="skipPreviewError" size="small" :disabled="skipSaving" @click="fetchSkipPreview">重新预览</el-button>
        </div>
        <p class="field-hint">周期按以上执行时区计算，周从周一开始。</p>
        <p v-if="skipError" class="save-error" role="alert">{{ skipError }}</p>
      </template>
      <template #footer>
        <el-button :disabled="skipSaving" @click="skipDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="skipSaving" :disabled="skipSaving || !skipPreviewValid" @click="submitSkipPeriod">{{ skipError ? '重试跳过' : '确认跳过' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新建待办' : '编辑待办'" width="min(680px, calc(100vw - 28px))" :before-close="beforeEditorClose" :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" append-to-body>
      <el-form :model="form" label-position="top" :disabled="saving" @submit.prevent="save">
        <el-form-item label="标题" :error="errors.title" required>
          <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="接下来要做什么？" @input="errors.title = ''" />
        </el-form-item>
        <el-form-item label="内容（选填）" :error="errors.content">
          <el-input v-model="form.content" type="textarea" :rows="5" maxlength="10000" show-word-limit placeholder="补充说明或备忘内容" @input="errors.content = ''" />
        </el-form-item>
        <el-form-item label="邮件提醒">
          <el-switch v-model="form.reminder_enabled" active-text="按计划提醒我" :disabled="saving || editingCompleted" aria-label="启用到期邮件提醒" @change="errors.due_at = ''" />
          <p v-if="editingCompleted" class="field-hint">已完成的事项不再提醒，重新打开后可再次开启。</p>
          <p v-else class="field-hint">填写收件邮箱并设置提醒时间，关闭后停止后续发送。</p>
        </el-form-item>
        <section v-if="form.reminder_repeat !== 'cron'" class="legacy-schedule">
          <strong>已保留原提醒计划</strong>
          <p>仅修改标题、内容或邮箱不会改变原计划。需要调整提醒时间时，可设置新的 crontab 规则。</p>
          <el-button :disabled="saving || editingCompleted" @click="configureCron">修改提醒规则</el-button>
          <p v-if="errors.due_at" class="save-error" role="alert">{{ errors.due_at }}</p>
        </section>
        <section v-else class="cron-schedule" aria-label="Crontab 提醒设置">
          <el-form-item label="快捷设置">
            <el-select v-model="builder.preset" aria-label="提醒快捷设置" :disabled="editingCompleted" @change="applyCronBuilder">
              <el-option label="每天" value="daily" />
              <el-option label="每周" value="weekly" />
              <el-option label="每月" value="monthly" />
              <el-option label="每年" value="yearly" />
              <el-option label="每隔几分钟" value="interval" />
              <el-option label="自定义表达式" value="custom" />
            </el-select>
          </el-form-item>
          <div v-if="builder.preset !== 'custom'" class="cron-builder-fields">
            <el-form-item v-if="builder.preset !== 'interval'" label="提醒时刻">
              <el-time-picker v-model="builder.time" format="HH:mm" value-format="HH:mm" :clearable="false" :disabled="editingCompleted" aria-label="提醒时刻" @change="applyCronBuilder" />
            </el-form-item>
            <el-form-item v-if="builder.preset === 'weekly'" label="星期">
              <el-checkbox-group v-model="builder.weekdays" :disabled="editingCompleted" aria-label="提醒星期" @change="applyCronBuilder">
                <el-checkbox v-for="day in weekdays" :key="day.value" :value="day.value">{{ day.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item v-if="builder.preset === 'yearly'" label="月份">
              <el-select v-model="builder.month" :disabled="editingCompleted" aria-label="提醒月份" @change="applyCronBuilder">
                <el-option v-for="month in 12" :key="month" :label="`${month} 月`" :value="month" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="builder.preset === 'monthly' || builder.preset === 'yearly'" label="日期">
              <el-input-number v-model="builder.day" :min="1" :max="31" :precision="0" :disabled="editingCompleted" aria-label="每月提醒日期" @change="applyCronBuilder" />
            </el-form-item>
            <el-form-item v-if="builder.preset === 'interval'" label="间隔分钟数">
              <el-input-number v-model="builder.interval" :min="1" :max="59" :precision="0" :disabled="editingCompleted" aria-label="提醒间隔分钟数" @change="applyCronBuilder" />
              <p class="field-hint">从每小时第 0 分钟开始，按步长匹配分钟。</p>
            </el-form-item>
          </div>
          <el-form-item label="Crontab 表达式" :error="errors.reminder_cron" :required="form.reminder_enabled">
            <el-input v-model="form.reminder_cron" maxlength="128" class="cron-expression" :disabled="editingCompleted" placeholder="0 9 * * 1-5" aria-label="Crontab 表达式" @input="builder.preset = 'custom'; errors.reminder_cron = ''" />
            <p class="field-hint">分 时 日 月 周，例如 <code>0 9 * * 1-5</code> 表示工作日 09:00。支持 *、范围、列表和步长，不包含秒或执行命令。</p>
          </el-form-item>
          <el-form-item label="执行时区" :error="errors.reminder_timezone">
            <el-select v-model="form.reminder_timezone" filterable allow-create default-first-option :disabled="editingCompleted" aria-label="提醒执行时区" @change="errors.reminder_timezone = ''">
              <el-option :label="`设备时区（${localTimezone}）`" :value="localTimezone" />
              <el-option v-if="localTimezone !== 'Asia/Shanghai'" label="Asia/Shanghai（上海）" value="Asia/Shanghai" />
              <el-option v-if="localTimezone !== 'UTC'" label="UTC" value="UTC" />
              <el-option v-if="localTimezone !== 'America/New_York'" label="America/New_York（纽约）" value="America/New_York" />
              <el-option v-if="localTimezone !== 'Europe/London'" label="Europe/London（伦敦）" value="Europe/London" />
            </el-select>
          </el-form-item>
          <div class="cron-preview" aria-live="polite">
            <strong>{{ cronDescription }}</strong>
            <p v-if="previewLoading" class="field-hint">正在确认未来提醒时间…</p>
            <p v-else-if="previewError" class="save-error" role="alert">{{ previewError }}</p>
            <template v-else-if="cronPreview">
              <p class="field-hint">接下来 5 次提醒 · {{ cronPreview.timezone }}</p>
              <ol class="cron-preview-list"><li v-for="time in cronPreview.times" :key="time"><time :datetime="time">{{ formatPreviewTime(time) }}</time></li></ol>
            </template>
            <p v-else class="field-hint">开启邮件提醒后预览实际执行时间。</p>
            <el-button v-if="form.reminder_enabled" size="small" :loading="previewLoading" :disabled="saving || editingCompleted" @click="fetchCronPreview">重新预览</el-button>
          </div>
          <p class="field-hint">不存在的日期会跳过该月或该年；日期和星期同时指定时，满足任一条件即可提醒。后台每分钟检查，漏过多次只补发一次。</p>
        </section>
        <el-form-item :label="form.reminder_enabled ? '收件邮箱' : '收件邮箱（选填）'" :error="errors.reminder_email" :required="form.reminder_enabled">
          <el-input v-model="form.reminder_email" type="email" maxlength="254" autocomplete="email" placeholder="例如：name@example.com" clearable aria-label="提醒收件邮箱" @input="errors.reminder_email = ''" />
          <p class="field-hint">填写一个邮箱地址。关闭提醒会保留该地址，方便以后再次启用。</p>
        </el-form-item>
        <el-alert v-if="form.reminder_enabled && !emailConfigured" type="warning" :closable="false" show-icon title="请先配置邮件服务，否则提醒会等待发送。" />
        <p v-if="saveError" class="save-error" role="alert">{{ saveError }}</p>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="requestEditorClose">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="saving || !previewValid" @click="save">{{ saveError ? '重试保存' : '保存待办' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.todo-agenda { min-height: 140px; }
.group-scope { margin: 0 0 20px; color: var(--el-text-color-secondary); font-size: 12px; }
.todo-group + .todo-group { margin-top: 32px; }
.group-heading { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin: 0 0 12px; }
.group-heading h3 { margin: 0; display: flex; gap: 8px; align-items: center; font-size: 15px; }
.group-heading h3 span { border-radius: 6px; padding: 2px 7px; background: var(--el-fill-color); color: var(--el-text-color-secondary); font-size: 12px; font-weight: 500; }
.group-heading p { margin: 0; color: var(--el-text-color-secondary); font-size: 12px; }
.todo-cards { display: grid; gap: 12px; }
.todo-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 24px; min-width: 0; padding: 20px; border: 1px solid var(--el-border-color-lighter); border-radius: 12px; background: var(--app-surface); overflow-wrap: anywhere; }
.todo-card.is-overdue { border-left: 3px solid var(--el-color-danger); }
.todo-card.is-completed { background: var(--el-fill-color-blank); }
.card-heading { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.card-heading .todo-title { font-size: 15px; font-weight: 600; }
.card-actions { align-self: start; margin: 0; }
.next-reminder { display: flex; gap: 10px; flex-wrap: wrap; align-items: baseline; margin-top: 14px; font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }
.next-caption { color: var(--el-text-color-secondary); font-size: 12px; font-weight: 400; }
.next-reminder .overdue-label { font-size: 12px; font-weight: 400; }
.todo-card details { grid-column: 1 / -1; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); color: var(--el-text-color-secondary); font-size: 13px; }
.todo-card summary { cursor: pointer; width: fit-content; line-height: 1.7; }
.todo-card details[open] summary { margin-bottom: 16px; }
.todo-details-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 24px; margin-bottom: 16px; }
.todo-details-grid p { margin: 5px 0 0; line-height: 1.7; color: var(--el-text-color-regular); }
.todo-details-grid code { display: block; margin-top: 6px; color: var(--el-text-color-regular); }
.detail-caption { font-size: 12px; color: var(--el-text-color-secondary); }
.full-content { white-space: pre-wrap; }
@media (max-width: 700px) {
  .todo-card { grid-template-columns: minmax(0, 1fr); gap: 0; padding: 16px; }
  .card-actions { margin-top: 16px; }
  .todo-details-grid { grid-template-columns: minmax(0, 1fr); }
  .group-heading { gap: 8px; }
  .group-heading p { width: 100%; }
}
.todos-admin { min-width: 0; }
.page-heading { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 18px; }
.page-heading h2 { margin: 0; font-size: 24px; }
.page-heading p { margin: 8px 0 0; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.7; }
.page-actions { display: flex; flex-shrink: 0; }
.notice { margin-bottom: 16px; }
.reminder-destination { margin: 0 0 16px; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.filter-bar { display: flex; gap: 12px; margin: 0 0 16px; flex-wrap: wrap; }
.status-filter { width: 150px; }
.search-form { display: flex; gap: 8px; width: min(420px, 100%); }
.search-form > :deep(.el-input) { min-width: 0; }
.todo-title { color: var(--el-text-color-primary); line-height: 1.65; overflow-wrap: anywhere; font-weight: 500; }
.todo-title.completed { color: var(--el-text-color-secondary); text-decoration: line-through; }
.todo-content { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin: 5px 0 0; color: var(--el-text-color-secondary); line-height: 1.6; white-space: pre-line; overflow-wrap: anywhere; font-size: 12px; }
.overdue-time, .overdue-label { color: var(--el-color-danger); }
.overdue-label { display: block; font-size: 12px; }
.row-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.row-actions :deep(.el-button + .el-button) { margin-left: 0; }
.pagination { display: flex; justify-content: flex-end; overflow-x: auto; margin-top: 18px; padding-bottom: 6px; }
.field-hint { width: 100%; margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.save-error { margin: 12px 0 0; color: var(--el-color-danger); font-size: 13px; line-height: 1.7; }
.cron-schedule, .legacy-schedule { margin-bottom: 20px; padding: 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--el-fill-color-blank); }
.legacy-schedule p { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.cron-builder-fields { display: flex; gap: 12px; flex-wrap: wrap; }
.cron-builder-fields > .el-form-item { flex: 1 1 180px; min-width: 0; }
.cron-builder-fields :deep(.el-checkbox) { margin-right: 14px; }
.cron-expression { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.cron-expression :deep(input) { font-family: inherit; }
.cron-preview { padding: 12px; border-radius: 6px; background: var(--el-fill-color-light); font-size: 13px; }
.cron-preview-list { margin: 8px 0 12px; padding-left: 24px; color: var(--el-text-color-regular); line-height: 1.9; font-variant-numeric: tabular-nums; }
.skip-title { margin: 0 0 6px; color: var(--el-text-color-primary); font-size: 16px; font-weight: 500; overflow-wrap: anywhere; }
.skip-period-options { display: flex; margin: 18px 0; }
.skip-period-options :deep(.el-radio-button) { flex: 1; min-width: 0; }
.skip-period-options :deep(.el-radio-button__inner) { box-sizing: border-box; width: 100%; padding-inline: 12px; }
.skip-details { margin: 0; padding: 14px; border-radius: 6px; background: var(--el-fill-color-light); line-height: 1.7; font-size: 13px; }
.skip-details > div { display: grid; grid-template-columns: 84px minmax(0, 1fr); gap: 10px; margin-bottom: 10px; }
.skip-details > div:last-child { margin-bottom: 0; }
.skip-details dt { color: var(--el-text-color-secondary); }
.skip-details dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
.skip-details code { display: block; margin-top: 4px; }
@media (max-width: 600px) {
  .page-heading { align-items: flex-start; }
  .page-actions { width: 100%; }
  .page-actions > :deep(.el-button) { flex: 1; }
  .filter-bar { gap: 10px; }
  .status-filter, .search-form { width: 100%; }
  .pagination { justify-content: flex-start; }
}
</style>
