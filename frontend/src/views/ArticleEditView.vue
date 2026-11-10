<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { articleApi, type Article } from '@/api/article'
import { adminApi } from '@/api/admin'
import { taxonomyApi, type Category, type TaxonomyItem } from '@/api/taxonomy'
import RichTextEditor from '@/components/RichTextEditor.vue'
import ArticleContent from '@/components/ArticleContent.vue'
import { getArticleText, hasArticleContent, toArticleHtml } from '@/utils/articleContent'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const loadError = ref(false)
const submitting = ref<'draft' | 'publish' | null>(null)
const previewVisible = ref(false)
const currentArticleId = ref<number | null>(null)
const isPublished = ref(false)
const savedAt = ref('')
const categories = ref<Category[]>([])
const categoriesLoading = ref(false)
const categoriesError = ref(false)
const tags = ref<TaxonomyItem[]>([])
const originalTags = ref<TaxonomyItem[]>([])
const tagsLoading = ref(false)
const tagsError = ref(false)
const tagOptions = computed(() => {
  const options = new Map([...originalTags.value, ...tags.value].map((tag) => [tag.id, tag]))
  return [...options.values()]
})
const selectedTags = computed(() => tagOptions.value.filter((tag) => form.tag_ids.includes(tag.id)))
let loadRequestId = 0
const form = reactive({ title: '', summary: '', content: '', cover: '', category_id: null as number | null, tag_ids: [] as number[] })
const snapshot = () => JSON.stringify(form)
const savedSnapshot = ref(snapshot())
const isDirty = computed(() => snapshot() !== savedSnapshot.value)
const wordCount = computed(() => getArticleText(form.content).replace(/\s/g, '').length)
const readingMinutes = computed(() => Math.max(1, Math.ceil(wordCount.value / 300)))
const coverUrl = computed(() => /^https?:\/\//i.test(form.cover.trim()) ? form.cover.trim() : '')
const pageTitle = computed(() => currentArticleId.value ? '编辑文章' : '创作新文章')
const saveStatus = computed(() => {
  if (isDirty.value) return '有未保存的修改'
  if (savedAt.value) return `已保存于 ${savedAt.value}`
  return '开始记录你的想法'
})

function fillArticle(article: Article) {
  currentArticleId.value = article.id
  isPublished.value = article.is_published
  originalTags.value = article.tags
  Object.assign(form, {
    title: article.title,
    summary: article.summary || '',
    content: toArticleHtml(article.content),
    cover: article.cover || '',
    category_id: article.category?.id || null,
    tag_ids: article.tags.map((tag) => tag.id),
  })
  savedSnapshot.value = snapshot()
}

async function loadArticle() {
  const requestId = ++loadRequestId
  const id = route.params.id ? Number(route.params.id) : null
  const isCurrentRequest = () => requestId === loadRequestId
    && (route.params.id ? Number(route.params.id) : null) === id
  loadError.value = false
  if (!id) {
    loading.value = false
    currentArticleId.value = null
    isPublished.value = false
    savedAt.value = ''
    Object.assign(form, { title: '', summary: '', content: '', cover: '', category_id: null, tag_ids: [] })
    originalTags.value = []
    savedSnapshot.value = snapshot()
    return
  }
  if (id === currentArticleId.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const article = await adminApi.articleDetail(id)
    if (!isCurrentRequest()) return
    fillArticle(article)
    savedAt.value = ''
  } catch {
    if (isCurrentRequest()) loadError.value = true
  } finally {
    if (isCurrentRequest()) loading.value = false
  }
}

async function submit(publish: boolean) {
  if (submitting.value || loading.value || loadError.value) return
  if (!form.title.trim()) {
    ElMessage.warning('请先填写文章标题')
    return
  }
  if (!hasArticleContent(form.content)) {
    ElMessage.warning('请先填写文章正文')
    return
  }
  if (form.cover.trim() && !coverUrl.value) {
    ElMessage.warning('封面图请使用完整的 HTTP 或 HTTPS 图片地址')
    return
  }
  submitting.value = publish ? 'publish' : 'draft'
  const requestId = loadRequestId
  try {
    const payload = {
      title: form.title.trim(),
      summary: form.summary.trim(),
      content: toArticleHtml(form.content),
      cover: form.cover.trim(),
      is_published: publish,
      category_id: form.category_id,
      tag_ids: [...form.tag_ids],
    }
    const isNew = !currentArticleId.value
    const data = currentArticleId.value
      ? await articleApi.update(currentArticleId.value, payload)
      : await articleApi.create(payload)
    if (requestId !== loadRequestId) return
    fillArticle(data)
    savedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    ElMessage.success(publish ? '文章已发布' : '草稿已保存')
    if (isNew) await router.replace({ name: 'article-edit', params: { id: data.id } })
  } catch {
    // The shared HTTP interceptor displays the error; retain all entered content.
  } finally {
    submitting.value = null
  }
}

async function loadCategories() {
  categoriesLoading.value = true
  categoriesError.value = false
  try {
    categories.value = await taxonomyApi.categories()
  } catch {
    categoriesError.value = true
  } finally {
    categoriesLoading.value = false
  }
}

async function loadTags() {
  if (tagsLoading.value) return
  tagsLoading.value = true
  tagsError.value = false
  try {
    tags.value = await taxonomyApi.tags()
  } catch {
    tagsError.value = true
  } finally {
    tagsLoading.value = false
  }
}

async function confirmLeave() {
  if (!isDirty.value) return true
  try {
    await ElMessageBox.confirm('当前修改尚未保存，离开后将丢失。确定离开吗？', '离开编辑页', {
      confirmButtonText: '离开',
      cancelButtonText: '继续编辑',
      type: 'warning',
    })
    return true
  } catch {
    return false
  }
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to, from) => to.params.id === from.params.id ? true : confirmLeave())
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  ++loadRequestId
  window.removeEventListener('beforeunload', beforeUnload)
})
watch(() => route.params.id, loadArticle, { immediate: true })
onMounted(loadCategories)
onMounted(loadTags)
</script>

