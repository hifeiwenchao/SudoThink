<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ArrowRight, Refresh, Search, View } from '@element-plus/icons-vue'
import { articleApi, type Article } from '@/api/article'
import { taxonomyApi, type TaxonomyItem } from '@/api/taxonomy'
import { useTaxonomyStore } from '@/stores/taxonomy'

const route = useRoute()
const router = useRouter()
const taxonomyStore = useTaxonomyStore()
const { categories } = storeToRefs(taxonomyStore)

function routeCategory(): number | undefined {
  const value = route.query.category
  if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) return undefined
  const id = Number(value)
  return Number.isSafeInteger(id) ? id : undefined
}

const list = ref<Article[]>([])
const total = ref(0)
const page = ref(1)
const size = 10
const loading = ref(false)
const hasLoaded = ref(false)
const loadError = ref(false)
const keyword = ref('')
const searchQuery = ref('')
const categoryId = ref<number | undefined>(routeCategory())
const tagId = ref<number>()
const tags = ref<TaxonomyItem[]>([])
const taxonomyLoading = ref(false)
const taxonomyError = ref(false)
const failedCovers = ref(new Set<string>())
let requestId = 0

const hasFilters = computed(() => Boolean(searchQuery.value || categoryId.value || tagId.value))
const selectedCategory = computed(() => categories.value.find((item) => item.id === categoryId.value))
const selectedTag = computed(() => tags.value.find((item) => item.id === tagId.value))

async function load() {
  const currentRequest = ++requestId
  loading.value = true
  loadError.value = false
  try {
    const data = await articleApi.list({
      page: page.value,
      size,
      q: searchQuery.value || undefined,
      category_id: categoryId.value,
      tag_id: tagId.value,
    })
    if (currentRequest !== requestId) return
    list.value = data.items
    total.value = data.total
    hasLoaded.value = true
  } catch {
    if (currentRequest === requestId) loadError.value = true
  } finally {
    if (currentRequest === requestId) loading.value = false
  }
}

async function loadTaxonomy() {
  taxonomyLoading.value = true
  const categoryRequest = taxonomyStore.loaded ? Promise.resolve(categories.value) : taxonomyStore.loadCategories()
  const results = await Promise.allSettled([categoryRequest, taxonomyApi.tags()])
  const [, tagResult] = results
  if (tagResult.status === 'fulfilled') tags.value = tagResult.value
  taxonomyError.value = results.some((result) => result.status === 'rejected')
  taxonomyLoading.value = false
}

function submitSearch() {
  searchQuery.value = keyword.value.trim()
  page.value = 1
  void load()
}

function selectCategory(id?: number) {
  if (categoryId.value === id) {
    page.value = 1
    void load()
    return
  }
  void router.push({ path: '/', query: { ...route.query, category: id ? String(id) : undefined }, hash: '#articles' })
}

function selectTag(id?: number) {
  tagId.value = tagId.value === id ? undefined : id
  page.value = 1
  void load()
}

function clearFilters() {
  keyword.value = ''
  searchQuery.value = ''
  tagId.value = undefined
  page.value = 1
  if (route.query.category) {
    void router.push({ path: '/', query: { ...route.query, category: undefined }, hash: '#articles' })
  } else {
    void load()
  }
}

function changePage(nextPage: number) {
  page.value = nextPage
  void load()
  document.getElementById('articles')?.scrollIntoView({ block: 'start' })
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date).replaceAll('/', '.')
}

function showCover(article: Article) {
  return article.cover && !failedCovers.value.has(article.cover)
}

onMounted(() => {
  void load()
  void loadTaxonomy()
})
watch(() => route.query.category, () => {
  categoryId.value = routeCategory()
  page.value = 1
  void load()
})
</script>

