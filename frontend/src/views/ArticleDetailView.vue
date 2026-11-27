<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, Clock, List, Picture, RefreshRight, View } from '@element-plus/icons-vue'
import { articleApi, type Article } from '@/api/article'
import ArticleContent from '@/components/ArticleContent.vue'
import ArticleComments from '@/components/ArticleComments.vue'
import WechatShare from '@/components/WechatShare.vue'
import { getArticleText } from '@/utils/articleContent'
import { safeListReturn, canReturnToListHistory } from '@/utils/publicNavigation'
import { setPageSeo } from '@/utils/seo'
import { isAdminSite } from '@/site'

interface ContentsItem { id: string; text: string; level: number }

const route = useRoute()
const router = useRouter()
const article = ref<Article | null>(null)
const listReturn = computed(() => safeListReturn(route.query.from))
function returnToList(event: MouseEvent) {
  if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  const previous = router.options.history.state.back
  if (canReturnToListHistory(previous, listReturn.value)) router.back()
  else void router.push(listReturn.value)
}

const loading = ref(true)
const loadError = ref<'not-found' | 'network' | null>(null)
const coverFailed = ref(false)
const readingBody = ref<HTMLElement | null>(null)
const contents = ref<ContentsItem[]>([])
const activeSection = ref('')
const mobileContentsOpen = ref(false)
let selectedHeading: HTMLElement | undefined
let requestVersion = 0
let headingElements: HTMLElement[] = []
let scrollFrame = 0

const authorName = computed(() => article.value?.author.nickname || article.value?.author.username || '')
const wordCount = computed(() => getArticleText(article.value?.content || '').replace(/\s/g, '').length)
const readingMinutes = computed(() => Math.max(1, Math.ceil(wordCount.value / 400)))
const articleDate = computed(() => article.value?.published_at || article.value?.created_at || '')
const formattedDate = computed(() => {
  const date = new Date(articleDate.value)
  if (Number.isNaN(date.getTime())) return ''
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('.')
})

