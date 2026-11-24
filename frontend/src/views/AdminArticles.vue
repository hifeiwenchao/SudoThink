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
      <h2>文章管理</h2>
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
    <div v-if="loadError" role="alert"><p>文章列表加载失败，请稍后重试。</p><el-button @click="load">重新加载</el-button></div>
    <el-table v-else :data="list" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column label="作者" width="120">
        <template #default="{ row }">{{ row.author.username }}</template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_published ? 'success' : 'info'" size="small">
            {{ row.deleted_at ? '回收站' : row.is_published ? '已发布' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="view_count" label="阅读" width="80" />
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button v-if="status !== 'trash'" size="small" :disabled="actingId !== null" @click="$router.push(`/articles/${row.id}/edit`)">编辑</el-button>
          <el-button v-if="status !== 'trash'" size="small" type="danger" :loading="actingId === row.id" :disabled="actingId !== null" @click="handleRemove(row.id)">
            移至回收站
          </el-button>
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
.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
