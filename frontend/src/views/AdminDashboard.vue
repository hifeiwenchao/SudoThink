<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminApi, type DashboardResp } from '@/api/admin'

const stats = ref<DashboardResp | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = await adminApi.dashboard()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h2>后台概览</h2>
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-row v-else-if="stats" :gutter="16" class="stats">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>用户总数</template>
          <div class="number">{{ stats.total_users }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>文章总数</template>
          <div class="number">{{ stats.total_articles }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>评论总数</template>
          <div class="number">{{ stats.total_comments }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" :class="{ 'pending-highlight': stats.pending_comments > 0 }">
          <template #header>待审核评论</template>
          <div class="number">{{ stats.pending_comments }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stats {
  margin-top: 16px;
}
.number {
  font-size: 28px;
  font-weight: 600;
  text-align: center;
}
.pending-highlight {
  border-color: #e6a23c;
}
</style>
