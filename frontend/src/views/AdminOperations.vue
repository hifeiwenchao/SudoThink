<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { operationsApi, type CdnConfiguration, type CdnOperation, type CdnSubmission, type CdnTask } from '@/api/operations'
import { cdnOperationLimit, parseCdnUrls, validateCdnUrls } from '@/utils/cdnOperations'
import ApiRequestLogs from '@/components/operations/ApiRequestLogs.vue'

const activeTab = ref('cdn')
const config = ref<CdnConfiguration | null>(null)
const configLoading = ref(false)
const configError = ref('')
const operation = ref<CdnOperation>('File')
const input = ref('')
const inputError = ref('')
const submitting = ref(false)
const submitError = ref('')
const submission = ref<CdnSubmission | null>(null)
const submittedOperation = ref('')
const queryTaskId = ref('')
const taskItems = ref<CdnTask[]>([])
const taskTotal = ref(0)
const taskPage = ref(1)
const taskLoading = ref(false)
const taskError = ref('')
const taskQuery = ref('')
const taskRequestId = ref('')
const taskPageSize = 20
let active = true
let taskRequest = 0
let configController: AbortController | null = null
let taskController: AbortController | null = null

const operationLabels: Record<CdnOperation, string> = { File: '文件 URL 刷新', Directory: '目录刷新', Regex: '正则刷新', Preload: 'URL 预热' }
const operations = computed(() => [...(config.value?.refresh_types ?? []), 'Preload'] as CdnOperation[])
const available = computed(() => Boolean(config.value?.enabled) && !configLoading.value)
const urls = computed(() => parseCdnUrls(input.value))
const limit = computed(() => config.value ? cdnOperationLimit(operation.value, config.value.limits) : 0)
const submittedTaskIds = computed(() => submission.value?.task_id.split(',').map((id) => id.trim()).filter(Boolean) ?? [])
const placeholder = computed(() => {
  const base = config.value?.cdn_base_url.replace(/\/$/, '') || 'https://cdn.example.com'
  if (operation.value === 'Directory') return `${base}/images/\n${base}/assets/`
  if (operation.value === 'Regex') return `${base}/images/.*`
  return `${base}/images/example.png\n${base}/assets/example.css`
})
const operationHint = computed(() => ({
  File: '清除指定文件的 CDN 缓存，用户下次访问时将从源站重新获取。',
  Directory: '刷新目录及其下的资源。目录地址必须以 / 结尾，不能带查询参数。',
  Regex: '通过 URL 中的指定模式匹配并刷新缓存；域名须固定，匹配模式仅用于域名后的路径或查询参数。',
  Preload: '将指定文件预先加载到 CDN 节点，仅支持文件地址。',
}[operation.value]))

async function loadConfig() {
  if (configLoading.value) return
  const controller = new AbortController()
  configController = controller
  configLoading.value = true
  configError.value = ''
  try {
    const data = await operationsApi.config(controller.signal)
    if (!active) return
    config.value = data
    if (operation.value !== 'Preload' && !data.refresh_types.includes(operation.value)) operation.value = data.refresh_types[0] ?? 'Preload'
  } catch {
    if (active && !controller.signal.aborted) configError.value = 'CDN 运维配置加载失败，请重试。'
  } finally {
    if (active) configLoading.value = false
    if (configController === controller) configController = null
  }
  if (active && config.value?.enabled) await loadTasks()
}

async function loadTasks(page = 1) {
  if (!available.value) return
  const request = ++taskRequest
  taskController?.abort()
  const controller = new AbortController()
  taskController = controller
  const taskId = queryTaskId.value.trim()
  if (taskId !== taskQuery.value) {
    taskItems.value = []
    taskTotal.value = 0
    taskPage.value = 1
    taskRequestId.value = ''
    taskQuery.value = taskId
  }
  taskLoading.value = true
  taskError.value = ''
  try {
    const data = await operationsApi.tasks(taskId, page, taskPageSize, controller.signal)
    if (!active || request !== taskRequest) return
    taskItems.value = data.items
    taskTotal.value = data.total
    taskPage.value = data.page
    taskQuery.value = taskId
    taskRequestId.value = data.request_id
  } catch {
    if (active && request === taskRequest && !controller.signal.aborted) taskError.value = '任务状态查询失败，请重试。'
  } finally {
    if (active && request === taskRequest) taskLoading.value = false
    if (taskController === controller) taskController = null
  }
}

