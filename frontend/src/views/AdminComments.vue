<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type AdminArticleBrief, type AdminComment, type CommentFilters, type CommentStatus } from '@/api/admin'
import http from '@/api/http'
import { PUBLIC_SITE_URL } from '@/site'

const pageSize = 10
const list = ref<AdminComment[]>([])
const total = ref(0)
const page = ref(1)
const articleId = ref(0)
const status = ref<CommentStatus>('all')
const loading = ref(false)
const error = ref('')
const actingId = ref<number | null>(null)
const selectedIds = ref<number[]>([])
const batchBusy = ref(false)
const detailVisible = ref(false)
const detailComment = ref<AdminComment | null>(null)
function openDetails(comment: AdminComment) { detailComment.value = comment; detailVisible.value = true }
function updateReviewedDetails(ids: number[], action: 'approve' | 'reject') {
  if (!detailComment.value || !ids.includes(detailComment.value.id)) return
  detailComment.value = { ...detailComment.value, status: action === 'approve' ? 'approved' : 'rejected', is_approved: action === 'approve' }
}
const mobile = ref(window.innerWidth <= 700)
function updateViewport() { mobile.value = window.innerWidth <= 700 }
function toggleSelected(id: number, selected: boolean) {
  if (batchBusy.value || loading.value || actingId.value !== null) return
  selectedIds.value = selected ? [...new Set([...selectedIds.value, id])] : selectedIds.value.filter(value => value !== id)
}
function selectPage(selected: boolean) {
  if (batchBusy.value || loading.value || actingId.value !== null) return
  selectedIds.value = selected ? list.value.map(item => item.id) : []
}
watch(mobile, () => { selectedIds.value = [] })
const actionError = ref('')
const articleOptions = ref<AdminArticleBrief[]>([])
const articlesLoading = ref(false)
const articleError = ref('')
const articleQuery = ref('')
let listRequest = 0
let articleRequest = 0
let disposed = false

const statusLabels = { pending: '待审核', approved: '已通过', rejected: '已驳回' } as const
const statusTags = { pending: 'warning', approved: 'success', rejected: 'danger' } as const

async function load() {
  if (disposed) return
  const request = ++listRequest
  const requestedPage = page.value
  const filters: CommentFilters = {}
  if (articleId.value) filters.article_id = articleId.value
  if (status.value !== 'all') filters.status = status.value
  loading.value = true
  error.value = ''
  try {
    const data = await adminApi.listComments(requestedPage, pageSize, filters)
    if (request !== listRequest) return
    const lastPage = Math.max(1, Math.ceil(data.total / pageSize))
    if (requestedPage > lastPage) {
      page.value = lastPage
      await load()
      return
    }
    list.value = data.items
    selectedIds.value = selectedIds.value.filter(id => data.items.some(item => item.id === id))
    total.value = data.total
  } catch {
    if (request !== listRequest) return
    list.value = []
    total.value = 0
    error.value = '评论加载失败，请重试'
  } finally {
    if (request === listRequest) loading.value = false
  }
}

async function searchArticles(query: string) {
  if (disposed) return
  const request = ++articleRequest
  articleQuery.value = query.trim()
  articlesLoading.value = true
  articleError.value = ''
  try {
    const data = await adminApi.listArticles(1, 100, articleQuery.value || undefined)
    if (request === articleRequest) articleOptions.value = data.items
  } catch {
    if (request !== articleRequest) return
    articleOptions.value = []
    articleError.value = '文章选项加载失败'
  } finally {
    if (request === articleRequest) articlesLoading.value = false
  }
}

async function reviewComment(cid: number, action: 'approve' | 'reject') {
  if (actingId.value !== null || batchBusy.value || loading.value || disposed) return
  actingId.value = cid
  actionError.value = ''
  try {
    await http.post(`/comments/${cid}/${action}`)
    if (disposed) return
    updateReviewedDetails([cid], action)
    ElMessage.success(action === 'approve' ? '已通过' : '已驳回')
    await load()
  } catch {
    if (!disposed) actionError.value = '评论审核失败，请重试'
  } finally {
    actingId.value = null
  }
}

function handleApprove(cid: number) {
  return reviewComment(cid, 'approve')
}

function handleReject(cid: number) {
  return reviewComment(cid, 'reject')
}

async function reviewBatch(action: 'approve' | 'reject') {
  if (batchBusy.value || actingId.value !== null || loading.value || disposed) return
  const ids = selectedIds.value.filter(id => list.value.some(item => item.id === id))
  if (!ids.length) return
  const context = listRequest
  batchBusy.value = true
  actionError.value = ''
  try {
    try {
      await ElMessageBox.confirm(`确定${action === 'approve' ? '通过' : '驳回'}选中的 ${ids.length} 条评论？`, '批量审核', {
        confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning',
      })
    } catch { return }
    if (disposed || context !== listRequest) return
    await adminApi.batchReviewComments(ids, action)
    if (disposed) return
    updateReviewedDetails(ids, action)
    if (context === listRequest) selectedIds.value = []
    ElMessage.success(`已${action === 'approve' ? '通过' : '驳回'} ${ids.length} 条评论`)
    await load()
  } catch {
    if (!disposed && context === listRequest) actionError.value = '批量审核失败，已保留选择，请重试'
  } finally { batchBusy.value = false }
}