async function load() {
  mobileContentsOpen.value = false
  selectedHeading = undefined
  const version = ++requestVersion
  loading.value = true
  loadError.value = null
  article.value = null
  coverFailed.value = false
  contents.value = []
  headingElements = []
  activeSection.value = ''
  try {
    const result = await articleApi.detail(Number(route.params.id))
    if (version === requestVersion) {
      article.value = result
      setPageSeo({ title: result.title, description: result.summary || getArticleText(result.content).slice(0, 160) || result.title, path: '/articles/' + result.id, image: result.cover, type: 'article', noindex: isAdminSite() || !result.is_published })
    }
  } catch (error: unknown) {
    if (version !== requestVersion) return
    const failure = error as { response?: { status?: number }; code?: number }
    loadError.value = failure?.response?.status === 404 || failure?.code === 404 ? 'not-found' : 'network'
    setPageSeo({ title: loadError.value === 'not-found' ? '文章未找到' : '文章加载失败', description: '请浏览其他文章或稍后重试。', path: route.path, noindex: true })
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function updateActiveSection() {
  scrollFrame = 0
  if (!headingElements.length) return
  let current = headingElements[0]!
  for (const heading of headingElements) {
    if (heading.getBoundingClientRect().top > 164) break
    current = heading
  }
  activeSection.value = current.id
}

function queueSectionUpdate() {
  if (!scrollFrame) scrollFrame = window.requestAnimationFrame(updateActiveSection)
}

function goToSection(id: string, updateUrl = true) {
  const heading = headingElements.find((element) => element.id === id)
  if (!heading) return
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  heading.scrollIntoView({ behavior: reduceMotion ? 'instant' : 'smooth', block: 'start' })
  heading.focus({ preventScroll: true })
  activeSection.value = id
  if (updateUrl && route.hash !== `#${id}`) void router.replace({ query: route.query, hash: `#${id}` })
}

function selectMobileSection(id: string) {
  selectedHeading = headingElements.find((heading) => heading.id === id)
  mobileContentsOpen.value = false
  goToSection(id)
}

function restoreContentsFocus() {
  if (!selectedHeading) return
  selectedHeading.focus({ preventScroll: true })
  selectedHeading = undefined
}

function onReadingResize() {
  if (window.innerWidth > 760) mobileContentsOpen.value = false
  queueSectionUpdate()
}

async function buildContents() {
  await nextTick()
  headingElements = Array.from(readingBody.value?.querySelectorAll<HTMLElement>('.article-prose h2, .article-prose h3, .article-prose h4') || [])
  const usedIds = new Set<string>()
  contents.value = headingElements.map((heading, index) => {
    const text = heading.textContent?.trim() || `章节 ${index + 1}`
    const slug = text.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '').slice(0, 64) || 'section'
    const baseId = `article-${article.value?.id}-${slug}`
    let id = baseId
    let duplicate = 1
    while (usedIds.has(id)) id = `${baseId}-${++duplicate}`
    usedIds.add(id)
    heading.id = id
    heading.tabIndex = -1
    return { id, text, level: Number(heading.tagName.slice(1)) }
  })
  updateActiveSection()
  if (route.hash) goToSection(route.hash.slice(1), false)
}

watch(() => route.params.id, load, { immediate: true })
watch([() => article.value?.content, loading], buildContents, { flush: 'post' })

onMounted(() => {
  window.addEventListener('scroll', queueSectionUpdate, { passive: true })
  window.addEventListener('resize', onReadingResize, { passive: true })
})
onBeforeUnmount(() => {
  requestVersion++
  window.removeEventListener('scroll', queueSectionUpdate)
  window.removeEventListener('resize', onReadingResize)
  if (scrollFrame) window.cancelAnimationFrame(scrollFrame)
})
</script>

<template>
  <div class="article-detail">
    <div class="detail-path">
      <a class="back-link" :href="listReturn" @click="returnToList"><ArrowLeft aria-hidden="true" />返回文章列表</a>
      <span class="path-label">SUDOTHINK / ARTICLE</span>
    </div>

    <div v-if="loading" class="article-loading" role="status" aria-label="文章加载中">
      <span class="loading-label"><span class="status-dot" />正在读取文章…</span>
      <el-skeleton :rows="9" animated />
    </div>

    <section v-else-if="loadError" class="article-error" aria-labelledby="article-error-title">
      <span class="error-code">{{ loadError === 'not-found' ? '404 / NOT FOUND' : 'CONNECTION INTERRUPTED' }}</span>
      <h1 id="article-error-title">{{ loadError === 'not-found' ? '这篇文章暂时找不到了' : '文章加载失败' }}</h1>
      <p>{{ loadError === 'not-found' ? '文章可能已移除，或尚未公开。去看看其他的思考与记录吧。' : '暂时没能获取文章内容，请检查网络后再试一次。' }}</p>
      <RouterLink v-if="loadError === 'not-found'" class="action-link" to="/">浏览全部文章<ArrowRight aria-hidden="true" /></RouterLink>
      <button v-else class="retry-button" type="button" @click="load"><RefreshRight aria-hidden="true" />重新加载</button>
    </section>

    <article v-else-if="article" class="reading-article">
      <button v-if="contents.length" class="mobile-contents-trigger" type="button" aria-controls="mobile-article-contents" :aria-expanded="mobileContentsOpen" @click="mobileContentsOpen = true"><List aria-hidden="true" /><span>目录</span></button>
      <el-drawer v-model="mobileContentsOpen" class="mobile-contents-drawer" title="本页目录" direction="btt" size="min(70dvh, 560px)" :close-on-press-escape="true" @closed="restoreContentsFocus">
        <nav id="mobile-article-contents" class="mobile-contents-links" aria-label="手机文章目录">
          <a v-for="item in contents" :key="item.id" :href="`#${item.id}`" :class="['contents-link', `level-${item.level}`, { active: activeSection === item.id }]" :aria-current="activeSection === item.id ? 'location' : undefined" @click.prevent="selectMobileSection(item.id)">{{ item.text }}</a>
        </nav>
      </el-drawer>
      <header class="article-header">
        <div class="article-eyebrow">
          <span class="category-label">{{ article.category?.name || '未分类' }}</span>
          <span v-if="formattedDate" class="meta-slash">/</span>
          <time v-if="formattedDate" :datetime="articleDate">{{ formattedDate }}</time>
        </div>
        <h1>{{ article.title }}</h1>
        <p v-if="article.summary" class="article-summary">{{ article.summary }}</p>
        <div class="article-meta">
          <span class="author-meta"><span class="author-initial" aria-hidden="true">{{ authorName.slice(0, 1).toUpperCase() }}</span>{{ authorName }}</span>
          <span><Clock aria-hidden="true" />约 {{ readingMinutes }} 分钟</span>
          <span><View aria-hidden="true" />{{ article.view_count.toLocaleString() }} 次阅读</span>
          <WechatShare :title="article.title" :summary="article.summary" :cover="article.cover" />
        </div>
      </header>

      <div class="reading-grid">
        <aside class="reading-aside" :class="{ 'without-contents': !contents.length }" aria-label="阅读导航">
          <details v-if="contents.length" class="contents-panel" open>
            <summary><span>本页目录 <small>CONTENTS</small></span><span class="contents-count">{{ String(contents.length).padStart(2, '0') }}</span></summary>
            <nav aria-label="文章目录">
              <a
                v-for="item in contents"
                :key="item.id"
                :href="`#${item.id}`"
                :class="['contents-link', `level-${item.level}`, { active: activeSection === item.id }]"
                :aria-current="activeSection === item.id ? 'location' : undefined"
                @click.prevent="goToSection(item.id)"
              >{{ item.text }}</a>
            </nav>
          </details>
          <div class="reading-note">
            <span class="note-label">阅读这篇文章</span>
            <span>{{ wordCount.toLocaleString() }} 字 <span class="note-dot">·</span> 约 {{ readingMinutes }} 分钟</span>
          </div>
        </aside>

        <div ref="readingBody" class="reading-body">
          <figure v-if="article.cover" class="article-cover">
            <img v-if="!coverFailed" :key="article.cover" :src="article.cover" :alt="article.title" @error="coverFailed = true" @load="queueSectionUpdate" />
            <div v-else class="cover-fallback"><Picture aria-hidden="true" /><span>封面暂时无法加载</span></div>
          </figure>
          <ArticleContent :content="article.content" />
          <ArticleComments :key="article.id" :article-id="article.id" />
          <footer class="article-end">
            <div v-if="article.tags.length" class="article-tags" aria-label="文章标签">
              <span v-for="tag in article.tags" :key="tag.id" class="article-tag"><span aria-hidden="true">#</span>{{ tag.name }}</span>
            </div>
            <div class="end-line"><span class="end-mark" aria-hidden="true">[ EOF ]</span><span>思考在此落笔，探索继续。</span></div>
            <a class="back-link end-back-link" :href="listReturn" @click="returnToList"><ArrowLeft aria-hidden="true" />继续阅读其他文章</a>
          </footer>
        </div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.article-detail { width: min(1120px, calc(100% - 64px)); margin: 0 auto; padding: 36px 0 88px; color: var(--blog-text); }
.detail-path { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 58px; }
.back-link { display: inline-flex; align-items: center; gap: 8px; color: var(--blog-muted); font-size: 13px; text-decoration: none; transition: color .2s; }
.back-link:hover, .back-link:focus-visible { color: var(--blog-accent); }
.back-link svg, .article-meta svg, .action-link svg, .retry-button svg { width: 15px; height: 15px; flex-shrink: 0; }
.path-label { color: var(--blog-muted); font: 10px var(--blog-mono); letter-spacing: .1em; }
.article-header { max-width: 720px; margin-bottom: 40px; }
.article-eyebrow { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; color: var(--blog-muted); font: 12px var(--blog-mono); }
.category-label { color: var(--blog-accent); font-weight: 600; overflow-wrap: anywhere; min-width: 0; }
.meta-slash { color: var(--blog-border); }
.article-header h1 { margin: 22px 0 18px; font-size: clamp(30px, 3.8vw, 44px); font-weight: 750; line-height: 1.35; letter-spacing: -.035em; overflow-wrap: anywhere; }
.article-summary { margin: 0; color: var(--blog-muted); font-size: 17px; line-height: 1.85; overflow-wrap: anywhere; }
.article-meta { display: flex; align-items: center; flex-wrap: wrap; column-gap: 22px; row-gap: 12px; margin-top: 28px; padding-bottom: 28px; border-bottom: 1px solid var(--blog-border); color: var(--blog-muted); font-size: 12px; }
.article-meta > span { display: inline-flex; align-items: center; gap: 7px; max-width: 100%; overflow-wrap: anywhere; }
.article-meta .author-meta { gap: 9px; color: var(--blog-text); font-weight: 500; }
.author-initial { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--blog-border); border-radius: 7px; background: var(--blog-surface-alt); color: var(--blog-accent); font: 12px var(--blog-mono); }
.reading-grid { display: grid; grid-template-columns: minmax(0, 720px) minmax(0, 240px); gap: 64px; align-items: start; }
.reading-body { grid-column: 1; grid-row: 1; min-width: 0; }
.reading-aside { grid-column: 2; grid-row: 1; position: sticky; top: 110px; min-width: 0; }
.contents-panel { border-top: 1px solid var(--blog-border); }
.contents-panel summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 0; color: var(--blog-text); cursor: pointer; list-style: none; font-size: 12px; font-weight: 600; }
.contents-panel summary::-webkit-details-marker { display: none; }
.contents-panel summary small { margin-left: 7px; color: var(--blog-muted); font: 9px var(--blog-mono); letter-spacing: .05em; }
.contents-count { color: var(--blog-accent); font: 11px var(--blog-mono); }
.contents-panel nav { display: flex; flex-direction: column; max-height: min(60vh, 560px); overflow-y: auto; padding: 2px 0 4px; }
.contents-link { padding: 9px 13px; border-left: 1px solid var(--blog-border); color: var(--blog-muted); font-size: 12px; line-height: 1.6; text-decoration: none; overflow-wrap: anywhere; transition: color .2s, background .2s, border-color .2s; }
.contents-link.level-3 { padding-left: 24px; }
.contents-link.level-4 { padding-left: 35px; }
.contents-link:hover { color: var(--blog-text); background: var(--blog-surface-alt); }
.contents-link.active { color: var(--blog-accent); border-left-color: var(--blog-accent); background: var(--blog-accent-soft); }
.reading-note { display: flex; flex-direction: column; gap: 9px; margin-top: 26px; padding-top: 18px; border-top: 1px solid var(--blog-border); color: var(--blog-muted); font: 11px var(--blog-mono); }
.note-label { line-height: 1.5; }
.note-dot { margin: 0 5px; }
.without-contents .reading-note { margin-top: 0; }
.article-cover { margin: 0 0 38px; overflow: hidden; border: 1px solid var(--blog-border); border-radius: 10px; background: var(--blog-surface-alt); }
.article-cover img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
.cover-fallback { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; aspect-ratio: 16 / 7; color: var(--blog-muted); font-size: 12px; background-image: linear-gradient(var(--blog-grid) 1px, transparent 1px), linear-gradient(90deg, var(--blog-grid) 1px, transparent 1px); background-size: 24px 24px; }
.cover-fallback svg { width: 28px; height: 28px; opacity: .6; }
.reading-body :deep(.article-prose) { font-size: 16px; line-height: 2; }
.reading-body :deep(.article-prose h1), .reading-body :deep(.article-prose h2), .reading-body :deep(.article-prose h3), .reading-body :deep(.article-prose h4) { scroll-margin-top: 120px; letter-spacing: -.02em; }
.reading-body :deep(.article-prose h2) { margin-top: 2em; font-size: 1.5em; }
.reading-body :deep(.article-prose pre) { border: 1px solid var(--blog-border); border-radius: 8px; }
.reading-body :deep(.article-prose a) { color: var(--blog-accent); }
.reading-body :deep(.article-prose h2:focus), .reading-body :deep(.article-prose h3:focus), .reading-body :deep(.article-prose h4:focus) { outline: none; }
.article-end { margin-top: 52px; padding-top: 26px; border-top: 1px solid var(--blog-border); }
.article-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 32px; }
.article-tag { display: inline-flex; gap: 5px; padding: 5px 9px; border: 1px solid var(--blog-border); border-radius: 5px; color: var(--blog-muted); font-size: 11px; overflow-wrap: anywhere; }
.article-tag > span { color: var(--blog-accent); font-family: var(--blog-mono); }
.end-line { display: flex; align-items: center; flex-wrap: wrap; gap: 13px; color: var(--blog-muted); font-size: 12px; }
.end-mark { color: var(--blog-accent); font: 11px var(--blog-mono); }
.end-back-link { margin-top: 24px; }
.article-loading { max-width: 760px; padding: 24px 0 80px; }
.loading-label { display: flex; align-items: center; gap: 9px; margin-bottom: 32px; color: var(--blog-muted); font: 12px var(--blog-mono); }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blog-accent); }
.article-error { padding: 72px 24px 112px; border: 1px solid var(--blog-border); border-radius: 10px; background: var(--blog-surface); text-align: center; }
.error-code { color: var(--blog-accent); font: 11px var(--blog-mono); letter-spacing: .08em; }
.article-error h1 { margin: 22px 0 12px; font-size: clamp(24px, 4vw, 32px); line-height: 1.5; }
.article-error p { margin: 0 auto 28px; max-width: 420px; color: var(--blog-muted); font-size: 14px; line-height: 1.9; }
.action-link, .retry-button { display: inline-flex; align-items: center; justify-content: center; gap: 9px; padding: 10px 16px; border: 1px solid var(--blog-border); border-radius: 6px; background: var(--blog-surface-alt); color: var(--blog-accent); font: inherit; font-size: 13px; text-decoration: none; cursor: pointer; }
.action-link:hover, .retry-button:hover { border-color: var(--blog-accent); }
.contents-link:focus-visible, .contents-panel summary:focus-visible, .back-link:focus-visible, .action-link:focus-visible, .retry-button:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 4px; }
.mobile-contents-trigger { display: none; }
.mobile-contents-links { display: flex; flex-direction: column; padding: 4px; }
:deep(.mobile-contents-drawer) { color: var(--blog-text); background: var(--blog-surface); border-radius: 16px 16px 0 0; }
:deep(.mobile-contents-drawer .el-drawer__header) { margin-bottom: 0; padding: 20px 24px 16px; border-bottom: 1px solid var(--blog-border); color: var(--blog-text); }
:deep(.mobile-contents-drawer .el-drawer__body) { overscroll-behavior: contain; padding: 16px 20px max(20px, env(safe-area-inset-bottom)); }
@media (max-width: 1000px) {
  .reading-grid { grid-template-columns: minmax(0, 1fr) 200px; gap: 36px; }
  .article-header { max-width: calc(100% - 236px); }
  .contents-panel summary small { display: none; }
}
@media (max-width: 760px) {
  .article-detail { padding-top: 24px; padding-bottom: 56px; }
  .detail-path { margin-bottom: 36px; }
  .path-label { font-size: 8px; letter-spacing: .04em; }
  .article-header { max-width: none; margin-bottom: 28px; }
  .article-header h1 { margin: 18px 0 16px; font-size: 30px; line-height: 1.4; }
  .article-summary { font-size: 15px; }
  .article-meta { column-gap: 16px; margin-top: 23px; padding-bottom: 24px; font-size: 11px; }
  .reading-grid { display: flex; flex-direction: column; gap: 28px; }
  .reading-aside { display: none; }
  .mobile-contents-trigger { display: flex; position: fixed; z-index: 44; right: calc(80px + env(safe-area-inset-right)); bottom: calc(12px + env(safe-area-inset-bottom)); flex-direction: column; align-items: center; justify-content: center; gap: 3px; width: 52px; min-height: 60px; border: 1px solid var(--blog-border); border-radius: 10px; background: var(--blog-surface); color: var(--blog-muted); box-shadow: 0 4px 18px rgb(0 0 0 / .08); font: inherit; font-size: 11px; cursor: pointer; }
  .mobile-contents-trigger svg { width: 19px; height: 19px; }
  .mobile-contents-trigger:hover { color: var(--blog-accent); border-color: var(--blog-accent); }
  .reading-body { width: 100%; }
  .contents-panel { padding: 0 16px; border: 1px solid var(--blog-border); border-radius: 7px; background: var(--blog-surface); }
  .contents-panel summary { padding: 14px 0; }
  .contents-panel summary small { display: inline; }
  .contents-panel summary::after { content: '+'; color: var(--blog-muted); font: 16px var(--blog-mono); }
  .contents-panel[open] summary::after { content: '−'; }
  .contents-count { margin-left: auto; }
  .contents-panel nav { padding-bottom: 14px; max-height: 260px; }
  .reading-note { display: none; }
  .without-contents { display: none; }
  .article-cover { margin-bottom: 28px; border-radius: 7px; }
  .reading-body :deep(.article-prose) { font-size: 15px; line-height: 1.95; }
  .reading-body :deep(.article-prose pre) { padding: 18px; }
  .reading-body :deep(.article-prose h1), .reading-body :deep(.article-prose h2), .reading-body :deep(.article-prose h3), .reading-body :deep(.article-prose h4) { scroll-margin-top: 150px; }
  .article-end { margin-top: 38px; }
  .article-error { padding: 52px 20px 64px; }
}
@media (prefers-reduced-motion: reduce) {
  .back-link, .contents-link { transition: none; }
}
@media (max-width: 640px) {
  .article-detail { width: calc(100% - 40px); }
}
</style>