async function submit() {
  if (!available.value || submitting.value || !config.value) return
  inputError.value = validateCdnUrls(urls.value, operation.value, config.value.limits)
  if (inputError.value) return
  submitting.value = true
  submitError.value = ''
  submission.value = null
  const selected = operation.value
  const submittedUrls = [...urls.value]
  try {
    const result = selected === 'Preload'
      ? await operationsApi.preload(submittedUrls)
      : await operationsApi.refresh(submittedUrls, selected)
    if (!active) return
    submission.value = result
    submittedOperation.value = operationLabels[selected]
    queryTaskId.value = submittedTaskIds.value[0] ?? ''
    await loadTasks()
  } catch (error) {
    if (active) {
      const failure = error as { message?: string; code?: number | string; response?: { data?: { message?: string } } }
      const serverMessage = failure?.response?.data?.message || (typeof failure?.code === 'number' ? failure.message : '')
      submitError.value = serverMessage
        ? `${serverMessage}。地址已保留。`
        : '提交结果未确认，任务可能已提交；地址已保留，请先查询最近任务，再决定是否重试。'
    }
  } finally {
    if (active) submitting.value = false
  }
}

function querySubmittedTask(taskId: string) {
  queryTaskId.value = taskId
  void loadTasks()
}

function changeTaskPage(page: number) {
  if (page === taskPage.value) return
  queryTaskId.value = taskQuery.value
  void loadTasks(page)
}

function taskType(value: string) {
  return ({ file: '文件刷新', directory: '目录刷新', regex: '正则刷新', preload: 'URL 预热' } as Record<string, string>)[value.toLowerCase()] || value || '未知'
}

function taskStatus(value: string) {
  return ({ Complete: '已完成', Refreshing: '执行中', Failed: '失败', Timeout: '已超时', Canceled: '已取消' } as Record<string, string>)[value] || value || '未知'
}

function taskTag(value: string): 'success' | 'warning' | 'danger' | 'info' {
  if (value === 'Complete') return 'success'
  if (value === 'Refreshing') return 'warning'
  if (value === 'Failed' || value === 'Timeout') return 'danger'
  return 'info'
}

function taskTime(value: string) {
  if (!value) return '未知'
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value.replace(' ', 'T')}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

watch([input, operation], () => { inputError.value = ''; submitError.value = '' }, { flush: 'sync' })
onMounted(() => { void loadConfig() })
onBeforeUnmount(() => {
  active = false
  taskRequest++
  configController?.abort()
  taskController?.abort()
})
</script>

