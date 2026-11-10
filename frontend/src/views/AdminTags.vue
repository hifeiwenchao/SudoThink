<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { taxonomyApi, type Tag, type TagInput } from '@/api/taxonomy'

const list = ref<Tag[]>([])
const loading = ref(false)
const loaded = ref(false)
const loadError = ref(false)
const operationError = ref('')
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const deletingId = ref<number | null>(null)
const saveError = ref('')
const form = reactive({ name: '', slug: '' })
const errors = reactive({ name: '', slug: '' })
const busy = computed(() => loading.value || saving.value || deletingId.value !== null)
const canManage = computed(() => loaded.value && !loadError.value && !busy.value)

function clearErrors() {
  Object.assign(errors, { name: '', slug: '' })
  saveError.value = ''
}

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = false
  try {
    list.value = await taxonomyApi.tags()
    loaded.value = true
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function openCreate() {
  if (!canManage.value) return
  editingId.value = null
  Object.assign(form, { name: '', slug: '' })
  clearErrors()
  dialogVisible.value = true
}

function openEdit(tag: Tag) {
  if (!canManage.value) return
  editingId.value = tag.id
  Object.assign(form, { name: tag.name, slug: tag.slug })
  clearErrors()
  dialogVisible.value = true
}

function validate() {
  clearErrors()
  const name = form.name.trim()
  if (!name) errors.name = '请填写标签名称'
  else if (Array.from(name).length > 6) errors.name = '标签名称最多 6 个字符'
  if (form.slug.trim().length > 64) errors.slug = 'Slug 不能超过 64 个字符'
  return !Object.values(errors).some(Boolean)
}

async function save() {
  if (!canManage.value || !dialogVisible.value || !validate()) return
  saving.value = true
  const payload: TagInput = {
    name: form.name.trim(),
    ...(form.slug.trim() ? { slug: form.slug.trim() } : {}),
  }
  try {
    if (editingId.value === null) await taxonomyApi.createTag(payload)
    else await taxonomyApi.updateTag(editingId.value, payload)
    dialogVisible.value = false
    operationError.value = ''
    ElMessage.success(editingId.value === null ? '标签已创建' : '标签已更新')
    await load()
  } catch {
    saveError.value = '保存失败，填写的内容已保留，请检查后重试。'
  } finally {
    saving.value = false
  }
}

async function remove(tag: Tag) {
  if (!canManage.value) return
  deletingId.value = tag.id
  try {
    try {
      await ElMessageBox.confirm(`确定删除标签“${tag.name}”？文章会保留，仅移除文章与该标签的关联。`, '删除标签', {
        confirmButtonText: '删除标签',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
    operationError.value = ''
    await taxonomyApi.removeTag(tag.id)
    ElMessage.success('标签已删除')
    await load()
  } catch {
    operationError.value = '删除失败，请再次点击该标签的“删除”重试。'
  } finally {
    deletingId.value = null
  }
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('zh-CN')
}

onMounted(load)
</script>

<template>
  <div class="tags-admin">
    <header class="page-heading">
      <div>
        <h2>标签管理</h2>
        <p>一篇文章可添加多个标签，便于组织和查找相关内容。</p>
      </div>
      <div class="page-actions">
        <el-button :loading="loading" :disabled="busy" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!canManage" @click="openCreate">新建标签</el-button>
      </div>
    </header>

    <div v-if="loadError" class="load-error" role="alert">
      <span>标签加载失败，请检查网络后重试。</span>
      <el-button type="primary" text :loading="loading" @click="load">重新加载</el-button>
    </div>
    <el-alert v-if="operationError" :title="operationError" type="error" :closable="false" show-icon class="operation-error" />

    <div class="table-panel">
      <el-table :data="list" v-loading="loading" stripe empty-text="暂无标签，点击“新建标签”添加" class="tag-table">
        <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="slug" label="Slug" min-width="150" show-overflow-tooltip />
        <el-table-column label="创建日期" min-width="120">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :disabled="!canManage" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" :loading="deletingId === row.id" :disabled="!canManage" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新建标签' : '编辑标签'"
      width="min(540px, calc(100vw - 28px))"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      append-to-body
    >
      <el-form :model="form" :disabled="saving" label-position="top" @submit.prevent="save">
        <el-form-item label="名称" :error="errors.name" required>
          <el-input v-model="form.name" maxlength="6" show-word-limit placeholder="例如：Python" @input="errors.name = ''" />
        </el-form-item>
        <el-form-item label="Slug（选填）" :error="errors.slug">
          <el-input v-model="form.slug" maxlength="64" placeholder="例如：python" @input="errors.slug = ''" />
          <p class="field-hint">留空时由标签名称自动生成。</p>
        </el-form-item>
        <p v-if="saveError" class="save-error" role="alert">{{ saveError }}</p>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="saving" @click="save">{{ saveError ? '重试保存' : '保存标签' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tags-admin { min-width: 0; }
.page-heading { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 20px; }
.page-heading h2 { margin: 0; font-size: 24px; }
.page-heading p { margin: 8px 0 0; font-size: 13px; line-height: 1.7; color: var(--el-text-color-secondary); }
.page-actions { display: flex; flex-shrink: 0; }
.table-panel { min-width: 0; overflow: hidden; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--app-surface); }
.tag-table { width: 100%; }
.field-hint { width: 100%; margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.load-error { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 10px 16px; margin-bottom: 14px; border-radius: 6px; color: var(--el-color-danger); background: var(--el-color-danger-light-9); font-size: 13px; }
.operation-error { margin-bottom: 14px; }
.save-error { margin: 12px 0 0; color: var(--el-color-danger); font-size: 13px; line-height: 1.7; }
</style>