<template>
  <div class="blog-home">
    <section class="hero" aria-labelledby="home-heading">
      <div class="hero-copy">
        <p class="eyebrow"><span class="eyebrow-mark">//</span> NOTES, IDEAS &amp; THINGS I BUILD</p>
        <h1 id="home-heading">记录、思考，<br /><span>然后构建。</span></h1>
        <p class="hero-description">在代码与生活之间，留下一些思考的痕迹。<br class="desktop-break" />分享技术探索，也记录那些值得慢慢琢磨的事。</p>
        <a class="browse-link" href="#articles">浏览文章 <ArrowRight aria-hidden="true" /></a>
      </div>

      <div class="terminal" role="img" aria-label="博客理念：保持好奇，认真思考，动手验证，持续记录">
        <div class="terminal-bar" aria-hidden="true">
          <div class="terminal-dots"><i></i><i></i><i></i></div>
          <span>~/sudothink</span>
          <span class="terminal-bash">bash</span>
        </div>
        <div class="terminal-content" aria-hidden="true">
          <p class="terminal-command"><span>❯</span> cat manifesto.md</p>
          <p class="terminal-comment"># Stay curious. Keep building.</p>
          <div class="manifesto">
            <p><span>01</span> 保持好奇，向未知多走一步。</p>
            <p><span>02</span> 认真思考，让问题有迹可循。</p>
            <p><span>03</span> 动手验证，让想法落到实处。</p>
            <p><span>04</span> 持续记录，分享路上的发现。</p>
          </div>
          <p class="terminal-end"><span>❯</span><i></i></p>
        </div>
      </div>
    </section>

    <div class="content-layout">
      <section id="articles" class="archive" aria-labelledby="archive-heading">
        <div class="archive-heading">
          <div>
            <p class="eyebrow archive-eyebrow">01 / THE ARCHIVE</p>
            <h2 id="archive-heading">最近的文字<span class="heading-dot">.</span></h2>
          </div>
          <form class="search-form" role="search" @submit.prevent="submitSearch">
            <label class="visually-hidden" for="article-search">搜索文章标题</label>
            <Search class="search-icon" aria-hidden="true" />
            <input id="article-search" v-model="keyword" type="search" placeholder="搜索文章标题…" />
            <button type="submit" aria-label="搜索文章"><ArrowRight aria-hidden="true" /></button>
          </form>
        </div>

        <div v-if="categories.length" class="category-filter" aria-label="按分类筛选文章">
          <button :class="{ active: !categoryId }" :aria-pressed="!categoryId" @click="selectCategory()">全部文章</button>
          <button
            v-for="category in categories"
            :key="category.id"
            :class="{ active: categoryId === category.id }"
            :aria-pressed="categoryId === category.id"
            @click="selectCategory(category.id)"
          >{{ category.name }}</button>
        </div>

        <div v-if="hasFilters" class="active-filters">
          <span v-if="searchQuery">搜索：{{ searchQuery }}</span>
          <span v-if="categoryId">分类：{{ selectedCategory?.name || '所选分类' }}</span>
          <span v-if="selectedTag">标签：{{ selectedTag.name }}</span>
          <button @click="clearFilters">清空筛选 <span aria-hidden="true">×</span></button>
        </div>

        <div v-if="loading" class="article-skeleton" role="status" aria-label="正在加载文章">
          <div v-for="index in 3" :key="index" class="skeleton-row"><i></i><i></i><i></i></div>
          <span class="visually-hidden">正在加载文章…</span>
        </div>

        <div v-else-if="loadError" class="empty-state" role="alert">
          <span class="empty-symbol" aria-hidden="true">[ ! ]</span>
          <h3>文章暂时没有加载出来</h3>
          <p>连接似乎遇到了问题，稍后再试一次。</p>
          <button class="state-action" @click="load"><Refresh aria-hidden="true" />重新加载</button>
        </div>

        <div v-else-if="!list.length" class="empty-state">
          <span class="empty-symbol" aria-hidden="true">{{ hasFilters ? '[ ? ]' : '[ … ]' }}</span>
          <h3>{{ hasFilters ? '没有找到相关的文章' : '故事，正在酝酿中' }}</h3>
          <p>{{ hasFilters ? '换个关键词，或看看其他分类与标签。' : '这里会慢慢收集新的想法、探索与记录。' }}</p>
          <button v-if="hasFilters" class="state-action" @click="clearFilters">查看全部文章<ArrowRight aria-hidden="true" /></button>
          <button v-else class="state-action" @click="load"><Refresh aria-hidden="true" />刷新文章</button>
        </div>

        <div v-else class="article-list">
          <article v-for="(item, index) in list" :key="item.id" class="article-card" :class="{ 'first-article': index === 0 && page === 1 }">
            <div class="article-meta">
              <button v-if="item.category" class="article-category" @click="selectCategory(item.category.id)">{{ item.category.name }}</button>
              <span v-else class="article-category-label">未分类</span>
              <span class="meta-divider" aria-hidden="true">/</span>
              <time :datetime="item.published_at || item.created_at">{{ formatDate(item.published_at || item.created_at) }}</time>
            </div>
            <div class="article-body" :class="{ 'has-cover': showCover(item) }">
              <div class="article-copy">
                <h3><RouterLink :to="`/articles/${item.id}`">{{ item.title }}<ArrowRight class="title-arrow" aria-hidden="true" /></RouterLink></h3>
                <p v-if="item.summary" class="article-summary">{{ item.summary }}</p>
              </div>
              <RouterLink v-if="showCover(item)" class="article-cover" :to="`/articles/${item.id}`" tabindex="-1" aria-hidden="true">
                <img :src="item.cover" alt="" loading="lazy" @error="failedCovers.add(item.cover)" />
              </RouterLink>
            </div>
            <div class="article-footer">
              <div class="article-tags" aria-label="文章标签">
                <button v-for="tag in item.tags" :key="tag.id" :class="{ selected: tagId === tag.id }" :aria-pressed="tagId === tag.id" @click="selectTag(tag.id)"><span aria-hidden="true">#</span>{{ tag.name }}</button>
              </div>
              <div class="article-byline"><span>{{ item.author.nickname || item.author.username }}</span><span class="byline-dot" aria-hidden="true">·</span><span class="view-count"><View aria-hidden="true" />{{ item.view_count }}<span class="visually-hidden"> 次阅读</span></span></div>
            </div>
          </article>
        </div>

        <div v-if="hasLoaded && !loading && !loadError && list.length" class="archive-footer">
          <span class="article-total">{{ hasFilters ? '找到' : '共' }} {{ total }} 篇文章</span>
          <el-pagination
            v-if="total > size"
            :current-page="page"
            :page-size="size"
            :total="total"
            :pager-count="5"
            layout="prev, pager, next"
            class="pagination"
            @current-change="changePage"
          />
          <span v-else class="archive-end">// 到这里，刚刚好</span>
        </div>
      </section>

      <aside class="sidebar" aria-label="站点介绍与文章索引">
        <section id="about" class="about-card" aria-labelledby="about-heading">
          <p class="eyebrow">02 / ABOUT THIS SPACE</p>
          <div class="about-symbol" aria-hidden="true">&gt;_</div>
          <h2 id="about-heading">思考，不止于此。</h2>
          <p>这里是 SudoThink，一处存放技术手记、实践经验与日常思考的地方。</p>
          <p>相信写下来，才能想得更清楚。也希望这些文字，能为你带来一点新的启发。</p>
          <div class="about-signature"><span aria-hidden="true">↳</span> Learn. Think. Build.</div>
        </section>

        <section v-if="tags.length" class="tag-index" aria-labelledby="tag-heading">
          <p class="eyebrow">03 / EXPLORE BY TOPIC</p>
          <h2 id="tag-heading">话题索引 <span aria-hidden="true">#</span></h2>
          <div class="topic-tags">
            <button v-for="tag in tags" :key="tag.id" :class="{ active: tagId === tag.id }" :aria-pressed="tagId === tag.id" @click="selectTag(tag.id)"><span aria-hidden="true">#</span> {{ tag.name }}</button>
          </div>
        </section>

        <div v-if="taxonomyError" class="taxonomy-error" role="status">
          <p>部分分类或标签未能加载。</p>
          <button :disabled="taxonomyLoading" @click="loadTaxonomy"><Refresh aria-hidden="true" />{{ taxonomyLoading ? '正在加载…' : '重新加载索引' }}</button>
        </div>

        <p class="sidebar-note"><span aria-hidden="true">/*</span><br />让想法在文字里沉淀，<br />让好奇心继续向前。<br /><span aria-hidden="true">*/</span></p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.blog-home { width: min(1120px, calc(100% - 64px)); margin: 0 auto; color: var(--blog-text); }
