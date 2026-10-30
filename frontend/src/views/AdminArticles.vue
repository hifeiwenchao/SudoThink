<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type AdminArticleBrief } from '@/api/admin'

const list = ref<AdminArticleBrief[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const keyword = ref('')

async function load() {
  loading.value = true
  try {
    const data = await adminApi.listArticles(page.value, 10, keyword.value || undefined)
    list.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function handleRemove(aid: number) {
  await ElMessageBox.confirm('确定删除该文章？（不可恢复）', '警告', { type: 'warning' })
  await adminApi.removeArticle(aid)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2>文章管理</h2>

    <el-input
      v-model="keyword"
      placeholder="搜索标题"
      clearable
      style="margin-bottom: 12px; max-width: 400px"
      @keyup.enter="load"
    >
      <template #append><el-button @click="load">搜索</el-button></template>
    </el-input>

    <el-table :data="list" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column label="作者" width="120">
        <template #default="{ row }">{{ row.author.username }}</template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_published ? 'success' : 'info'" size="small">
            {{ row.is_published ? '已发布' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="view_count" label="阅读" width="80" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="handleRemove(row.id)">
            删除
          </el-button>
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
.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