<template>
  <div class="article-workspace" v-loading="loading">
    <header class="workspace-header">
      <div class="heading">
        <el-button class="back-button" text :disabled="loading || !!submitting" @click="router.push('/admin/articles')">
          ← 文章管理
        </el-button>
        <div class="heading-title">
          <h1>{{ pageTitle }}</h1>
          <el-tag :type="isPublished ? 'success' : 'info'" effect="plain" round>
            {{ isPublished ? '已发布' : '草稿' }}
          </el-tag>
        </div>
        <p class="save-status" role="status"><span :class="{ dirty: isDirty }" />{{ saveStatus }}</p>
      </div>
      <div class="header-actions">
        <el-button :disabled="loading || loadError || !!submitting" @click="previewVisible = true">预览</el-button>
        <el-button
          :loading="submitting === 'draft'"
          :disabled="loading || loadError || submitting === 'publish'"
          @click="submit(false)"
        >{{ isPublished ? '转为草稿' : '保存草稿' }}</el-button>
        <el-button
          type="primary"
          :loading="submitting === 'publish'"
          :disabled="loading || loadError || submitting === 'draft'"
          @click="submit(true)"
        >{{ isPublished ? '更新文章' : '发布文章' }}</el-button>
      </div>
    </header>

    <el-result v-if="loadError" icon="error" title="文章加载失败" sub-title="请检查网络或返回文章管理后重试。">
      <template #extra><el-button type="primary" @click="loadArticle">重新加载</el-button></template>
    </el-result>
    <div v-else class="workspace-grid">
      <main class="writing-panel panel">
        <div class="title-field">
          <label for="article-title">文章标题 <span>*</span></label>
          <el-input
            id="article-title"
            v-model="form.title"
            class="title-input"
            placeholder="一个好标题，是故事的开始"
            maxlength="255"
            show-word-limit
            :disabled="loading || !!submitting"
          />
        </div>
        <div class="body-heading">
          <label>文章正文 <span>*</span></label>
          <span class="body-hint">让想法有条理地呈现</span>
        </div>
        <RichTextEditor v-model="form.content" :disabled="loading || !!submitting" />
        <footer class="writing-footer">
          <span>正文 {{ wordCount.toLocaleString() }} 字</span>
          <span>预计阅读 {{ readingMinutes }} 分钟</span>
        </footer>
      </main>

      <aside class="settings-column">
        <section class="panel settings-panel">
          <div class="section-heading"><h2>发布设置</h2><span>文章信息</span></div>
          <el-form :model="form" label-position="top" :disabled="loading || !!submitting">
            <el-form-item label="文章分类">
              <el-select v-model="form.category_id" aria-label="文章分类" placeholder="未分类" clearable :empty-values="[null, undefined]" :value-on-clear="null" :loading="categoriesLoading" :disabled="categoriesLoading || categoriesError" style="width: 100%">
                <el-option v-for="category in categories" :key="category.id" :label="category.name" :value="category.id" />
              </el-select>
              <p v-if="categoriesError" class="field-hint">分类加载失败。<el-button link type="primary" @click="loadCategories">重新加载</el-button></p>
              <p v-else class="field-hint">每篇文章最多选择一个分类；未选择时显示为未分类。</p>
            </el-form-item>
            <el-form-item label="文章标签">
              <el-select
                v-model="form.tag_ids"
                aria-label="文章标签"
                placeholder="选择标签，可多选"
                multiple
                filterable
                fit-input-width
                clearable
                :loading="tagsLoading"
                :disabled="tagsLoading || tagsError"
                style="width: 100%"
              >
                <el-option v-for="tag in tagOptions" :key="tag.id" :label="tag.name" :value="tag.id" />
              </el-select>
              <p v-if="tagsError" class="field-hint">标签加载失败，已有选择会保留。<el-button link type="primary" @click="loadTags">重新加载</el-button></p>
              <p v-else class="field-hint">可选择多个标签，在后台“标签管理”中维护。</p>
            </el-form-item>
            <el-form-item label="文章摘要">
              <el-input
                v-model="form.summary"
                type="textarea"
                :rows="5"
                maxlength="512"
                show-word-limit
                placeholder="用几句话介绍文章内容，方便读者快速了解。"
              />
              <p class="field-hint">选填，将显示在文章列表中。</p>
            </el-form-item>
            <el-form-item label="封面图片">
              <el-input v-model="form.cover" maxlength="512" placeholder="https://example.com/cover.jpg" clearable />
              <div v-if="coverUrl" class="cover-preview">
                <el-image :src="coverUrl" fit="cover" alt="文章封面预览">
                  <template #error><div class="cover-error">图片暂时无法加载</div></template>
                </el-image>
              </div>
              <p class="field-hint">选填，粘贴可公开访问的图片地址。</p>
            </el-form-item>
          </el-form>
        </section>
        <section class="publish-note">
          <span class="note-marker">✦</span>
          <div>
            <h3>准备好再与世界分享</h3>
            <p>草稿仅在管理后台可见。发布前可以预览正文排版，确认内容与图片展示效果。</p>
          </div>
        </section>
      </aside>
    </div>

    <el-dialog v-model="previewVisible" title="文章预览" class="article-preview-dialog" width="min(880px, calc(100vw - 32px))">
      <article class="article-preview">
        <div class="preview-label">{{ isPublished ? '已发布文章预览' : '草稿预览 · 尚未发布' }}</div>
        <h1>{{ form.title.trim() || '未命名文章' }}</h1>
        <p class="preview-meta">{{ wordCount.toLocaleString() }} 字 · 预计阅读 {{ readingMinutes }} 分钟</p>
        <div v-if="selectedTags.length" class="preview-tags" aria-label="预览文章标签">
          <el-tag v-for="tag in selectedTags" :key="tag.id" size="small" effect="plain">{{ tag.name }}</el-tag>
        </div>
        <p v-if="form.summary.trim()" class="preview-summary">{{ form.summary }}</p>
        <img v-if="coverUrl" class="preview-cover" :src="coverUrl" alt="文章封面" />
        <ArticleContent v-if="hasArticleContent(form.content)" :content="form.content" />
        <el-empty v-else description="还没有正文，开始写下你的想法吧" />
      </article>
    </el-dialog>
  </div>
