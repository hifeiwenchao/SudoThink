<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aboutApi, type About, type CurrentProject } from '@/api/about'
import { articleApi } from '@/api/article'
import RichTextEditor from '@/components/RichTextEditor.vue'
import ArticleContent from '@/components/ArticleContent.vue'
import { getArticleText, hasArticleContent, toArticleHtml } from '@/utils/articleContent'
import { contactFields, isContactEmail, isContactUrl } from '@/utils/aboutContacts'

const form = reactive({ title: '关于我', content: '', github_url: '', email: '', x_url: '', facebook_url: '', instagram_url: '', featured_article_ids: [] as number[], current_projects: [] as CurrentProject[] })
const projectError = ref('')
const articleChoices = ref<{ id: number; title: string }[]>([])
const articleTitles = ref(new Map<number, string>())
const articleSearching = ref(false)
const articleSearchError = ref(false)
let articleSearchVersion = 0
const selectedFeatured = computed(() => form.featured_article_ids.map(id => ({ id, title: articleTitles.value.get(id) || `文章 #${id}` })))
const featuredOptions = computed(() => [...selectedFeatured.value, ...articleChoices.value.filter(item => !form.featured_article_ids.includes(item.id))])
const contactErrors = reactive<Record<string, string>>({})
const loading = ref(false)
const loaded = ref(false)
const saving = ref(false)
const uploading = ref(false)
const loadError = ref(false)
const saveError = ref('')
const titleError = ref('')
const previewVisible = ref(false)
const updatedAt = ref<string | null>(null)
const snapshot = () => JSON.stringify(form)
const savedSnapshot = ref(snapshot())
const isDirty = computed(() => loaded.value && snapshot() !== savedSnapshot.value)
const editable = computed(() => loaded.value && !loading.value && !saving.value)
const wordCount = computed(() => getArticleText(form.content).replace(/\s/g, '').length)
const hasContent = computed(() => hasArticleContent(form.content))
const saveStatus = computed(() => {
  if (loading.value) return '正在加载内容…'
  if (loadError.value) return '内容加载失败，请重试'
  if (saving.value) return '正在保存…'
  if (uploading.value) return '正在上传文件，请等待完成或取消…'
  if (isDirty.value) return '有未保存的修改'
  if (!loaded.value) return '等待加载'
  if (updatedAt.value) {
    const date = new Date(updatedAt.value)
    if (!Number.isNaN(date.getTime())) return `已保存于 ${date.toLocaleString('zh-CN')}`
  }
  return '内容已同步'
})
let active = true

function fill(data: About) {
  form.title = data.title
  form.content = toArticleHtml(data.content)
  for (const field of contactFields) form[field.key] = data[field.key] || ''
  form.featured_article_ids = [...(data.featured_article_ids || [])]
  form.current_projects = (data.current_projects || []).map(project => ({ ...project }))
  updatedAt.value = data.updated_at
  savedSnapshot.value = snapshot()
}

async function searchArticles(query: string) {
  const version = ++articleSearchVersion
  articleSearching.value = true
  articleSearchError.value = false
  try {
    const data = await articleApi.list({ page: 1, size: 20, q: query.trim() || undefined })
    if (!active || version !== articleSearchVersion) return
    articleChoices.value = data.items.map(({ id, title }) => ({ id, title }))
    for (const item of data.items) articleTitles.value.set(item.id, item.title)
  } catch {
    if (active && version === articleSearchVersion) articleSearchError.value = true
  } finally {
    if (active && version === articleSearchVersion) articleSearching.value = false
  }
}

async function loadFeaturedTitles() {
  try {
    const data = await aboutApi.sidebar()
    if (active) for (const item of data.featured_articles) articleTitles.value.set(item.id, item.title)
  } catch { /* Existing selections remain editable by ID when optional discovery fails. */ }
}

function moveFeatured(index: number, direction: number) {
  const destination = index + direction
  if (!editable.value || destination < 0 || destination >= form.featured_article_ids.length) return
  const ids = [...form.featured_article_ids]
  ;[ids[index], ids[destination]] = [ids[destination]!, ids[index]!]
  form.featured_article_ids = ids
}

