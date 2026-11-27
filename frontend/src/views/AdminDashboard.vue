<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminApi, type DashboardResp } from '@/api/admin'

const stats = ref<DashboardResp | null>(null)
const loading = ref(false)
const loadError = ref(false)

async function load() {
  loading.value = true
  loadError.value = false
  try {
    stats.value = await adminApi.dashboard()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <header class="page-heading"><div><h2>后台概览</h2><p class="admin-description">从一篇文章、一条回复，继续今天的记录。</p></div><el-button :loading="loading" @click="load">刷新概览</el-button></header>
    <div v-if="loadError" class="admin-feedback" role="alert"><span>概览加载失败，请稍后重试。</span><el-button @click="load">重新加载</el-button></div>
    <div v-else-if="loading" class="admin-initial-loading" role="status" aria-label="概览加载中"><el-skeleton :rows="4" animated /></div>
    <el-row v-else-if="stats" :gutter="16" class="stats">
      <el-col :xs="12" :sm="12" :lg="6">
        <el-card shadow="hover">
          <template #header>用户总数</template>
          <div class="number">{{ stats.total_users }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :lg="6">
        <el-card shadow="hover">
          <template #header>文章总数</template>
          <div class="number">{{ stats.total_articles }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :lg="6">
        <el-card shadow="hover">
          <template #header>评论总数</template>
          <div class="number">{{ stats.total_comments }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :lg="6">
        <el-card shadow="hover" :class="{ 'pending-highlight': stats.pending_comments > 0 }">
          <template #header>待审核评论</template>
          <div class="number">{{ stats.pending_comments }}</div>
        </el-card>
      </el-col>
    </el-row>
    <nav class="quick-links" aria-label="常用操作">
      <RouterLink to="/articles/new"><strong>写一篇文章 <span aria-hidden="true">↗</span></strong><span>把新的想法整理成文字</span></RouterLink>
      <RouterLink to="/admin/comments"><strong>处理评论 <span aria-hidden="true">↗</span></strong><span>回应读者，审核新的讨论</span></RouterLink>
      <RouterLink to="/admin/todos"><strong>查看待办 <span aria-hidden="true">↗</span></strong><span>安排事项和下一次提醒</span></RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.stats {
  margin-top: 16px;
  row-gap: 16px;
}
.page-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
.page-heading h2 { margin: 0; }
.stats :deep(.el-card) { border-radius: var(--app-radius); }
.stats :deep(.el-card__header) { font-size: 13px; color: var(--el-text-color-secondary); padding: 16px 20px; }
.quick-links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 28px; }
.quick-links a { display: grid; gap: 10px; padding: 22px; border: 1px solid var(--el-border-color-lighter); border-radius: var(--app-radius); background: var(--app-surface); color: var(--el-text-color-primary); transition: border-color .15s ease; }
.quick-links a:hover { border-color: var(--el-color-primary); }
.quick-links strong { display: flex; justify-content: space-between; font-size: 15px; }
.quick-links a > span { font-size: 13px; color: var(--el-text-color-secondary); line-height: 1.7; }
@media (max-width: 900px) { .quick-links { grid-template-columns: 1fr; } }
.number {
  font-size: 28px;
  font-weight: 600;
  text-align: center;
}
.pending-highlight {
  border-color: var(--el-color-warning);
}
</style>