</template>

<style scoped>
.article-workspace { max-width: 1320px; margin: 0 auto; padding: 4px 8px 32px; }
.workspace-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
.back-button { padding: 0; height: 24px; color: var(--el-text-color-secondary); font-size: 13px; margin-bottom: 12px; }
.heading-title { display: flex; align-items: center; gap: 12px; }
.heading-title h1 { margin: 0; color: var(--app-heading); font-size: 27px; font-weight: 650; letter-spacing: -.6px; }
.save-status { display: flex; align-items: center; gap: 6px; color: var(--el-text-color-secondary); font-size: 12px; margin: 10px 0 0; }
.save-status > span { width: 6px; height: 6px; background: var(--el-text-color-placeholder); border-radius: 50%; }
.save-status > .dirty { background: var(--el-color-warning); }
.header-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.header-actions :deep(.el-button + .el-button) { margin-left: 0; }
.header-actions :deep(.el-button) { height: 37px; padding: 0 18px; border-radius: 7px; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1fr) 290px; align-items: start; gap: 22px; }
.panel { background: var(--app-surface); border: 1px solid var(--el-border-color-lighter); border-radius: 12px; box-shadow: var(--el-box-shadow-lighter); }
.writing-panel { min-width: 0; overflow: hidden; }
.title-field { padding: 26px 26px 24px; border-bottom: 1px solid var(--el-border-color-lighter); }
.title-field label, .body-heading label { font-size: 13px; font-weight: 600; color: var(--el-text-color-regular); }
.title-field label span, .body-heading label span { color: var(--el-color-danger); padding-left: 3px; }
.title-input { margin-top: 13px; }
.title-input :deep(.el-input__wrapper) { padding: 0; box-shadow: none; }
.title-input :deep(.el-input__inner) { height: 44px; font-size: 24px; font-weight: 600; color: var(--app-heading); }
.title-input :deep(.el-input__inner::placeholder) { color: var(--el-text-color-placeholder); font-size: 22px; font-weight: 400; }
.title-input :deep(.el-input__count) { align-self: flex-end; padding-bottom: 2px; color: var(--el-text-color-secondary); }
.body-heading { padding: 22px 26px 16px; display: flex; justify-content: space-between; gap: 10px; align-items: center; }
.body-hint { color: var(--el-text-color-secondary); font-size: 12px; }
.writing-footer { border-top: 1px solid var(--el-border-color-lighter); padding: 13px 24px; display: flex; justify-content: space-between; color: var(--el-text-color-secondary); font-size: 12px; }
.settings-column { display: grid; gap: 16px; }
.settings-panel { padding: 22px; }
.section-heading { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; }
.section-heading h2 { margin: 0; font-size: 15px; color: var(--app-heading); }
.section-heading > span { color: var(--el-text-color-secondary); font-size: 11px; }
.settings-panel :deep(.el-form-item) { margin-bottom: 24px; }
.settings-panel :deep(.el-form-item:last-child) { margin-bottom: 0; }
.settings-panel :deep(.el-form-item__label) { color: var(--el-text-color-regular); font-size: 13px; }
.settings-panel :deep(.el-textarea__inner) { font-size: 13px; line-height: 1.8; padding: 10px 12px 24px; resize: vertical; }
.field-hint { margin: 8px 0 0; color: var(--el-text-color-secondary); line-height: 1.65; font-size: 12px; }
.cover-preview { width: 100%; margin-top: 12px; aspect-ratio: 16 / 9; border-radius: 7px; overflow: hidden; background: var(--app-surface-muted); }
.cover-preview :deep(.el-image) { width: 100%; height: 100%; }
.cover-error { display: grid; height: 100%; place-items: center; color: var(--el-text-color-secondary); font-size: 12px; }
.publish-note { display: flex; align-items: flex-start; gap: 12px; padding: 16px 17px; border: 1px solid var(--el-color-primary-light-8); border-radius: 10px; background: var(--el-color-primary-light-9); }
.note-marker { color: var(--el-color-primary); font-size: 21px; }
.publish-note h3 { color: var(--el-color-primary); font-size: 12px; margin: 3px 0 8px; font-weight: 600; }
.publish-note p { color: var(--el-text-color-regular); font-size: 12px; line-height: 1.85; margin: 0; }
.article-preview { max-width: 720px; margin: 0 auto; padding: 12px 18px 30px; overflow-wrap: anywhere; }
.preview-label { color: var(--el-text-color-secondary); font-size: 12px; letter-spacing: 1px; }
.article-preview h1 { font-size: 30px; line-height: 1.45; color: var(--app-heading); margin: 16px 0; }
.preview-meta { color: var(--el-text-color-secondary); font-size: 12px; margin-bottom: 30px; }
.preview-tags { display: flex; flex-wrap: wrap; gap: 8px; margin: -10px 0 24px; }
.preview-tags :deep(.el-tag) { max-width: 100%; height: auto; min-height: 24px; white-space: normal; }
.preview-tags :deep(.el-tag__content) { overflow-wrap: anywhere; }
.preview-summary { background: var(--app-quote-bg); border-left: 3px solid var(--el-color-primary); padding: 14px 18px; color: var(--app-quote-text); font-size: 14px; line-height: 1.8; margin-bottom: 26px; }
.preview-cover { display: block; width: 100%; max-height: 400px; object-fit: cover; border-radius: 8px; margin-bottom: 28px; }
@media (max-width: 1050px) {
  .workspace-grid { grid-template-columns: minmax(0, 1fr) 260px; gap: 16px; }
  .settings-panel { padding: 18px; }
}
@media (max-width: 800px) {
  .article-workspace { padding: 0 0 24px; }
  .workspace-header { align-items: flex-start; flex-direction: column; gap: 20px; }
  .header-actions { width: 100%; }
  .workspace-grid { grid-template-columns: minmax(0, 1fr); }
  .settings-column { grid-template-columns: minmax(0, 1fr); }
  .title-field { padding: 20px; }
  .body-heading { padding: 20px; }
  .body-hint { display: none; }
  .title-input :deep(.el-input__inner), .title-input :deep(.el-input__inner::placeholder) { font-size: 20px; }
  .article-preview { padding: 0 0 18px; }
}
</style>
