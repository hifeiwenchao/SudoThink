<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type AdminArticleBrief, type AdminArticleStatus } from '@/api/admin'

const list = ref<AdminArticleBrief[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loadError = ref(false)
const keyword = ref('')
const query = ref('')
const status = ref<AdminArticleStatus>('all')
const actingId = ref<number | null>(null)
let requestId = 0
async function load() {
  const request = ++requestId
  loading.value = true
  loadError.value = false
  try {
    const data = await adminApi.listArticles(page.value, 10, query.value || undefined, status.value)
    if (request !== requestId) return
    if (!data.items.length && page.value > 1) {
      page.value = Math.max(1, Math.ceil(data.total / 10))
      await load()
      return
    }
    list.value = data.items
    total.value = data.total
  } catch {
    if (request === requestId) loadError.value = true
  } finally {
    if (request === requestId) loading.value = false
  }
}
function search() { query.value = keyword.value.trim(); page.value = 1; void load() }
watch(status, () => { page.value = 1; void load() })
async function handleRemove(aid: number) {
  if (actingId.value !== null) return
  actingId.value = aid
  try {
    await ElMessageBox.confirm('将文章移至回收站？文章内容和评论将保留，可随时恢复。', '移至回收站', { type: 'warning' })
    await adminApi.removeArticle(aid)
    ElMessage.success('已移至回收站')
    await load()
  } catch { /* Cancellation and HTTP failures leave the list available. */ }
  finally { actingId.value = null }
}
async function handleRestore(aid: number) {
  if (actingId.value !== null) return
  actingId.value = aid
  try {
    await adminApi.restoreArticle(aid)
    ElMessage.success('已恢复文章，保留原发布状态')
    await load()
  } catch { /* HTTP interceptor displays the operation failure. */ }
  finally { actingId.value = null }
}
onMounted(load)
onBeforeUnmount(() => { requestId++ })
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>文章管理</h2><p class="admin-description">管理已发布内容和草稿，移入回收站的文章可随时恢复。</p></div>
      <el-button type="primary" @click="$router.push('/articles/new')">新建文章</el-button>
    </div>

    <el-input
      v-model="keyword"
      placeholder="搜索标题"
      clearable
      style="margin-bottom: 12px; max-width: 400px"
      @keyup.enter="search"
      @clear="search"
    >
      <template #append><el-button @click="search">搜索</el-button></template>
    </el-input>

    <el-radio-group v-model="status" aria-label="文章状态" style="margin-bottom: 16px; display: flex; flex-wrap: wrap">
      <el-radio-button value="all">全部文章</el-radio-button>
      <el-radio-button value="published">已发布</el-radio-button>
      <el-radio-button value="draft">草稿</el-radio-button>
      <el-radio-button value="trash">回收站</el-radio-button>
    </el-radio-group>
    <p v-if="status === 'trash'">回收站保留文章内容及评论，恢复后沿用原发布状态。</p>
    <div v-if="loadError" class="admin-feedback" role="alert"><span>文章列表加载失败，请稍后重试。</span><el-button @click="load">重新加载</el-button></div>
    <div v-else-if="loading && !list.length" class="admin-initial-loading" role="status" aria-label="文章加载中"><p>正在读取文章…</p><el-skeleton :rows="5" animated /></div>
    <el-empty v-else-if="!list.length" :description="query ? '没有找到匹配的文章，试试其他关键词' : status === 'trash' ? '回收站为空' : '这里还没有文章，开始记录一个想法吧'">
      <el-button v-if="status !== 'trash' && !query" type="primary" @click="$router.push('/articles/new')">创作第一篇文章</el-button>
    </el-empty>
    <el-table v-else :data="list" v-loading="loading" row-key="id">
      <el-table-column label="文章" min-width="220">
        <template #default="{ row }"><strong class="article-title">{{ row.title }}</strong><p class="article-meta">{{ row.author.username }} · #{{ row.id }}</p></template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_published ? 'success' : 'info'" size="small">
            {{ row.deleted_at ? '回收站' : row.is_published ? '已发布' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="view_count" label="阅读" width="80" />
      <el-table-column label="操作" width="154" align="right">
        <template #default="{ row }">
          <el-button v-if="status !== 'trash'" size="small" :disabled="actingId !== null" @click="$router.push(`/articles/${row.id}/edit`)">编辑</el-button>
          <el-dropdown v-if="status !== 'trash'" :disabled="actingId !== null" trigger="click" @command="handleRemove(row.id)">
            <el-button class="more-action" size="small" :loading="actingId === row.id" :disabled="actingId !== null" :aria-label="`文章 ${row.title} 的更多操作`">更多</el-button>
            <template #dropdown><el-dropdown-menu><el-dropdown-item command="trash">移至回收站</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
          <el-button v-if="status === 'trash'" size="small" type="primary" :loading="actingId === row.id" :disabled="actingId !== null" @click="handleRestore(row.id)">恢复</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > 10"
      v-model:current-page="page"
      :page-size="10"
      :total="total"
      layout="prev, pager, next"
      class="pagination"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.page-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}
.page-heading h2 { margin: 0; }
.article-title { font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.article-meta { margin: 5px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.more-action { margin-left: 6px; }
.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
