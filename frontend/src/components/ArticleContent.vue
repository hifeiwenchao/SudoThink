<script setup lang="ts">
import { computed } from 'vue'
import { toArticleHtml } from '@/utils/articleContent'
import '@/styles/article.css'

const props = defineProps<{ content: string }>()
const html = computed(() => toArticleHtml(props.content))
</script>

<template>
  <div class="article-prose" v-html="html" />
</template>