function changePage(value: number) {
  if (value === page.value) return
  page.value = value
  selectedIds.value = []
  void load()
}

function publicArticleUrl(id: number) {
  return new URL(`/articles/${id}`, PUBLIC_SITE_URL).href
}

watch([articleId, status], () => {
  selectedIds.value = []
  page.value = 1
  list.value = []
  total.value = 0
  actionError.value = ''
  void load()
})

onMounted(() => {
  window.addEventListener('resize', updateViewport)
  void load()
  void searchArticles('')
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
  disposed = true
  listRequest++
  articleRequest++
})
</script>

<template>
  <div>
    <header class="page-heading"><div><h2>评论管理</h2><p>让讨论保持有序，审核后再向读者公开。</p></div><span class="total-count">共 {{ total }} 条评论</span></header>

    <div class="filters">
      <el-select
        v-model="articleId"
        filterable
        remote
        clearable
        :empty-values="[0, undefined, null]"
        :value-on-clear="0"
        :remote-method="searchArticles"
        :loading="articlesLoading"
        placeholder="所有文章"
        aria-label="按文章筛选"
        class="article-filter"
      >
        <el-option label="所有文章" :value="0" />
        <el-option
          v-for="article in articleOptions"
          :key="article.id"
          :label="article.title + (article.is_published ? '' : '（草稿）')"
          :value="article.id"
        />
      </el-select>
      <el-select v-model="status" aria-label="按评论状态筛选" class="status-filter">
        <el-option label="全部状态" value="all" />
        <el-option label="待审核" value="pending" />
        <el-option label="已通过" value="approved" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
    </div>
    <div v-if="articleError" class="error-message" role="alert">
      {{ articleError }}
      <el-button text @click="searchArticles(articleQuery)">重试文章搜索</el-button>
    </div>
    <div v-if="actionError" class="error-message" role="alert">{{ actionError }}</div>
    <div v-if="error" class="error-message" role="alert">
      {{ error }}
      <el-button @click="load">重试</el-button>
    </div>
    <el-empty v-else-if="!loading && !list.length" description="暂无符合条件的评论" />

    <div v-if="loading && !list.length" class="admin-initial-loading" role="status" aria-label="评论加载中"><p>正在读取评论…</p><el-skeleton :rows="5" animated /></div>
    <div v-if="list.length" class="batch-actions">
      <span>已选 {{ selectedIds.length }} 条（当前页）</span>
      <el-button :disabled="!selectedIds.length || loading || actingId !== null || batchBusy" :loading="batchBusy" type="success" @click="reviewBatch('approve')">批量通过</el-button>
      <el-button :disabled="!selectedIds.length || loading || actingId !== null || batchBusy" type="danger" @click="reviewBatch('reject')">批量驳回</el-button>
    </div>
    <div v-if="mobile && list.length" class="comment-cards" v-loading="loading">
      <article v-for="row in list" :key="row.id" class="comment-card">
        <div class="card-heading">
          <el-checkbox :model-value="selectedIds.includes(row.id)" :disabled="batchBusy || loading || actingId !== null" :aria-label="`选择评论 ${row.id}`" @change="toggleSelected(row.id, !!$event)" />
          <strong>{{ row.nickname || row.author?.nickname || row.author?.username || '访客' }}</strong>
          <el-tag :type="statusTags[row.status]" size="small">{{ statusLabels[row.status] }}</el-tag>
        </div>
        <p class="content card-content">{{ row.content }}</p>
        <a v-if="row.article.is_published" :href="publicArticleUrl(row.article.id)" target="_blank" rel="noopener noreferrer">{{ row.article.title }}</a>
        <span v-else>{{ row.article.title }}（草稿）</span>
        <p><small>{{ new Date(row.created_at).toLocaleString() }}</small></p>
        <div class="card-actions">
          <el-button v-if="row.status !== 'approved'" size="small" type="success" :disabled="actingId !== null || batchBusy || loading" @click="handleApprove(row.id)">通过</el-button>
          <el-button v-if="row.status !== 'rejected'" size="small" type="danger" :disabled="actingId !== null || batchBusy || loading" @click="handleReject(row.id)">驳回</el-button>
          <el-button size="small" :aria-label="`查看评论 ${row.id} 详情`" @click="openDetails(row)">更多</el-button>
        </div>
      </article>
    </div>
    <el-table v-else-if="!error && list.length" :data="list" v-loading="loading" stripe row-key="id">
      <el-table-column width="44">
        <template #header>
          <el-checkbox :model-value="list.length > 0 && selectedIds.length === list.length" :indeterminate="selectedIds.length > 0 && selectedIds.length < list.length" :disabled="batchBusy || loading || actingId !== null" aria-label="选择当前页全部评论" @change="selectPage(!!$event)" />
        </template>
        <template #default="{ row }">
          <el-checkbox :model-value="selectedIds.includes(row.id)" :disabled="batchBusy || loading || actingId !== null" :aria-label="`选择评论 ${row.id}`" @change="toggleSelected(row.id, !!$event)" />
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTags[row.status as AdminComment['status']]" size="small">
            {{ statusLabels[row.status as AdminComment['status']] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="文章" min-width="170">
        <template #default="{ row }">
          <a v-if="row.article.is_published" :href="publicArticleUrl(row.article.id)" target="_blank" rel="noopener noreferrer">
            {{ row.article.title }}
          </a>
          <template v-else>{{ row.article.title }} <el-tag type="info" size="small">草稿</el-tag></template>
        </template>
      </el-table-column>
      <el-table-column label="昵称" min-width="120">
        <template #default="{ row }">
          {{ row.nickname || row.author?.nickname || row.author?.username || '访客' }}
        </template>
      </el-table-column>
      <el-table-column label="评论内容" min-width="220">
        <template #default="{ row }">
          <div class="content table-content">{{ row.content }}</div>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'approved'"
            size="small"
            type="success"
            :loading="actingId === row.id"
            :disabled="actingId !== null || batchBusy || loading"
            @click="handleApprove(row.id)"
          >通过</el-button>
          <el-button
            v-if="row.status !== 'rejected'"
            size="small"
            type="danger"
            :loading="actingId === row.id"
            :disabled="actingId !== null || batchBusy || loading"
            @click="handleReject(row.id)"
          >驳回</el-button>
          <el-button size="small" :aria-label="`查看评论 ${row.id} 详情`" @click="openDetails(row)">更多</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next"
      class="pagination"
      @current-change="changePage"
    />
    <el-drawer v-model="detailVisible" title="评论详情" class="comment-detail-drawer" size="min(500px, 100vw)" append-to-body destroy-on-close>
      <template v-if="detailComment">
        <div class="detail-heading"><el-tag :type="statusTags[detailComment.status]">{{ statusLabels[detailComment.status] }}</el-tag><span>#{{ detailComment.id }}</span></div>
        <h3>{{ detailComment.nickname || detailComment.author?.nickname || detailComment.author?.username || '访客' }}</h3>
        <p class="content detail-content">{{ detailComment.content }}</p>
        <dl class="detail-list">
          <div><dt>文章</dt><dd>{{ detailComment.article.title }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ new Date(detailComment.created_at).toLocaleString() }}</dd></div>
          <div><dt>邮箱（不公开）</dt><dd>{{ detailComment.email || '未填写' }}</dd></div>
          <div><dt>IP（不公开）</dt><dd>{{ detailComment.ip_address || '未知' }}</dd></div>
          <div><dt>地理位置</dt><dd>{{ detailComment.location_detail || detailComment.location || '未知' }}</dd></div>
          <div><dt>User-Agent</dt><dd>{{ detailComment.user_agent || '未记录' }}</dd></div>
        </dl>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.page-heading h2 { margin: 0; }
.page-heading p { margin: 8px 0 0; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.7; }
.total-count { flex-shrink: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.table-content { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.7; }
.detail-heading { display: flex; justify-content: space-between; align-items: center; color: var(--el-text-color-secondary); }
.detail-content { line-height: 1.9; padding-bottom: 20px; border-bottom: 1px solid var(--el-border-color-lighter); }
.detail-list { display: grid; gap: 20px; }
.detail-list dt { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.detail-list dd { margin: 0; line-height: 1.7; overflow-wrap: anywhere; font-size: 14px; }
@media (max-width: 700px) { .page-heading { align-items: flex-start; }.total-count { padding-top: 7px; } }
.batch-actions, .card-heading, .card-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.batch-actions :deep(.el-button + .el-button), .card-actions :deep(.el-button + .el-button) { margin-left: 0; }
.comment-cards { display: grid; gap: 12px; }
.comment-card { min-width: 0; padding: 14px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; overflow-wrap: anywhere; }
.card-content { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.article-filter {
  width: 320px;
  max-width: 100%;
}
.status-filter {
  width: 150px;
}
.error-message {
  margin: 12px 0;
  color: var(--el-color-danger);
}
.pagination {
  margin-top: 16px;
  justify-content: center;
}
.content {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--el-text-color-regular);
}
</style>
