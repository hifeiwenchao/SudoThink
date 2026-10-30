<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { articleApi, type Article } from '@/api/article'

const list = ref<Article[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const loading = ref(false)
const keyword = ref('')

async function load() {
  loading.value = true
  try {
    const data = await articleApi.list({
      page: page.value,
      size: size.value,
      q: keyword.value || undefined,
    })
    list.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="home">
    <el-input
      v-model="keyword"
      placeholder="搜索文章标题"
      clearable
      class="search"
      @keyup.enter="load"
    >
      <template #append>
        <el-button @click="load">搜索</el-button>
      </template>
    </el-input>

    <el-skeleton v-if="loading" :rows="5" animated />

    <el-empty v-else-if="!list.length" description="暂时还没有文章" />

    <el-card v-for="item in list" :key="item.id" class="article-card" shadow="hover">
      <RouterLink :to="`/articles/${item.id}`" class="title">{{ item.title }}</RouterLink>
      <div class="meta">
        <span>{{ item.author.nickname || item.author.username }}</span>
        <span>·</span>
        <span>{{ new Date(item.created_at).toLocaleString() }}</span>
        <span v-if="item.category">· {{ item.category.name }}</span>
      </div>
      <div v-if="item.summary" class="summary">{{ item.summary }}</div>
    </el-card>

    <el-pagination
      v-if="total > size"
      v-model:current-page="page"
      :page-size="size"
      :total="total"
      layout="prev, pager, next, total"
      class="pagination"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.home {
  max-width: 900px;
  margin: 0 auto;
}
.search {
  margin-bottom: 16px;
}
.article-card {
  margin-bottom: 12px;
}
.title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.meta {
  margin: 6px 0;
  color: #909399;
  font-size: 12px;
  display: flex;
  gap: 6px;
}
.summary {
  color: #606266;
}
.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