<template>
  <div class="operations-page">
    <header class="page-heading">
      <h2>运维管理</h2>
      <p>API 请求记录与阿里云 CDN 缓存刷新、预热</p>
    </header>

    <el-tabs v-model="activeTab" class="operations-tabs">
      <el-tab-pane label="CDN 运维" name="cdn">
    <el-result v-if="configError" icon="error" title="配置加载失败" :sub-title="configError">
      <template #extra><el-button type="primary" :loading="configLoading" @click="loadConfig">重新加载</el-button></template>
    </el-result>
    <div v-else v-loading="configLoading">
      <el-alert v-if="config && !config.enabled" title="CDN 运维尚未启用" description="请在服务端配置阿里云 CDN 访问凭据后重新加载页面。" type="info" :closable="false" show-icon class="config-notice" />

      <section class="operation-panel" aria-labelledby="cdn-operation-heading">
        <h3 id="cdn-operation-heading">提交 CDN 任务</h3>
        <p v-if="config?.cdn_base_url" class="field-hint">当前静态资源地址：<span class="cdn-address">{{ config.cdn_base_url }}</span></p>
        <el-form label-position="top" :disabled="!available || submitting" @submit.prevent="submit">
          <el-form-item label="操作类型">
            <el-radio-group v-model="operation" aria-label="CDN 操作类型" class="operation-options">
              <el-radio-button v-for="item in operations" :key="item" :value="item">{{ operationLabels[item] }}</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <p class="operation-hint">{{ operationHint }}</p>
          <el-form-item label="URL 地址" :error="inputError">
            <el-input v-model="input" type="textarea" :rows="7" :placeholder="placeholder" aria-label="CDN URL 地址，每行一条" />
          </el-form-item>
          <div class="input-notes">
            <span>每行一条，空行与重复地址会自动合并。每次最多 10 个 CDN 域名。</span>
            <span v-if="config">{{ urls.length }} / {{ limit }} 条；每条最多 {{ config.limits.max_url_length }} 字符</span>
          </div>
          <p v-if="operation === 'Regex'" class="field-hint">阿里云 CDN 支持 <code>[0-9]</code>、<code>[a-z]</code>、<code>[^/]*</code> 和 <code>.*</code> 四种匹配模式。示例：<code>https://cdn.example.com/images/.*</code>。</p>
          <div v-if="submitError" role="alert" class="error-message">{{ submitError }}</div>
          <el-button type="primary" native-type="submit" :loading="submitting" :disabled="!available">提交{{ operationLabels[operation] }}</el-button>
        </el-form>
      </section>

      <section v-if="submission" class="submission-result" role="status" aria-label="CDN 任务提交结果">
        <el-alert :title="`${submittedOperation}已提交，任务将由 CDN 异步执行。`" type="success" :closable="false" show-icon />
        <p>任务编号：<code>{{ submission.task_id }}</code></p>
        <p class="field-hint">请求编号：<code>{{ submission.request_id }}</code></p>
        <div v-if="submittedTaskIds.length > 1" class="submitted-tasks">
          <span>查看本次任务：</span>
          <el-button v-for="taskId in submittedTaskIds" :key="taskId" size="small" :disabled="taskLoading" @click="querySubmittedTask(taskId)">{{ taskId }}</el-button>
        </div>
      </section>

      <section class="operation-panel tasks-panel" aria-labelledby="cdn-tasks-heading">
        <div class="section-heading">
          <h3 id="cdn-tasks-heading">任务状态</h3>
          <span class="field-hint">可查询近 3 天的任务 · 时间为北京时间</span>
        </div>
        <form class="task-query" @submit.prevent="loadTasks()">
          <el-input v-model="queryTaskId" placeholder="任务编号（留空查询最近任务）" aria-label="CDN 任务编号" clearable :disabled="!available || submitting" />
          <el-button type="primary" native-type="submit" :loading="taskLoading" :disabled="!available || submitting">查询状态</el-button>
        </form>
        <p v-if="taskError" role="alert" class="error-message">{{ taskError }}</p>
        <el-table :data="taskItems" v-loading="taskLoading" stripe :empty-text="taskQuery ? '暂未查询到此任务，提交后可稍后重试' : '暂无最近任务'">
          <el-table-column prop="task_id" label="任务编号" min-width="150" />
          <el-table-column label="操作" width="120"><template #default="{ row }">{{ taskType(row.object_type) }}</template></el-table-column>
          <el-table-column prop="object_path" label="URL 地址" min-width="280" show-overflow-tooltip />
          <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="taskTag(row.status)" size="small">{{ taskStatus(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="进度" width="90"><template #default="{ row }">{{ row.process || '—' }}</template></el-table-column>
          <el-table-column label="创建时间" width="185"><template #default="{ row }">{{ taskTime(row.creation_time) }}</template></el-table-column>
          <el-table-column label="说明" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.description || '—' }}</template></el-table-column>
        </el-table>
        <el-pagination v-if="taskTotal > taskPageSize" :current-page="taskPage" :page-size="taskPageSize" :total="taskTotal" layout="prev, pager, next" class="pagination" @current-change="changeTaskPage" />
        <p v-if="taskRequestId" class="field-hint request-id">查询请求编号：<code>{{ taskRequestId }}</code></p>
      </section>
    </div>
      </el-tab-pane>
      <el-tab-pane label="API 请求记录" name="requests" lazy>
        <ApiRequestLogs />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.operations-page { max-width: 1400px; }
.page-heading { margin-bottom: 24px; }
.page-heading h2 { margin: 0 0 8px; }
.page-heading p, .field-hint, .input-notes { color: var(--el-text-color-secondary); font-size: 13px; }
.page-heading p { margin: 0; }
.operations-tabs { --el-tabs-header-height: 46px; }
.operation-panel { padding: 24px; margin-bottom: 24px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--app-surface); }
.operation-panel h3 { margin: 0 0 20px; font-size: 17px; }
.operation-panel > .field-hint { margin: -8px 0 20px; }
.config-notice { margin-bottom: 20px; }
.cdn-address, code { overflow-wrap: anywhere; }
.operation-options { display: flex; flex-wrap: wrap; }
.operation-hint { margin: -6px 0 20px; color: var(--el-text-color-regular); font-size: 14px; line-height: 1.6; }
.input-notes { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; margin: -5px 0 20px; line-height: 1.6; }
.error-message { margin: 12px 0; color: var(--el-color-danger); font-size: 14px; }
.submission-result { margin-bottom: 24px; padding: 20px; border: 1px solid var(--el-color-success-light-5); border-radius: 8px; background: var(--app-surface); }
.submission-result p { margin: 14px 0 0; font-size: 14px; }
.submission-result .field-hint { font-size: 13px; }
.submitted-tasks { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 16px; font-size: 13px; }
.submitted-tasks .el-button + .el-button { margin-left: 0; }
.section-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 20px; }
.section-heading h3 { margin: 0; }
.task-query { display: flex; gap: 12px; margin-bottom: 20px; max-width: 600px; }
.pagination { justify-content: center; margin-top: 20px; }
.request-id { margin-top: 14px; margin-bottom: 0; }
@media (max-width: 700px) {
  .operation-panel { padding: 18px 14px; }
  .task-query { gap: 8px; }
  .submission-result { padding: 14px; }
}
</style>
