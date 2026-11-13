<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { requestLogsApi, type ApiRequestLog, type RequestLogFilters } from '@/api/requestLogs'

const pageSize = 20
const items = ref<ApiRequestLog[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const filterError = ref('')
const urlFilter = ref('')
const methodFilter = ref('')
const statusCodeFilter = ref('')
const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
let filters: RequestLogFilters = {}
let requestNumber = 0
let controller: AbortController | null = null
let disposed = false

async function load(nextPage = page.value) {
  if (disposed) return
  const request = ++requestNumber
  controller?.abort()
  const currentController = new AbortController()
  controller = currentController
  page.value = nextPage
  loading.value = true
  error.value = ''
  try {
    const data = await requestLogsApi.list(nextPage, pageSize, filters, currentController.signal)
    if (disposed || request !== requestNumber) return
    const lastPage = Math.max(1, Math.ceil(data.total / pageSize))
    if (nextPage > lastPage) {
      await load(lastPage)
      return
    }
    items.value = data.items
    total.value = data.total
    page.value = data.page
  } catch {
    if (disposed || request !== requestNumber || currentController.signal.aborted) return
    items.value = []
    total.value = 0
    error.value = '请求记录加载失败，请重试。'
  } finally {
    if (!disposed && request === requestNumber) loading.value = false
    if (controller === currentController) controller = null
  }
}

async function applyFilters() {
  const statusCode = statusCodeFilter.value.trim()
  if (statusCode && !/^[1-5]\d{2}$/.test(statusCode)) {
    filterError.value = '状态码须为 100–599 的三位整数'
    return
  }
  filterError.value = ''
  filters = {}
  if (urlFilter.value.trim()) filters.url = urlFilter.value.trim()
  if (methodFilter.value) filters.method = methodFilter.value
  if (statusCode) filters.status_code = Number(statusCode)
  items.value = []
  total.value = 0
  await load(1)
}

async function resetFilters() {
  urlFilter.value = ''
  methodFilter.value = ''
  statusCodeFilter.value = ''
  await applyFilters()
}

function changePage(value: number) {
  if (value !== page.value) void load(value)
}

function statusTag(status: number) {
  if (status >= 400) return 'danger'
  if (status >= 300) return 'warning'
  return status >= 200 ? 'success' : 'info'
}

function time(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

function hasParams(value: Record<string, unknown>) {
  return Object.keys(value).length > 0
}

function json(value: unknown) {
  return JSON.stringify(value, null, 2)
}

onMounted(() => { void load() })
onBeforeUnmount(() => {
  disposed = true
  requestNumber++
  controller?.abort()
})
</script>

<template>
  <section class="request-logs" aria-labelledby="request-logs-heading">
    <div class="section-heading">
      <div>
        <h3 id="request-logs-heading">API 请求记录</h3>
        <p class="field-hint">展开记录查看请求参数 · 时间为北京时间</p>
      </div>
      <el-button :loading="loading" @click="load()">刷新记录</el-button>
    </div>

    <el-form label-position="top" class="request-filters" @submit.prevent="applyFilters">
      <el-form-item label="URL 包含" class="url-filter">
        <el-input v-model="urlFilter" placeholder="例如 /api/articles/42" aria-label="按 URL 包含内容筛选" clearable />
      </el-form-item>
      <el-form-item label="请求方法" class="method-filter">
        <el-select v-model="methodFilter" placeholder="全部方法" aria-label="按请求方法筛选">
          <el-option label="全部方法" value="" />
          <el-option v-for="method in methods" :key="method" :label="method" :value="method" />
        </el-select>
      </el-form-item>
      <el-form-item label="HTTP 状态码" :error="filterError" class="status-filter">
        <el-input v-model="statusCodeFilter" placeholder="例如 200" aria-label="按 HTTP 状态码筛选" inputmode="numeric" maxlength="3" clearable />
      </el-form-item>
      <div class="filter-actions">
        <el-button type="primary" native-type="submit">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </el-form>

    <div v-if="error" role="alert" class="error-message">
      {{ error }}
      <el-button :loading="loading" @click="load()">重试</el-button>
    </div>
    <el-table :data="items" row-key="id" v-loading="loading" stripe empty-text="暂无符合条件的请求记录">
      <el-table-column type="expand" width="48">
        <template #default="{ row }">
          <div class="request-details">
            <div class="request-meta">
              <p><span>请求 ID：</span>{{ row.id }}</p>
              <p><span>完整 URL：</span><code>{{ row.url }}</code></p>
              <p><span>路径：</span><code>{{ row.path }}</code></p>
            </div>
            <div class="parameter-grid">
              <section class="parameter-block">
                <h4>查询参数</h4>
                <pre v-if="hasParams(row.query_params)">{{ json(row.query_params) }}</pre>
                <p v-else class="field-hint">无查询参数</p>
              </section>
              <section class="parameter-block">
                <h4>路径参数</h4>
                <pre v-if="hasParams(row.path_params)">{{ json(row.path_params) }}</pre>
                <p v-else class="field-hint">无路径参数</p>
              </section>
              <section class="parameter-block">
                <h4>请求体</h4>
                <pre v-if="row.body_params !== null">{{ json(row.body_params) }}</pre>
                <p v-else class="field-hint">无请求体</p>
              </section>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="请求时间" width="185"><template #default="{ row }">{{ time(row.created_at) }}</template></el-table-column>
      <el-table-column prop="method" label="方法" width="90" />
      <el-table-column prop="url" label="URL" min-width="280" show-overflow-tooltip />
      <el-table-column label="状态码" width="90"><template #default="{ row }"><el-tag :type="statusTag(row.status_code)" size="small">{{ row.status_code }}</el-tag></template></el-table-column>
      <el-table-column label="耗时" width="100"><template #default="{ row }">{{ row.duration_ms }} ms</template></el-table-column>
    </el-table>
    <div class="list-footer">
      <span class="field-hint">共 {{ total }} 条记录</span>
      <el-pagination v-if="total > pageSize" :current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" :pager-count="5" @current-change="changePage" />
    </div>
  </section>
</template>

<style scoped>
.request-logs { padding: 24px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--app-surface); }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.section-heading h3 { margin: 0 0 8px; font-size: 17px; }
.field-hint { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; }
.request-filters { display: flex; align-items: flex-start; flex-wrap: wrap; gap: 0 12px; margin-bottom: 6px; }
.url-filter { flex: 1 1 260px; }
.method-filter { width: 135px; }
.status-filter { width: 145px; }
.filter-actions { display: flex; padding-top: 30px; margin-bottom: 18px; }
.error-message { display: flex; align-items: center; gap: 12px; margin: 14px 0; color: var(--el-color-danger); font-size: 14px; }
.list-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-top: 20px; }
.request-details { padding: 18px 24px; background: var(--el-fill-color-lighter); }
.request-meta { margin-bottom: 16px; }
.request-meta p { margin: 0 0 8px; overflow-wrap: anywhere; line-height: 1.6; }
.request-meta span { color: var(--el-text-color-secondary); }
.parameter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.parameter-block { min-width: 0; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--app-surface); }
.parameter-block h4 { margin: 0; padding: 12px; border-bottom: 1px solid var(--el-border-color-light); font-size: 13px; }
.parameter-block pre { max-height: 360px; margin: 0; padding: 12px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.6; color: var(--el-text-color-regular); }
.parameter-block > p { padding: 12px; }
@media (max-width: 900px) { .parameter-grid { grid-template-columns: 1fr; } }
@media (max-width: 700px) {
  .request-logs { padding: 18px 14px; }
  .url-filter { flex-basis: 100%; }
  .method-filter, .status-filter { flex: 1 1 130px; }
  .filter-actions { padding-top: 0; }
  .request-details { padding: 14px; }
}
</style>
