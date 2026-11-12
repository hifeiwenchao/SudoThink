<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aboutApi, type About } from '@/api/about'
import RichTextEditor from '@/components/RichTextEditor.vue'
import ArticleContent from '@/components/ArticleContent.vue'
import { getArticleText, hasArticleContent, toArticleHtml } from '@/utils/articleContent'

const form = reactive({ title: '关于我', content: '' })
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
  updatedAt.value = data.updated_at
  savedSnapshot.value = snapshot()
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
  saving.value = true
  saveError.value = ''
  try {
    const data = await aboutApi.save({ title, content: hasContent.value ? toArticleHtml(form.content) : '' })
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
@media (max-width: 640px) {
  .title-field { padding: 20px 18px 0; }
  .body-heading { padding: 0 18px 14px; }
  .writing-footer { padding: 14px 18px; }
  .save-error { margin: 14px 18px 0; }
  .about-preview { padding: 8px 4px 18px; }
}
</style>
