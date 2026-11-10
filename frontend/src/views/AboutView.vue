<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft, ArrowRight, RefreshRight } from '@element-plus/icons-vue'
import { aboutApi } from '@/api/about'
import ArticleContent from '@/components/ArticleContent.vue'
import { hasArticleContent } from '@/utils/articleContent'

const about = ref<Awaited<ReturnType<typeof aboutApi.get>> | null>(null)
const loading = ref(true)
const loadError = ref(false)
let requestVersion = 0

const hasContent = computed(() => hasArticleContent(about.value?.content || ''))
const formattedDate = computed(() => {
  if (!about.value?.updated_at) return ''
  const date = new Date(about.value.updated_at)
  if (Number.isNaN(date.getTime())) return ''
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('.')
})

async function load() {
  const version = ++requestVersion
  loading.value = true
  loadError.value = false
  about.value = null
  try {
    const result = await aboutApi.get()
    if (version === requestVersion) about.value = result
  } catch {
    if (version === requestVersion) loadError.value = true
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => { requestVersion++ })
</script>

<template>
  <div class="about-page">
    <div class="about-path">
      <RouterLink class="back-link" to="/"><ArrowLeft aria-hidden="true" />返回文章列表</RouterLink>
      <span class="path-label">SUDOTHINK / ABOUT</span>
    </div>

    <div v-if="loading" class="about-loading" role="status" aria-label="关于我加载中">
      <span class="loading-label"><span class="status-dot" />正在读取关于我…</span>
      <el-skeleton :rows="8" animated />
    </div>

    <section v-else-if="loadError" class="about-state" aria-labelledby="about-error-title">
      <span class="state-label">CONNECTION INTERRUPTED</span>
      <h1 id="about-error-title">关于我加载失败</h1>
      <p>暂时没能获取页面内容，请检查网络后再试一次。</p>
      <button class="retry-button" type="button" @click="load"><RefreshRight aria-hidden="true" />重新加载</button>
    </section>

    <article v-else class="about-article">
      <header class="about-header">
        <span class="about-eyebrow">ABOUT ME</span>
        <h1>{{ about?.title || '关于我' }}</h1>
        <p v-if="formattedDate" class="updated-date">最近更新 <time :datetime="about?.updated_at || undefined">{{ formattedDate }}</time></p>
      </header>

      <div v-if="hasContent" class="about-body">
        <ArticleContent :content="about?.content || ''" />
      </div>
      <section v-else class="about-empty" aria-labelledby="about-empty-title">
        <span class="state-label">STILL WRITING</span>
        <h2 id="about-empty-title">关于我的介绍还在准备中</h2>
        <p>先从文章开始，了解这里的思考与记录。</p>
        <RouterLink class="action-link" to="/">浏览全部文章<ArrowRight aria-hidden="true" /></RouterLink>
      </section>

      <footer v-if="hasContent" class="about-end">
        <span class="end-mark" aria-hidden="true">[ EOF ]</span>
        <RouterLink class="back-link" to="/"><ArrowLeft aria-hidden="true" />继续阅读文章</RouterLink>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.about-page { width: min(1120px, calc(100% - 64px)); min-width: 0; margin: 0 auto; padding: 36px 0 88px; color: var(--blog-text); }
.about-path { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 58px; }
.back-link { display: inline-flex; align-items: center; gap: 8px; min-width: 0; color: var(--blog-muted); font-size: 13px; text-decoration: none; transition: color .2s; }
.back-link:hover, .back-link:focus-visible { color: var(--blog-accent); }
.back-link svg, .action-link svg, .retry-button svg { width: 15px; height: 15px; flex-shrink: 0; }
.path-label { color: var(--blog-muted); font: 10px var(--blog-mono); letter-spacing: .1em; }
.about-article, .about-loading, .about-state { width: 100%; max-width: 760px; min-width: 0; }
.about-header { margin-bottom: 38px; padding-bottom: 28px; border-bottom: 1px solid var(--blog-border); }
.about-eyebrow { color: var(--blog-accent); font: 600 12px var(--blog-mono); letter-spacing: .12em; }
.about-header h1 { margin: 22px 0 0; font-size: clamp(30px, 3.8vw, 44px); font-weight: 750; line-height: 1.35; letter-spacing: -.035em; overflow-wrap: anywhere; }
.updated-date { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin: 24px 0 0; color: var(--blog-muted); font-size: 12px; line-height: 1.8; }
.updated-date time { font-family: var(--blog-mono); }
.about-body { min-width: 0; }
.about-body :deep(.article-prose) { font-size: 16px; line-height: 2; }
.about-body :deep(.article-prose h1), .about-body :deep(.article-prose h2), .about-body :deep(.article-prose h3), .about-body :deep(.article-prose h4) { letter-spacing: -.02em; scroll-margin-top: 120px; }
.about-body :deep(.article-prose h2) { margin-top: 2em; font-size: 1.5em; }
.about-body :deep(.article-prose a) { color: var(--blog-accent); }
.about-body :deep(.article-prose pre) { max-width: 100%; border: 1px solid var(--blog-border); border-radius: 8px; }
.about-end { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px; margin-top: 52px; padding-top: 26px; border-top: 1px solid var(--blog-border); }
.end-mark { color: var(--blog-accent); font: 11px var(--blog-mono); }
.about-loading { padding: 24px 0 80px; }
.loading-label { display: flex; align-items: center; gap: 9px; margin-bottom: 32px; color: var(--blog-muted); font: 12px var(--blog-mono); }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blog-accent); }
.about-state, .about-empty { padding: 64px 24px 72px; border: 1px solid var(--blog-border); border-radius: 10px; background: var(--blog-surface); text-align: center; overflow-wrap: anywhere; }
.state-label { color: var(--blog-accent); font: 11px var(--blog-mono); letter-spacing: .08em; }
.about-state h1, .about-empty h2 { margin: 22px 0 12px; font-size: clamp(22px, 3vw, 28px); line-height: 1.5; }
.about-state p, .about-empty p { max-width: 420px; margin: 0 auto 28px; color: var(--blog-muted); font-size: 14px; line-height: 1.9; }
.action-link, .retry-button { display: inline-flex; align-items: center; justify-content: center; gap: 9px; padding: 10px 16px; border: 1px solid var(--blog-border); border-radius: 6px; background: var(--blog-surface-alt); color: var(--blog-accent); font: inherit; font-size: 13px; text-decoration: none; cursor: pointer; }
.action-link:hover, .retry-button:hover { border-color: var(--blog-accent); }
.back-link:focus-visible, .action-link:focus-visible, .retry-button:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 4px; }
@media (max-width: 760px) {
  .about-page { padding-top: 24px; padding-bottom: 56px; }
  .about-path { margin-bottom: 36px; }
  .path-label { font-size: 8px; letter-spacing: .04em; }
  .about-header { margin-bottom: 28px; padding-bottom: 24px; }
  .about-header h1 { margin-top: 18px; font-size: 30px; line-height: 1.4; }
  .updated-date { margin-top: 20px; }
  .about-body :deep(.article-prose) { font-size: 15px; line-height: 1.95; }
  .about-body :deep(.article-prose pre) { padding: 18px; }
  .about-body :deep(.article-prose h1), .about-body :deep(.article-prose h2), .about-body :deep(.article-prose h3), .about-body :deep(.article-prose h4) { scroll-margin-top: 150px; }
  .about-end { margin-top: 38px; }
  .about-state, .about-empty { padding: 48px 20px 56px; }
}
@media (max-width: 640px) {
  .about-page { width: calc(100% - 40px); }
}
@media (prefers-reduced-motion: reduce) {
  .back-link { transition: none; }
}
</style>
