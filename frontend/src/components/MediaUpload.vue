<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import { uploadsApi } from '@/api/uploads'
import { uploadMedia, type UploadConfig, type UploadedMedia, type UploadKind } from '@/utils/mediaUpload'

const props = withDefaults(defineProps<{ kind: UploadKind; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ uploaded: [media: UploadedMedia]; 'uploading-change': [uploading: boolean] }>()
const fileInput = ref<HTMLInputElement>()
const config = ref<UploadConfig | null>(null)
const configLoading = ref(false)
const configError = ref(false)
const uploading = ref(false)
const percentage = ref(0)
const error = ref('')
const status = ref('')
const kindLabel = computed(() => props.kind === 'image' ? '图片' : '视频')
const acceptedTypes = computed(() => config.value ? (props.kind === 'image' ? config.value.image_types : config.value.video_types) : {})
const accept = computed(() => [...Object.keys(acceptedTypes.value), ...Object.values(acceptedTypes.value).flat()].join(','))
const maxSize = computed(() => {
  if (!config.value) return ''
  const bytes = props.kind === 'image' ? config.value.image_max_bytes : config.value.video_max_bytes
  return `${(bytes / 1024 / 1024).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} MB`
})
let active = true
let requestVersion = 0
let uploadController: AbortController | null = null
let configController: AbortController | null = null

function setUploading(value: boolean) {
  if (uploading.value === value) return
  uploading.value = value
  emit('uploading-change', value)
}

async function loadConfig() {
  configController?.abort()
  const controller = new AbortController()
  configController = controller
  configLoading.value = true
  configError.value = false
  try {
    const data = await uploadsApi.config(controller.signal)
    if (active && configController === controller) config.value = data
  } catch {
    if (active && !controller.signal.aborted && configController === controller) configError.value = true
  } finally {
    if (active && configController === controller) configLoading.value = false
  }
}

function cancelUpload() {
  ++requestVersion
  uploadController?.abort()
  uploadController = null
  if (uploading.value) status.value = '上传已取消'
  setUploading(false)
}

async function selectFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || props.disabled || uploading.value || !config.value?.enabled) return
  const version = ++requestVersion
  const controller = new AbortController()
  uploadController = controller
  percentage.value = 0
  error.value = ''
  status.value = '正在上传文件…'
  setUploading(true)
  const isCurrent = () => active && version === requestVersion && !controller.signal.aborted
  try {
    const result = await uploadMedia(file, {
      config: config.value,
      kind: props.kind,
      signal: controller.signal,
      requestPolicy: uploadsApi.policy,
      onProgress: (value) => { if (isCurrent()) percentage.value = value },
    })
    if (!isCurrent() || props.disabled) return
    status.value = '上传完成'
    setUploading(false)
    emit('uploaded', result)
  } catch (cause) {
    if (isCurrent()) {
      error.value = cause instanceof Error ? cause.message : '上传失败，请重试'
      status.value = ''
    }
  } finally {
    if (active && version === requestVersion) {
      uploadController = null
      setUploading(false)
    }
  }
}

watch(() => props.disabled, (disabled) => { if (disabled) cancelUpload() })
watch(() => props.kind, cancelUpload)
onMounted(loadConfig)
onBeforeUnmount(() => {
  active = false
  configController?.abort()
  cancelUpload()
})
</script>

<template>
  <div class="media-upload" :aria-busy="uploading">
    <input ref="fileInput" class="file-input" type="file" :accept="accept" :disabled="disabled || uploading || !config?.enabled" tabindex="-1" aria-hidden="true" @change="selectFile" />
    <div class="upload-actions">
      <el-button :loading="configLoading" :disabled="disabled || uploading || !config?.enabled" :icon="Upload" @click="fileInput?.click()">上传本地{{ kindLabel }}</el-button>
      <el-button v-if="uploading" text type="danger" @click="cancelUpload">取消上传</el-button>
    </div>
    <el-progress v-if="uploading" :percentage="percentage" :stroke-width="5" />
    <p v-if="configError" class="upload-hint" role="alert">上传配置加载失败，仍可使用资源地址。<el-button link type="primary" :disabled="disabled" @click="loadConfig">重试</el-button></p>
    <p v-else-if="config && !config.enabled" class="upload-hint">暂未启用本地上传，可继续填写资源地址。</p>
    <p v-else-if="config?.enabled && !uploading" class="upload-hint">{{ Object.values(acceptedTypes).flat().join(' / ').toUpperCase() }}，不超过 {{ maxSize }}。</p>
    <p v-if="status" class="upload-hint" role="status">{{ status }}</p>
    <p v-if="error" class="upload-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.media-upload { width: 100%; }
.file-input { display: none; }
.upload-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.upload-actions :deep(.el-button + .el-button) { margin-left: 0; }
.media-upload :deep(.el-progress) { margin-top: 12px; }
.upload-hint, .upload-error { margin: 8px 0 0; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.upload-hint { color: var(--el-text-color-secondary); }
.upload-error { color: var(--el-color-danger); }
</style>
