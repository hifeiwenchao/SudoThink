<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type PendingComment } from '@/api/admin'
import http from '@/api/http'

const list = ref<PendingComment[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await adminApi.pendingComments(page.value)
    list.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function handleApprove(cid: number) {
  await http.post(`/comments/${cid}/approve`)
  ElMessage.success('已通过')
  load()
}

async function handleReject(cid: number) {
  await http.post(`/comments/${cid}/reject`)
  ElMessage.success('已驳回')
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2>评论审核</h2>

    <el-empty v-if="!loading && !list.length" description="暂无待审核评论" />

    <el-table :data="list" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="文章" min-width="150">
        <template #default="{ row }">
          <RouterLink :to="`/articles/${row.article.id}`" target="_blank">
            {{ row.article.title }}
          </RouterLink>
        </template>
      </el-table-column>
      <el-table-column label="作者" width="120">
        <template #default="{ row }">
          {{ row.author.nickname || row.author.username }}
        </template>
      </el-table-column>
      <el-table-column label="评论内容" min-width="200">
        <template #default="{ row }">
          <div class="content">{{ row.content }}</div>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" type="success" @click="handleApprove(row.id)">
            通过
          </el-button>
          <el-button size="small" type="danger" @click="handleReject(row.id)">
            驳回
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
.content {
  white-space: pre-wrap;
  color: #606266;
}
</style>