function addProject() {
  if (!editable.value || form.current_projects.length >= 3) return
  form.current_projects.push({ name: '', description: '', url: '' })
  projectError.value = ''
}

function removeProject(index: number) {
  if (!editable.value) return
  form.current_projects.splice(index, 1)
  projectError.value = ''
}

async function load() {
  if (loading.value || saving.value) return
  loading.value = true
  loadError.value = false
  try {
    const data = await aboutApi.adminGet()
    if (!active) return
    fill(data)
    loaded.value = true
    void searchArticles('')
    void loadFeaturedTitles()
  } catch {
    if (active) loadError.value = true
  } finally {
    if (active) loading.value = false
  }
}

async function save() {
  if (!editable.value || uploading.value) return
  titleError.value = ''
  const title = form.title.trim()
  if (!title || title.length > 120) {
    titleError.value = !title ? '请填写页面标题' : '标题不能超过 120 个字符'
    return
  }
  let invalidContact = false
  for (const field of contactFields) {
    const value = form[field.key].trim()
    contactErrors[field.key] = value && !(field.key === 'email' ? isContactEmail(value) : isContactUrl(value))
      ? field.key === 'email' ? '请填写有效邮箱地址' : '请填写完整的 http:// 或 https:// 链接（不含账号密码）'
      : ''
    if (contactErrors[field.key]) invalidContact = true
  }
  if (invalidContact) return
  projectError.value = ''
  const projects = form.current_projects.map(project => ({ name: project.name.trim(), description: project.description.trim(), url: project.url.trim() }))
  if (projects.length > 3 || projects.some(project => !project.name || Array.from(project.name).length > 60 || Array.from(project.description).length > 160)) {
    projectError.value = '最多添加 3 个项目；名称必填且不超过 60 字，说明不超过 160 字。'
    return
  }
  if (projects.some(project => project.url && !isContactUrl(project.url))) {
    projectError.value = '项目链接请填写完整的 http:// 或 https:// 地址（不含账号密码），也可以留空。'
    return
  }
  saving.value = true
  saveError.value = ''
  try {
    const contacts = Object.fromEntries(contactFields.map(field => [field.key, form[field.key].trim()]))
    const data = await aboutApi.save({ title, content: hasContent.value ? toArticleHtml(form.content) : '', ...contacts, featured_article_ids: [...form.featured_article_ids], current_projects: projects })
    if (!active) return
    fill(data)
    ElMessage.success('关于我已保存')
  } catch {
    if (active) saveError.value = '保存失败，输入的内容已保留，请重试。'
  } finally {
    if (active) saving.value = false
  }
}

