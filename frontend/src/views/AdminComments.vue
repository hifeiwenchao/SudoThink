<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
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
  if (actingId.value !== null || loading.value || disposed) return
  actingId.value = cid
  actionError.value = ''
  try {
    await http.post(`/comments/${cid}/${action}`)
    if (disposed) return
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

function changePage(value: number) {
  if (value === page.value) return
  page.value = value
  void load()
}

function publicArticleUrl(id: number) {
  return new URL(`/articles/${id}`, PUBLIC_SITE_URL).href
}

watch([articleId, status], () => {
  page.value = 1
  list.value = []
  total.value = 0
  actionError.value = ''
  void load()
})

onMounted(() => {
  void load()
  void searchArticles('')
})
onBeforeUnmount(() => {
  disposed = true
  listRequest++
  articleRequest++
})
</script>

<template>
  <div>
    <h2>评论管理</h2>

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

    <el-table v-else :data="list" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
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
          <div class="content">{{ row.content }}</div>
        </template>
      </el-table-column>
      <el-table-column label="邮箱（不公开）" min-width="190">
        <template #default="{ row }">{{ row.email || '未填写' }}</template>
      </el-table-column>
      <el-table-column label="IP 地址（不公开）" min-width="160">
        <template #default="{ row }">{{ row.ip_address || '未知' }}</template>
      </el-table-column>
      <el-table-column label="IP 详细地址" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ row.location_detail || row.location || '未知' }}</template>
      </el-table-column>
      <el-table-column label="User-Agent（不公开）" width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ row.user_agent || '未记录' }}</template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'approved'"
            size="small"
            type="success"
            :loading="actingId === row.id"
            :disabled="actingId !== null || loading"
            @click="handleApprove(row.id)"
          >通过</el-button>
          <el-button
            v-if="row.status !== 'rejected'"
            size="small"
            type="danger"
            :loading="actingId === row.id"
            :disabled="actingId !== null || loading"
            @click="handleReject(row.id)"
          >驳回</el-button>
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
  </div>
</template>

<style scoped>
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
