<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { todosApi, type Todo, type TodoHistoryEntry } from '@/api/todos'

const props = defineProps<{ todo: Todo | null; modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const visible = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
const items = ref<TodoHistoryEntry[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const error = ref('')
const pageSize = 10
let controller: AbortController | null = null
let revision = 0
let active = true

function cancel() {
  revision++
  controller?.abort()
  controller = null
  loading.value = false
}

async function load(nextPage = page.value) {
  if (!active || !props.modelValue || !props.todo) return
  cancel()
  const current = revision
  const target = props.todo.id
  const request = new AbortController()
  controller = request
  page.value = nextPage
  loading.value = true
  error.value = ''
  try {
    const result = await todosApi.history(target, nextPage, pageSize, request.signal)
    if (!active || request.signal.aborted || current !== revision || !props.modelValue || props.todo?.id !== target) return
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize))
    if (nextPage > lastPage) { await load(lastPage); return }
    items.value = result.items
    total.value = result.total
    page.value = result.page
  } catch {
    if (!active || request.signal.aborted || current !== revision) return
    items.value = []
    error.value = '提醒历史加载失败，请重试。'
  } finally {
    if (active && current === revision) loading.value = false
    if (controller === request) controller = null
  }
}

watch(() => [props.modelValue, props.todo?.id], () => {
  cancel()
  if (props.modelValue && props.todo) {
    items.value = []
    total.value = 0
    page.value = 1
    void load(1)
  }
}, { immediate: true })
onBeforeUnmount(() => { active = false; cancel() })

function time(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return value
  return date.toLocaleString('zh-CN', { timeZone: props.todo?.reminder_timezone || 'Asia/Shanghai', hour12: false })
}
const resultLabels = { sent: '发送成功', failed: '发送失败', skipped: '已跳过' }
const periodLabels = { day: '本日', week: '本周', month: '本月', year: '本年', '': '' }
</script>

<template>
  <el-dialog v-model="visible" title="提醒历史" width="min(760px, calc(100vw - 28px))" class="todo-history-dialog" append-to-body>
    <p class="history-title">{{ todo?.title }}</p>
    <p class="history-hint">时间按 {{ todo?.reminder_timezone || 'Asia/Shanghai' }} 显示；失败详情已脱敏。</p>
    <div v-if="error" role="alert" class="history-error">{{ error }} <el-button @click="load()">重试</el-button></div>
    <div v-loading="loading" :aria-busy="loading" class="history-list">
      <p v-if="loading" role="status" class="history-hint">正在加载提醒历史…</p>
      <p v-else-if="!error && !items.length" class="history-empty">暂无提醒历史</p>
      <article v-for="entry in items" :key="entry.id" class="history-card">
        <div class="history-result"><el-tag :type="entry.event === 'failed' ? 'danger' : entry.event === 'sent' ? 'success' : 'info'">{{ resultLabels[entry.event] }}</el-tag><span v-if="entry.period">{{ periodLabels[entry.period] }}不再提醒</span></div>
        <dl>
          <div><dt>计划时间</dt><dd><time :datetime="entry.scheduled_at || undefined">{{ time(entry.scheduled_at) }}</time></dd></div>
          <div><dt>记录时间</dt><dd><time :datetime="entry.created_at">{{ time(entry.created_at) }}</time></dd></div>
          <div><dt>下次提醒</dt><dd><time :datetime="entry.next_run_at || undefined">{{ time(entry.next_run_at) }}</time></dd></div>
          <div v-if="entry.error"><dt>失败详情</dt><dd class="history-detail">{{ entry.error }}</dd></div>
        </dl>
      </article>
    </div>
    <div class="history-footer"><span class="history-hint">共 {{ total }} 条记录</span><el-pagination v-if="total > pageSize" :current-page="page" :page-size="pageSize" :total="total" :disabled="loading" layout="prev, pager, next" :pager-count="5" @current-change="load" /></div>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>

<style scoped>
.history-title { margin: 0 0 6px; font-weight: 600; overflow-wrap: anywhere; }
.history-hint { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; }
.history-error { display: flex; align-items: center; gap: 12px; margin: 16px 0; color: var(--el-color-danger); }
.history-list { min-height: 80px; }
.history-empty { padding: 28px 0; text-align: center; color: var(--el-text-color-secondary); }
.history-card { padding: 14px; margin-top: 12px; border: 1px solid var(--el-border-color-light); border-radius: 8px; }
.history-result { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.history-card dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 16px; margin: 14px 0 0; }
.history-card dl > div { min-width: 0; }
.history-card dt { margin-bottom: 4px; color: var(--el-text-color-secondary); font-size: 12px; }
.history-card dd { margin: 0; overflow-wrap: anywhere; font-size: 13px; }
.history-detail { white-space: pre-wrap; }
.history-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-top: 16px; }
@media (max-width: 520px) { .history-card dl { grid-template-columns: 1fr; } }
</style>
