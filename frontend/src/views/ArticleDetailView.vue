<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { articleApi, type Article } from '@/api/article'

const route = useRoute()
const article = ref<Article | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    article.value = await articleApi.detail(Number(route.params.id))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="detail">
    <el-skeleton v-if="loading" :rows="6" animated />
    <template v-else-if="article">
      <h1>{{ article.title }}</h1>
      <div class="meta">
        <span>{{ article.author.nickname || article.author.username }}</span>
        <span>· {{ new Date(article.created_at).toLocaleString() }}</span>
        <span>· 阅读 {{ article.view_count }}</span>
      </div>
      <div class="content">{{ article.content }}</div>
      <div class="tags">
        <el-tag v-for="t in article.tags" :key="t.id" type="info" class="tag">
          {{ t.name }}
        </el-tag>
      </div>
    </template>
  </div>
</template>

<style scoped>
.detail {
  max-width: 800px;
  margin: 0 auto;
  background: #fff;
  padding: 24px;
  border-radius: 8px;
}
.meta {
  color: #909399;
  font-size: 12px;
  margin-bottom: 16px;
  display: flex;
  gap: 6px;
}
.content {
  line-height: 1.8;
  white-space: pre-wrap;
  color: #303133;
}
.tags {
  margin-top: 16px;
}
.tag {
  margin-right: 8px;
}
</style>
