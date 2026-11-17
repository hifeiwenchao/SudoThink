<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { todosApi, type Todo, type TodoFilter } from '@/api/todos'
import { prepareTodoInput, type TodoForm, type TodoFormErrors } from '@/utils/todos'

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
const editingId = ref<number | null>(null)
const editingCompleted = ref(false)
const saving = ref(false)
const saveError = ref('')
const form = reactive<TodoForm>({ title: '', content: '', due_at: null, reminder_enabled: false, reminder_email: '' })
const errors = reactive<TodoFormErrors>({})
const now = ref(Date.now())
const busy = computed(() => loading.value || saving.value || operationId.value !== null)
const canManage = computed(() => loaded.value && !loadError.value && !busy.value)
let active = true
let controller: AbortController | null = null
let refreshTimer: ReturnType<typeof setInterval> | undefined

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
  saveError.value = ''
}

function openCreate() {
  if (!canManage.value) return
  editingId.value = null
  editingCompleted.value = false
  Object.assign(form, { title: '', content: '', due_at: null, reminder_enabled: false, reminder_email: '' })
  clearErrors()
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
  })
  clearErrors()
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

function isOverdue(item: Todo) {
  return !item.is_completed && !!item.due_at && new Date(item.due_at).getTime() <= now.value
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

onMounted(() => {
  void load()
  refreshTimer = setInterval(() => {
    now.value = Date.now()
    if (!document.hidden && loaded.value && !busy.value && !dialogVisible.value && !loadError.value) void load()
  }, 60000)
})

onBeforeUnmount(() => {
  active = false
  controller?.abort()
  if (refreshTimer !== undefined) clearInterval(refreshTimer)
})
</script>

<template>
  <div class="todos-admin">
    <header class="page-heading">
      <div>
        <h2>待办事项</h2>
        <p>记录要做的事，按需设置一次邮件提醒。完成事项后，尚未发送的提醒会停止。</p>
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
    <template v-else>
      <div class="table-panel">
        <el-table v-loading="loading" :data="list" stripe row-key="id" empty-text="暂无待办事项，点击“新建待办”记录一件事" class="todo-table">
          <el-table-column label="事项" min-width="260">
            <template #default="{ row }">
              <div class="todo-title" :class="{ completed: row.is_completed }">{{ row.title }}</div>
              <p v-if="row.content" class="todo-content">{{ row.content }}</p>
            </template>
          </el-table-column>
          <el-table-column label="到期时间" min-width="175">
            <template #default="{ row }">
              <span :class="{ 'overdue-time': isOverdue(row) }">{{ formatTime(row.due_at) }}</span>
              <span v-if="isOverdue(row)" class="overdue-label">已逾期</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="92">
            <template #default="{ row }"><el-tag :type="row.is_completed ? 'success' : 'info'" effect="plain">{{ row.is_completed ? '已完成' : '未完成' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="邮件提醒" min-width="220">
            <template #default="{ row }">
              <el-tag :type="reminderType(row)" effect="plain">{{ reminderLabel(row) }}</el-tag>
              <span v-if="row.reminder_email" class="reminder-detail reminder-email" :title="row.reminder_email">{{ row.reminder_email }}</span>
              <p v-if="row.reminder_sent_at" class="reminder-detail">{{ formatTime(row.reminder_sent_at) }}</p>
              <el-tooltip v-else-if="row.reminder_error" :content="row.reminder_error" placement="top" :show-after="300">
                <span class="reminder-detail error-detail">已尝试 {{ row.reminder_attempts }} 次</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="270" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button size="small" :type="row.is_completed ? 'default' : 'success'" plain :disabled="!canManage" :loading="operationId === row.id" @click="toggleCompletion(row)">{{ row.is_completed ? '重新打开' : '完成' }}</el-button>
                <el-button size="small" :disabled="!canManage" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" type="danger" plain :disabled="!canManage" @click="remove(row)">删除</el-button>
                <el-button v-if="!row.is_completed && row.reminder_enabled && row.reminder_status === 'failed'" size="small" type="warning" plain :disabled="!canManage" @click="retryReminder(row)">重试提醒</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="pagination">
        <el-pagination :current-page="page" :page-size="size" :page-sizes="[10, 20, 50]" :total="total" :disabled="busy" layout="total, sizes, prev, pager, next" @current-change="pageChanged" @size-change="sizeChanged" />
      </div>
    </template>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新建待办' : '编辑待办'" width="min(600px, calc(100vw - 28px))" :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" append-to-body>
      <el-form :model="form" label-position="top" :disabled="saving" @submit.prevent="save">
        <el-form-item label="标题" :error="errors.title" required>
          <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="接下来要做什么？" @input="errors.title = ''" />
        </el-form-item>
        <el-form-item label="内容（选填）" :error="errors.content">
          <el-input v-model="form.content" type="textarea" :rows="5" maxlength="10000" show-word-limit placeholder="补充说明或备忘内容" @input="errors.content = ''" />
        </el-form-item>
        <el-form-item label="到期时间（选填）" :error="errors.due_at">
          <el-date-picker v-model="form.due_at" type="datetime" format="YYYY-MM-DD HH:mm" placeholder="选择到期时间" clearable aria-label="待办到期时间" @change="errors.due_at = ''" />
          <p class="field-hint">按当前设备的本地时间设置和显示。</p>
        </el-form-item>
        <el-form-item label="邮件提醒">
          <el-switch v-model="form.reminder_enabled" active-text="到期后提醒我" :disabled="saving || editingCompleted" aria-label="启用到期邮件提醒" @change="errors.due_at = ''" />
          <p v-if="editingCompleted" class="field-hint">已完成的事项不再提醒，重新打开后可再次开启。</p>
          <p v-else class="field-hint">开启后填写收件邮箱，提醒发送一次；修改到期时间或收件邮箱可重新安排。</p>
        </el-form-item>
        <el-form-item :label="form.reminder_enabled ? '收件邮箱' : '收件邮箱（选填）'" :error="errors.reminder_email" :required="form.reminder_enabled">
          <el-input v-model="form.reminder_email" type="email" maxlength="254" autocomplete="email" placeholder="例如：name@example.com" clearable aria-label="提醒收件邮箱" @input="errors.reminder_email = ''" />
          <p class="field-hint">填写一个邮箱地址。关闭提醒会保留该地址，方便以后再次启用。</p>
        </el-form-item>
        <el-alert v-if="form.reminder_enabled && !emailConfigured" type="warning" :closable="false" show-icon title="请先配置邮件服务，否则提醒会等待发送。" />
        <p v-if="saveError" class="save-error" role="alert">{{ saveError }}</p>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="saving" @click="save">{{ saveError ? '重试保存' : '保存待办' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
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
.table-panel { min-width: 0; overflow: hidden; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--app-surface); }
.todo-table { width: 100%; }
.todo-title { color: var(--el-text-color-primary); line-height: 1.65; overflow-wrap: anywhere; font-weight: 500; }
.todo-title.completed { color: var(--el-text-color-secondary); text-decoration: line-through; }
.todo-content { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin: 5px 0 0; color: var(--el-text-color-secondary); line-height: 1.6; white-space: pre-line; overflow-wrap: anywhere; font-size: 12px; }
.overdue-time, .overdue-label { color: var(--el-color-danger); }
.overdue-label { display: block; font-size: 12px; }
.reminder-detail { display: block; margin: 5px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
.reminder-email { overflow-wrap: anywhere; }
.error-detail { cursor: help; color: var(--el-color-warning); }
.row-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.row-actions :deep(.el-button + .el-button) { margin-left: 0; }
.pagination { display: flex; justify-content: flex-end; overflow-x: auto; margin-top: 18px; padding-bottom: 6px; }
.field-hint { width: 100%; margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.save-error { margin: 12px 0 0; color: var(--el-color-danger); font-size: 13px; line-height: 1.7; }
@media (max-width: 600px) {
  .page-heading { align-items: flex-start; }
  .page-actions { width: 100%; }
  .page-actions > :deep(.el-button) { flex: 1; }
  .filter-bar { gap: 10px; }
  .status-filter, .search-form { width: 100%; }
  .pagination { justify-content: flex-start; }
}
</style>