async function confirmLeave() {
  if (!isDirty.value && !uploading.value) return true
  try {
    await ElMessageBox.confirm(uploading.value ? '文件正在上传，离开会取消上传，未保存的修改也会丢失。确定离开吗？' : '当前修改尚未保存，离开后将丢失。确定离开吗？', '离开编辑页', {
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
  if (!isDirty.value && !uploading.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(confirmLeave)
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  active = false
  articleSearchVersion++
  window.removeEventListener('beforeunload', beforeUnload)
})
onMounted(load)
</script>

<template>
  <div class="about-admin">
    <header class="page-heading">
      <div>
        <h2>关于我</h2>
        <p class="save-status" role="status">{{ saveStatus }}</p>
      </div>
      <div class="page-actions">
        <el-button :disabled="!editable || uploading" @click="previewVisible = true">预览</el-button>
        <el-button type="primary" :loading="saving" :disabled="!editable || uploading" @click="save">保存内容</el-button>
      </div>
    </header>

    <el-result v-if="loadError" icon="error" title="关于我加载失败" sub-title="请检查网络后重试，成功加载后即可继续编辑。">
      <template #extra><el-button type="primary" :loading="loading" @click="load">重新加载</el-button></template>
    </el-result>
    <section v-else class="writing-panel" v-loading="loading" aria-label="关于我编辑区">
      <div v-if="saveError" class="save-error" role="alert">
        <span>{{ saveError }}</span>
        <el-button text type="primary" :disabled="!editable || uploading" @click="save">重试保存</el-button>
      </div>
      <el-form label-position="top" :disabled="!editable" @submit.prevent="save">
        <el-form-item class="title-field" label="页面标题" :error="titleError" required>
          <el-input id="about-title" v-model="form.title" maxlength="120" show-word-limit placeholder="关于我" @input="titleError = ''" />
        </el-form-item>
      </el-form>
      <section class="contact-settings" aria-labelledby="contact-heading">
        <h3 id="contact-heading">联系方式</h3>
        <p class="field-hint">保存后会公开显示在博客侧边栏；留空则隐藏对应入口。邮箱将对所有访客可见。</p>
        <el-form label-position="top" :disabled="!editable" @submit.prevent="save">
          <el-form-item v-for="field in contactFields" :key="field.key" :label="field.label" :error="contactErrors[field.key]">
            <el-input :id="`about-${field.key}`" v-model="form[field.key]" :placeholder="field.placeholder" :maxlength="field.key === 'email' ? 254 : 512" @input="contactErrors[field.key] = ''" />
          </el-form-item>
        </el-form>
      </section>
      <section class="sidebar-settings" aria-labelledby="sidebar-settings-heading">
        <h3 id="sidebar-settings-heading">首页侧栏</h3>
        <p class="field-hint">精选文章和正在折腾会显示在博客首页；未配置的模块自动隐藏。</p>
        <el-form label-position="top" :disabled="!editable" @submit.prevent="save">
          <el-form-item label="精选文章">
            <el-select id="featured-articles" v-model="form.featured_article_ids" multiple filterable remote :remote-method="searchArticles" :loading="articleSearching" :multiple-limit="5" placeholder="搜索已发布文章，最多选择 5 篇" aria-label="精选文章" style="width: 100%">
              <el-option v-for="item in featuredOptions" :key="item.id" :label="item.title" :value="item.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <p v-if="articleSearchError" class="field-hint" role="status">文章搜索暂不可用，已选内容仍会保留。<el-button text type="primary" :disabled="!editable" @click="searchArticles('')">重试</el-button></p>
        <ol v-if="selectedFeatured.length" class="featured-order" aria-label="精选展示顺序">
          <li v-for="(item, index) in selectedFeatured" :key="item.id">
            <span>{{ item.title }}</span>
            <div>
              <el-button text :disabled="!editable || index === 0" :aria-label="`上移精选文章 ${item.title}`" @click="moveFeatured(index, -1)">↑</el-button>
              <el-button text :disabled="!editable || index === selectedFeatured.length - 1" :aria-label="`下移精选文章 ${item.title}`" @click="moveFeatured(index, 1)">↓</el-button>
            </div>
          </li>
        </ol>
        <p class="field-hint">按上方顺序展示；文章改为草稿或移入回收站后自动隐藏。</p>
        <div class="projects-heading"><h4>正在折腾</h4><el-button :disabled="!editable || form.current_projects.length >= 3" @click="addProject">添加项目</el-button></div>
        <p class="field-hint">最多添加 3 条近期项目或研究方向；链接可留空。</p>
        <div v-for="(project, index) in form.current_projects" :key="index" class="project-settings">
          <div class="project-heading"><strong>项目 {{ index + 1 }}</strong><el-button text type="danger" :disabled="!editable" :aria-label="`移除项目 ${index + 1}`" @click="removeProject(index)">移除</el-button></div>
          <el-form label-position="top" :disabled="!editable" @submit.prevent="save">
            <el-form-item label="名称" required><el-input :id="`project-${index}-name`" v-model="project.name" maxlength="60" show-word-limit placeholder="例如：搭建自己的知识库" /></el-form-item>
            <el-form-item label="说明"><el-input :id="`project-${index}-description`" v-model="project.description" maxlength="160" type="textarea" :rows="2" show-word-limit placeholder="写一句最近的进展" /></el-form-item>
            <el-form-item label="链接"><el-input :id="`project-${index}-url`" v-model="project.url" maxlength="512" placeholder="https://…（可选）" /></el-form-item>
          </el-form>
        </div>
        <p v-if="projectError" role="alert" class="project-error">{{ projectError }}</p>
      </section>
      <div class="body-heading">
        <span>自我介绍</span>
        <span class="field-hint">保存后会显示在公开博客，留空表示暂未填写。</span>
      </div>
      <RichTextEditor v-model="form.content" :disabled="!editable" aria-label="关于我正文" @uploading-change="uploading = $event" />
      <footer class="writing-footer"><span>正文 {{ wordCount.toLocaleString() }} 字</span></footer>
    </section>

    <el-dialog v-model="previewVisible" title="关于我预览" width="min(860px, calc(100vw - 28px))" class="about-preview-dialog" append-to-body>
      <article class="about-preview">
        <h1>{{ form.title.trim() || '关于我' }}</h1>
        <ArticleContent v-if="hasContent" :content="form.content" />
        <p v-else class="empty-preview">暂未填写自我介绍。</p>
      </article>
    </el-dialog>
  </div>
</template>

<style scoped>
.about-admin { max-width: 1120px; min-width: 0; margin: 0 auto; }
.page-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; margin-bottom: 20px; }
.page-heading h2 { margin: 0; font-size: 24px; }
.save-status { margin: 8px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.page-actions { display: flex; align-items: center; }
.writing-panel { overflow: hidden; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--app-surface); }
.title-field { padding: 24px 28px 0; margin-bottom: 20px; }
.body-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; padding: 0 28px 14px; font-size: 14px; }
.field-hint { color: var(--el-text-color-secondary); font-size: 12px; }
.writing-footer { display: flex; padding: 14px 28px; color: var(--el-text-color-secondary); font-size: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.save-error { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 18px 28px 0; color: var(--el-color-danger); font-size: 13px; }
.about-preview { max-width: 740px; padding: 12px 20px 30px; margin: 0 auto; overflow-wrap: anywhere; }
.about-preview h1 { color: var(--app-heading); font-size: 30px; margin: 0 0 28px; line-height: 1.5; }
.empty-preview { color: var(--el-text-color-secondary); }
.contact-settings { padding: 20px 28px 8px; border-top: 1px solid var(--el-border-color-lighter); }
.contact-settings h3 { margin: 0 0 8px; font-size: 16px; }
.contact-settings > p { margin: 0 0 20px; line-height: 1.6; }
.contact-settings .el-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 20px; }
.sidebar-settings { padding: 24px 28px; margin-bottom: 24px; border-block: 1px solid var(--el-border-color-lighter); }
.sidebar-settings h3 { margin: 0 0 8px; font-size: 16px; }
.sidebar-settings .field-hint { line-height: 1.7; }
.featured-order { padding-left: 24px; margin: 12px 0; }
.featured-order li { padding-left: 4px; }
.featured-order li::marker { color: var(--el-text-color-secondary); font-size: 12px; }
.featured-order li > span { overflow-wrap: anywhere; }
.featured-order li > div { display: inline-flex; margin-left: 8px; }
.projects-heading, .project-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.projects-heading { margin-top: 24px; }
.projects-heading h4 { margin: 0; font-size: 14px; }
.project-settings { margin-top: 14px; padding: 12px 16px 0; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--el-fill-color-extra-light); }
.project-heading { margin-bottom: 12px; font-size: 13px; }
.project-error { color: var(--el-color-danger); font-size: 13px; }
@media (max-width: 640px) {
  .sidebar-settings { padding: 20px 18px; }
  .contact-settings { padding: 20px 18px 8px; }
  .contact-settings .el-form { grid-template-columns: 1fr; }
  .title-field { padding: 20px 18px 0; }
  .body-heading { padding: 0 18px 14px; }
  .writing-footer { padding: 14px 18px; }
  .save-error { margin: 14px 18px 0; }
  .about-preview { padding: 8px 4px 18px; }
}
</style>