button, input { font: inherit; }
button { cursor: pointer; }
button, a, input { -webkit-tap-highlight-color: transparent; }
button:focus-visible, a:focus-visible, input:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 5px; }
.eyebrow { margin: 0; font-family: var(--blog-mono); font-size: 10px; line-height: 1.6; font-weight: 500; letter-spacing: 1.3px; color: var(--blog-muted); }
.eyebrow-mark { color: var(--blog-accent); margin-right: 6px; }
.hero { position: relative; display: grid; grid-template-columns: 1.12fr 1fr; align-items: center; gap: 72px; min-height: 390px; padding: 42px 0 57px; }
.hero::before { content: ''; position: absolute; inset: 20px -20px 20px 40%; background-image: linear-gradient(var(--blog-grid) 1px, transparent 1px), linear-gradient(90deg, var(--blog-grid) 1px, transparent 1px); background-size: 24px 24px; mask-image: radial-gradient(ellipse at center, #000 25%, transparent 72%); pointer-events: none; }
.hero-copy { position: relative; }
.hero-copy h1 { margin: 21px 0 18px; font-size: clamp(38px, 4.1vw, 50px); line-height: 1.3; letter-spacing: -1.5px; font-weight: 750; }
.hero-copy h1 > span { color: var(--blog-accent); }
.hero-description { font-size: 14px; color: var(--blog-muted); line-height: 1.95; margin: 0; }
.browse-link { display: inline-flex; gap: 22px; align-items: center; margin-top: 24px; font-size: 13px; font-weight: 600; text-decoration: none; color: var(--blog-accent); }
.browse-link svg { width: 16px; transition: transform .18s ease; }
.browse-link:hover svg { transform: translateX(4px); }
.terminal { overflow: hidden; border: 1px solid color-mix(in srgb, var(--blog-terminal-text) 13%, transparent); border-radius: 11px; background: var(--blog-terminal-bg); color: var(--blog-terminal-text); box-shadow: 0 16px 35px rgb(0 0 0 / 7%); font-family: var(--blog-mono); transform: rotate(-1deg); }
.terminal-bar { display: flex; align-items: center; justify-content: space-between; gap: 15px; padding: 13px 17px; border-bottom: 1px solid color-mix(in srgb, var(--blog-terminal-text) 10%, transparent); color: var(--blog-terminal-muted); font-size: 10px; }
.terminal-dots { display: flex; gap: 5px; }
.terminal-dots i { width: 7px; height: 7px; border-radius: 50%; background: #ec786e; }
.terminal-dots i:nth-child(2) { background: #d7b15e; }
.terminal-dots i:nth-child(3) { background: #74a887; }
.terminal-bash { font-size: 9px; opacity: .7; }
.terminal-content { padding: 23px 24px 18px; font-size: 11px; line-height: 1.8; }
.terminal-content p { margin: 0; }
.terminal-command { color: var(--blog-terminal-text); }
.terminal-command > span, .terminal-end > span { color: var(--blog-terminal-accent); margin-right: 9px; }
.terminal-comment { color: var(--blog-terminal-accent); padding-top: 20px; }
.manifesto { padding: 12px 0 18px; }
.manifesto p { margin: 6px 0; letter-spacing: .3px; }
.manifesto span { display: inline-block; color: var(--blog-terminal-muted); margin-right: 12px; font-size: 10px; opacity: .7; }
.terminal-end { display: flex; align-items: center; }
.terminal-end i { display: inline-block; width: 6px; height: 12px; background: var(--blog-terminal-accent); opacity: .7; }
.content-layout { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 48px; padding-top: 40px; padding-bottom: 70px; border-top: 1px solid var(--blog-border); }
.archive, .sidebar, #about { min-width: 0; scroll-margin-top: 95px; }
.archive-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 27px; }
.archive-eyebrow { font-size: 9px; }
.archive-heading h2 { margin: 6px 0 0; font-size: 27px; letter-spacing: -1px; line-height: 1.5; font-weight: 700; }
.heading-dot { color: var(--blog-accent); margin-left: 3px; }
.search-form { display: flex; align-items: center; gap: 9px; width: 224px; flex-shrink: 0; border: 1px solid var(--blog-border); border-radius: 6px; padding: 0 10px; background: var(--blog-surface); transition: border-color .15s ease; }
.search-form:focus-within { border-color: var(--blog-accent); }
.search-icon { width: 15px; flex-shrink: 0; color: var(--blog-muted); }
.search-form input { width: 100%; min-width: 0; height: 37px; padding: 0; border: none; outline: none; background: transparent; color: var(--blog-text); font-size: 11px; }
.search-form input::placeholder { color: var(--blog-muted); }
.search-form input:focus-visible { outline: none; }
.search-form button { display: flex; padding: 3px; background: none; border: none; color: var(--blog-muted); }
.search-form button:hover { color: var(--blog-accent); }
.search-form button svg { width: 15px; }
.category-filter { display: flex; flex-wrap: wrap; gap: 6px 19px; padding: 0 0 15px; margin-bottom: 17px; border-bottom: 1px solid var(--blog-border); }
.category-filter button { position: relative; padding: 5px 0; font-size: 12px; line-height: 1.6; border: none; color: var(--blog-muted); background: none; max-width: 100%; overflow-wrap: anywhere; }
.category-filter button:hover, .category-filter button.active { color: var(--blog-accent); }
.category-filter button.active { font-weight: 650; }
.category-filter button.active::after { position: absolute; content: ''; height: 2px; background: var(--blog-accent); bottom: -16px; left: 0; right: 0; }
.active-filters { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; margin: 0 0 17px; font-size: 11px; color: var(--blog-muted); overflow-wrap: anywhere; }
.active-filters > span { padding: 3px 7px; background: var(--blog-surface-alt); border-radius: 3px; max-width: 100%; }
.active-filters button { padding: 3px 0; border: none; background: transparent; color: var(--blog-accent); font-size: 11px; }
.active-filters button span { margin-left: 5px; }
.article-card { padding: 25px 0 26px; border-bottom: 1px solid var(--blog-border); }
.article-card:first-child { padding-top: 12px; }
.article-card.first-article { position: relative; margin-bottom: 5px; padding: 24px; background: var(--blog-surface); border: 1px solid var(--blog-border); border-radius: 8px; }
.first-article::before { content: ''; position: absolute; left: -1px; top: 24px; width: 2px; height: 25px; background: var(--blog-accent); }
.article-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-family: var(--blog-mono); color: var(--blog-muted); font-size: 10px; line-height: 1.6; margin-bottom: 11px; }
.article-category, .article-category-label { color: var(--blog-accent); font-family: inherit; font-size: 10px; line-height: 1.6; font-weight: 600; max-width: 100%; overflow-wrap: anywhere; }
.article-category { background: none; padding: 0; border: none; }
.article-category:hover { text-decoration: underline; text-underline-offset: 4px; }
.meta-divider { opacity: .5; }
.article-body { min-width: 0; }
.article-body.has-cover { display: grid; grid-template-columns: minmax(0, 1fr) 142px; gap: 23px; }
.article-copy { min-width: 0; }
.article-copy h3 { margin: 0; font-size: 20px; font-weight: 650; line-height: 1.55; letter-spacing: -.35px; overflow-wrap: anywhere; }
.first-article .article-copy h3 { font-size: 23px; }
.article-copy h3 a { text-decoration: none; color: var(--blog-text); transition: color .15s ease; }
.article-copy h3 a:hover { color: var(--blog-accent); }
.title-arrow { display: inline; vertical-align: -1px; width: 15px; margin-left: 10px; color: var(--blog-accent); opacity: 0; transition: opacity .15s ease, transform .15s ease; }
.article-copy h3 a:hover .title-arrow, .article-copy h3 a:focus-visible .title-arrow { opacity: 1; transform: translateX(2px); }
.article-summary { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin: 10px 0 0; color: var(--blog-muted); font-size: 12px; line-height: 1.95; overflow-wrap: anywhere; }
.article-cover { display: block; height: 102px; overflow: hidden; border: 1px solid var(--blog-border); border-radius: 5px; background: var(--blog-surface-alt); }
.article-cover img { display: block; width: 100%; height: 100%; object-fit: cover; transition: transform .25s ease; }
.article-cover:hover img { transform: scale(1.035); }
.article-footer { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-top: 20px; font-size: 10px; }
.article-tags { display: flex; flex-wrap: wrap; gap: 6px 12px; min-width: 0; }
.article-tags button { max-width: 100%; padding: 0; border: none; color: var(--blog-muted); background: none; font-family: var(--blog-mono); font-size: 10px; line-height: 1.6; overflow-wrap: anywhere; text-align: left; }
.article-tags button > span { margin-right: 3px; opacity: .65; }
.article-tags button:hover, .article-tags button.selected { color: var(--blog-accent); }
.article-byline { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; color: var(--blog-muted); margin-left: auto; min-width: 0; overflow-wrap: anywhere; }
.article-byline > span:first-child { max-width: 175px; overflow-wrap: anywhere; }
.byline-dot { opacity: .5; }
.view-count { display: inline-flex; align-items: center; gap: 4px; font-family: var(--blog-mono); }
.view-count svg { width: 13px; }
.archive-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px; padding: 25px 0 0; }
.article-total { font-size: 10px; color: var(--blog-muted); }
.archive-end { font-family: var(--blog-mono); font-size: 10px; color: var(--blog-muted); opacity: .7; }
.pagination { --el-pagination-bg-color: transparent; --el-pagination-button-disabled-bg-color: transparent; --el-pagination-hover-color: var(--blog-accent); --el-pagination-text-color: var(--blog-muted); --el-pagination-button-color: var(--blog-text); --el-pagination-button-disabled-color: var(--blog-muted); gap: 3px; }
.pagination :deep(.el-pager li) { border-radius: 4px; font-size: 11px; font-weight: 400; }
.pagination :deep(.el-pager li.is-active) { color: var(--blog-accent); background: var(--blog-accent-soft); font-weight: 600; }
.pagination :deep(button:disabled) { opacity: .4; }
.sidebar { border-left: 1px solid var(--blog-border); padding-left: 29px; }
.sidebar .eyebrow { font-size: 9px; letter-spacing: .85px; }
.about-symbol { width: 39px; height: 39px; display: flex; align-items: center; justify-content: center; font-family: var(--blog-mono); font-size: 20px; color: var(--blog-accent); background: var(--blog-accent-soft); border: 1px solid color-mix(in srgb, var(--blog-accent) 15%, transparent); border-radius: 8px; margin: 24px 0 16px; }
.about-card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 650; letter-spacing: -.3px; }
.about-card > p:not(.eyebrow) { color: var(--blog-muted); font-size: 11px; line-height: 2; margin: 0 0 11px; }
.about-signature { display: flex; gap: 8px; font-family: var(--blog-mono); font-size: 10px; color: var(--blog-accent); margin-top: 19px; }
.about-signature span { font-size: 15px; line-height: 1; }
.tag-index { margin-top: 35px; padding-top: 26px; border-top: 1px dashed var(--blog-border); }
.tag-index h2 { display: flex; align-items: center; justify-content: space-between; margin: 10px 0 17px; font-size: 14px; font-weight: 600; }
.tag-index h2 > span { font-family: var(--blog-mono); font-size: 16px; color: var(--blog-muted); }
.topic-tags { display: flex; flex-wrap: wrap; gap: 8px 6px; }
.topic-tags button { padding: 5px 8px; border: 1px solid var(--blog-border); border-radius: 4px; background: var(--blog-surface); color: var(--blog-muted); font-size: 10px; line-height: 1.5; text-align: left; max-width: 100%; overflow-wrap: anywhere; transition: color .15s ease, border-color .15s ease; }
.topic-tags button > span { font-family: var(--blog-mono); opacity: .65; }
.topic-tags button:hover, .topic-tags button.active { color: var(--blog-accent); border-color: var(--blog-accent); background: var(--blog-accent-soft); }
.taxonomy-error { margin-top: 28px; font-size: 11px; color: var(--blog-muted); line-height: 1.7; }
.taxonomy-error button { border: 0; padding: 0; background: none; color: var(--blog-accent); display: inline-flex; align-items: center; gap: 5px; font-size: 11px; }
.taxonomy-error button:disabled { cursor: wait; opacity: .6; }
.taxonomy-error svg { width: 12px; }
.sidebar-note { margin: 32px 0 0; font-size: 10px; line-height: 2; color: var(--blog-muted); opacity: .7; font-family: var(--blog-mono); }
.sidebar-note > span { opacity: .7; }
.empty-state { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 55px 18px 64px; border: 1px dashed var(--blog-border); border-radius: 7px; }
.empty-symbol { color: var(--blog-accent); font-size: 29px; font-family: var(--blog-mono); }
.empty-state h3 { font-size: 16px; margin: 20px 0 9px; font-weight: 600; }
.empty-state p { color: var(--blog-muted); font-size: 12px; line-height: 1.8; margin: 0; }
.state-action { display: inline-flex; align-items: center; gap: 8px; margin-top: 21px; border: 1px solid var(--blog-border); border-radius: 5px; padding: 9px 13px; color: var(--blog-accent); background: var(--blog-surface); font-size: 12px; }
.state-action:hover { border-color: var(--blog-accent); }
.state-action svg { width: 13px; }
.article-skeleton { padding-top: 10px; }
.skeleton-row { padding: 20px 0; border-bottom: 1px solid var(--blog-border); }
.skeleton-row i { display: block; height: 12px; width: 40%; border-radius: 3px; background: var(--blog-surface-alt); margin-bottom: 16px; animation: skeleton-pulse 1.3s ease-in-out infinite alternate; }
.skeleton-row i:nth-child(2) { width: 80%; height: 24px; }
.skeleton-row i:nth-child(3) { width: 95%; margin-bottom: 0; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@keyframes skeleton-pulse { from { opacity: .5; } to { opacity: 1; } }
@media (max-width: 1024px) {
  .hero { gap: 40px; }
  .terminal-content { padding: 22px 19px 17px; font-size: 10px; }
  .manifesto span { margin-right: 7px; }
  .content-layout { grid-template-columns: minmax(0, 1fr) 224px; gap: 30px; }
  .sidebar { padding-left: 23px; }
  .search-form { width: 190px; }
}
@media (max-width: 800px) {
  .hero { grid-template-columns: 1.05fr 1fr; gap: 26px; padding-top: 30px; min-height: 350px; }
  .hero-copy h1 { font-size: 40px; }
  .hero-description { font-size: 12px; }
  .hero-copy > .eyebrow { font-size: 8px; letter-spacing: .6px; }
  .terminal { transform: none; }
  .terminal-bar { padding: 11px 13px; }
  .terminal-content { padding: 19px 15px 14px; }
  .manifesto { letter-spacing: 0; }
  .manifesto p { font-size: 9px; letter-spacing: 0; }
  .content-layout { grid-template-columns: minmax(0, 1fr); gap: 46px; }
  .sidebar { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; border-left: 0; padding: 32px 0 0; border-top: 1px solid var(--blog-border); }
  .tag-index { margin-top: 0; padding-top: 0; border-top: 0; }
  .about-symbol { margin-top: 18px; }
  .sidebar-note { display: none; }
  .taxonomy-error { margin: 0; }
}
@media (max-width: 600px) {
  .hero::before { display: none; }
  .hero { grid-template-columns: 1fr; gap: 32px; padding: 28px 0 36px; }
  .hero-copy h1 { font-size: 42px; margin-top: 17px; }
  .hero-copy > .eyebrow { font-size: 9px; letter-spacing: .6px; }
  .hero-description { font-size: 13px; }
  .browse-link { margin-top: 20px; }
  .terminal { max-width: 440px; width: 100%; }
  .terminal-content { padding: 18px 21px 14px; font-size: 11px; }
  .terminal-comment { padding-top: 13px; }
  .manifesto { padding-top: 7px; padding-bottom: 12px; }
  .manifesto p { font-size: 10px; }
  .terminal-bar { padding: 11px 16px; }
  .content-layout { padding-top: 29px; padding-bottom: 40px; }
  .archive-heading { flex-wrap: wrap; gap: 20px; margin-bottom: 23px; }
  .archive-heading h2 { font-size: 25px; }
  .search-form { width: 100%; }
  .search-form input { font-size: 12px; height: 39px; }
  .category-filter { gap: 6px 18px; }
  .category-filter button { font-size: 11px; }
  .article-card.first-article { padding: 21px 18px; }
  .article-card { padding-top: 23px; padding-bottom: 23px; }
  .first-article .article-copy h3 { font-size: 21px; }
  .article-copy h3 { font-size: 19px; }
  .article-body.has-cover { grid-template-columns: minmax(0, 1fr) 90px; gap: 14px; }
  .article-cover { height: 82px; }
  .article-summary { margin-top: 7px; -webkit-line-clamp: 3; }
  .article-footer { margin-top: 16px; gap: 11px; }
  .article-byline { margin-left: 0; width: 100%; }
  .title-arrow { display: none; }
  .sidebar { grid-template-columns: 1fr; gap: 30px; }
  .about-card > p:not(.eyebrow) { font-size: 12px; }
  .tag-index { padding-top: 24px; border-top: 1px dashed var(--blog-border); }
  .archive-footer { gap: 12px; }
  .archive-end { font-size: 9px; }
  .pagination { margin-left: -9px; max-width: 100%; }
}
@media (max-width: 640px) {
  .blog-home { width: calc(100% - 40px); }
  .archive, #about { scroll-margin-top: 150px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
