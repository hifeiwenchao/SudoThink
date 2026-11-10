<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { taxonomyApi, type Category, type CategoryInput } from '@/api/taxonomy'

const list = ref<Category[]>([])
const loading = ref(false)
const loaded = ref(false)
const loadError = ref(false)
const operationError = ref('')
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const deletingId = ref<number | null>(null)
const saveError = ref('')
const form = reactive({ name: '', slug: '', description: '', weight: 0 as number | undefined })
const errors = reactive({ name: '', slug: '', description: '', weight: '' })
const busy = computed(() => loading.value || saving.value || deletingId.value !== null)
const canManage = computed(() => loaded.value && !loadError.value && !busy.value)

function clearErrors() {
  Object.assign(errors, { name: '', slug: '', description: '', weight: '' })
  saveError.value = ''
}

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = false
  try {
    list.value = await taxonomyApi.categories()
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
  Object.assign(form, { name: '', slug: '', description: '', weight: 0 })
  clearErrors()
  dialogVisible.value = true
}

function openEdit(category: Category) {
  if (!canManage.value) return
  editingId.value = category.id
  Object.assign(form, { name: category.name, slug: category.slug, description: category.description, weight: category.weight })
  clearErrors()
  dialogVisible.value = true
}

function validate() {
  clearErrors()
  const name = form.name.trim()
  if (!name) errors.name = '请填写分类名称'
  else if (name.length > 64) errors.name = '分类名称不能超过 64 个字符'
  if (form.slug.trim().length > 64) errors.slug = 'Slug 不能超过 64 个字符'
  if (form.description.trim().length > 255) errors.description = '描述不能超过 255 个字符'
  if (!Number.isInteger(form.weight) || form.weight === undefined || form.weight < 0 || form.weight > 999999) {
    errors.weight = '权重须为 0 至 999999 的整数'
  }
  return !Object.values(errors).some(Boolean)
}

async function save() {
  if (!canManage.value || !dialogVisible.value || !validate()) return
  saving.value = true
  const payload: CategoryInput = {
    name: form.name.trim(),
    description: form.description.trim(),
    weight: form.weight as number,
    ...(form.slug.trim() ? { slug: form.slug.trim() } : {}),
  }
  try {
    if (editingId.value === null) await taxonomyApi.create(payload)
    else await taxonomyApi.update(editingId.value, payload)
    dialogVisible.value = false
    operationError.value = ''
    ElMessage.success(editingId.value === null ? '分类已创建' : '分类已更新')
    await load()
  } catch {
    saveError.value = '保存失败，填写的内容已保留，请检查后重试。'
  } finally {
    saving.value = false
  }
}

async function remove(category: Category) {
  if (!canManage.value) return
  deletingId.value = category.id
  try {
    try {
      await ElMessageBox.confirm(`确定删除分类“${category.name}”？该分类下的文章会变为未分类，文章内容会保留。`, '删除分类', {
        confirmButtonText: '删除分类',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
    operationError.value = ''
    await taxonomyApi.remove(category.id)
    ElMessage.success('分类已删除')
    await load()
  } catch {
    operationError.value = '删除失败，请再次点击该分类的“删除”重试。'
  } finally {
    deletingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="categories-admin">
    <header class="page-heading">
      <div>
        <h2>分类管理</h2>
        <p>权重越大，分类在导航中越靠前；相同权重按创建顺序排列。</p>
      </div>
      <div class="page-actions">
        <el-button :loading="loading" :disabled="busy" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!canManage" @click="openCreate">新建分类</el-button>
      </div>
    </header>

    <div v-if="loadError" class="load-error" role="alert">
      <span>分类加载失败，请检查网络后重试。</span>
      <el-button type="primary" text :loading="loading" @click="load">重新加载</el-button>
    </div>
    <el-alert v-if="operationError" :title="operationError" type="error" :closable="false" show-icon class="operation-error" />

    <div class="table-panel">
      <el-table :data="list" v-loading="loading" stripe empty-text="暂无分类，点击“新建分类”添加" class="category-table">
        <el-table-column prop="weight" label="权重" width="90" />
        <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="slug" label="Slug" min-width="150" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip>
          <template #default="{ row }"><span :class="{ 'empty-description': !row.description }">{{ row.description || '未填写' }}</span></template>
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
      :title="editingId === null ? '新建分类' : '编辑分类'"
      width="min(540px, calc(100vw - 28px))"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      append-to-body
    >
      <el-form :model="form" :disabled="saving" label-position="top" @submit.prevent="save">
        <el-form-item label="名称" :error="errors.name" required>
          <el-input v-model="form.name" maxlength="64" show-word-limit placeholder="例如：技术笔记" @input="errors.name = ''" />
        </el-form-item>
        <el-form-item label="Slug（选填）" :error="errors.slug">
          <el-input v-model="form.slug" maxlength="64" placeholder="例如：technology" @input="errors.slug = ''" />
          <p class="field-hint">留空时由分类名称自动生成。</p>
        </el-form-item>
        <el-form-item label="描述（选填）" :error="errors.description">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="255" show-word-limit @input="errors.description = ''" />
        </el-form-item>
        <el-form-item label="排序权重" :error="errors.weight" required>
          <el-input-number v-model="form.weight" :min="0" :max="999999" :precision="0" controls-position="right" aria-label="分类排序权重" @change="errors.weight = ''" />
          <p class="field-hint">0 至 999999 的整数，数值越大越靠前。</p>
        </el-form-item>
        <p v-if="saveError" class="save-error" role="alert">{{ saveError }}</p>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="saving" @click="save">{{ saveError ? '重试保存' : '保存分类' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.categories-admin { min-width: 0; }
.page-heading { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 20px; }
.page-heading h2 { margin: 0; font-size: 24px; }
.page-heading p { margin: 8px 0 0; font-size: 13px; line-height: 1.7; color: var(--el-text-color-secondary); }
.page-actions { display: flex; flex-shrink: 0; }
.table-panel { min-width: 0; overflow: hidden; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--app-surface); }
.category-table { width: 100%; }
.empty-description, .field-hint { color: var(--el-text-color-secondary); }
.field-hint { width: 100%; margin: 6px 0 0; font-size: 12px; line-height: 1.7; }
.load-error { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 10px 16px; margin-bottom: 14px; border-radius: 6px; color: var(--el-color-danger); background: var(--el-color-danger-light-9); font-size: 13px; }
.operation-error { margin-bottom: 14px; }
.save-error { margin: 12px 0 0; color: var(--el-color-danger); font-size: 13px; line-height: 1.7; }
</style>
