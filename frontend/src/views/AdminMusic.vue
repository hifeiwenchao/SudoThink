<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, ArrowUp, Delete, Upload } from '@element-plus/icons-vue'
import { musicApi, type MusicSettings, type MusicTrack } from '@/api/music'
import { uploadsApi } from '@/api/uploads'
import { uploadMedia, type UploadConfig } from '@/utils/mediaUpload'

const MAX_TRACKS = 100
const form = reactive<{ enabled: boolean; tracks: MusicTrack[] }>({ enabled: false, tracks: [] })
const loading = ref(false)
const loaded = ref(false)
const saving = ref(false)
const loadError = ref(false)
const saveError = ref('')
const validationError = ref('')
const uploadConfig = ref<UploadConfig | null>(null)
const configLoading = ref(false)
const configError = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadStatus = ref('')
const uploadErrors = ref<string[]>([])
const fileInput = ref<HTMLInputElement>()
const audioList = ref<HTMLElement>()
const snapshot = () => JSON.stringify(form)
const savedSnapshot = ref(snapshot())
const isDirty = computed(() => loaded.value && savedSnapshot.value !== snapshot())
const editable = computed(() => loaded.value && !loading.value && !saving.value)
const accept = computed(() => Object.values(uploadConfig.value?.audio_types ?? {}).flat().join(','))
const maxSize = computed(() => ((uploadConfig.value?.audio_max_bytes ?? 52428800) / 1024 / 1024).toLocaleString('zh-CN', { maximumFractionDigits: 1 }))
const saveStatus = computed(() => {
  if (loading.value) return '正在加载设置…'
  if (loadError.value) return '设置加载失败，请重试'
  if (saving.value) return '正在保存…'
  if (uploading.value) return '音频正在上传，已完成的曲目会保留在列表中'
  if (isDirty.value) return '有未保存的修改'
  return loaded.value ? '设置已同步' : '等待加载'
})
let active = true
let loadController: AbortController | null = null
let configController: AbortController | null = null
let uploadController: AbortController | null = null

function fill(data: MusicSettings) {
  form.enabled = data.enabled
  form.tracks = data.tracks.map(track => ({ ...track }))
  savedSnapshot.value = snapshot()
}

async function load() {
  if (loading.value || saving.value || uploading.value) return
  const controller = new AbortController()
  loadController = controller
  loading.value = true
  loadError.value = false
  try {
    const data = await musicApi.adminGet(controller.signal)
    if (!active || controller.signal.aborted) return
    fill(data)
    loaded.value = true
  } catch {
    if (active && !controller.signal.aborted) loadError.value = true
  } finally {
    if (active) loading.value = false
    if (loadController === controller) loadController = null
  }
}

async function loadUploadConfig() {
  if (configLoading.value) return
  const controller = new AbortController()
  configController = controller
  configLoading.value = true
  configError.value = false
  try {
    const data = await uploadsApi.config(controller.signal)
    if (active && !controller.signal.aborted) uploadConfig.value = data
  } catch {
    if (active && !controller.signal.aborted) configError.value = true
  } finally {
    if (active) configLoading.value = false
    if (configController === controller) configController = null
  }
}

async function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (!files.length || !editable.value || uploading.value || !uploadConfig.value?.enabled) return
  uploadErrors.value = []
  validationError.value = ''
  if (form.tracks.length + files.length > MAX_TRACKS) {
    uploadErrors.value = [`最多保留 ${MAX_TRACKS} 首音频，当前还能添加 ${MAX_TRACKS - form.tracks.length} 首。请减少选择数量。`]
    return
  }
  const controller = new AbortController()
  uploadController = controller
  uploading.value = true
  let completed = 0
  for (let index = 0; index < files.length; index++) {
    if (!active || controller.signal.aborted) break
    const file = files[index]!
    uploadProgress.value = 0
    uploadStatus.value = `正在上传 ${index + 1}/${files.length}：${file.name}`
    try {
      const result = await uploadMedia(file, {
        config: uploadConfig.value,
        kind: 'audio',
        signal: controller.signal,
        requestPolicy: uploadsApi.policy,
        onProgress: value => { if (active && !controller.signal.aborted) uploadProgress.value = value },
      })
      if (!active || controller.signal.aborted) break
      const title = file.name.replace(/\.[^.]+$/, '').trim().slice(0, 120) || '未命名音频'
      form.tracks.push({ title, artist: '', url: result.url })
      completed++
    } catch (error) {
      if (!active || controller.signal.aborted) break
      uploadErrors.value.push(`${file.name}：${error instanceof Error ? error.message : '上传失败，请重新选择文件重试'}`)
    }
  }
  if (active) {
    uploading.value = false
    uploadStatus.value = controller.signal.aborted
      ? `上传已取消，已完成的 ${completed} 首音频已保留，请保存设置。`
      : `本次上传完成 ${completed}/${files.length} 首，请保存设置后在前台播放。`
  }
  if (uploadController === controller) uploadController = null
}

function cancelUpload() {
  uploadController?.abort()
}

function move(index: number, delta: number) {
  if (!editable.value || uploading.value) return
  const destination = index + delta
  if (destination < 0 || destination >= form.tracks.length) return
  const track = form.tracks.splice(index, 1)[0]!
  form.tracks.splice(destination, 0, track)
}

function remove(index: number) {
  if (!editable.value || uploading.value) return
  form.tracks.splice(index, 1)
  validationError.value = ''
}

function pauseOtherPreviews(event: Event) {
  for (const audio of audioList.value?.querySelectorAll('audio') ?? []) {
    if (audio !== event.target) audio.pause()
  }
}

async function save() {
  if (!editable.value || uploading.value) return
  validationError.value = ''
  const tracks = form.tracks.map(track => ({ title: track.title.trim(), artist: track.artist.trim(), url: track.url }))
  if (tracks.some(track => !track.title || track.title.length > 120 || track.artist.length > 120)) {
    validationError.value = '请填写每首音频的曲名，曲名和歌手均不能超过 120 个字符。'
    return
  }
  saving.value = true
  saveError.value = ''
  try {
    const data = await musicApi.save({ enabled: form.enabled, tracks })
    if (!active) return
    fill(data)
    ElMessage.success('音乐设置已保存')
  } catch {
    if (active) saveError.value = '保存失败，已上传的音频和当前修改均已保留，请重试保存。'
  } finally {
    if (active) saving.value = false
  }
}

async function confirmLeave() {
  if (!isDirty.value && !uploading.value) return true
  try {
    await ElMessageBox.confirm(uploading.value ? '音频正在上传，离开会取消剩余上传，未保存的修改也会丢失。确定离开吗？' : '当前音乐设置尚未保存，离开后将丢失。确定离开吗？', '离开音乐设置', {
      confirmButtonText: '离开', cancelButtonText: '继续编辑', type: 'warning',
    })
    return true
  } catch { return false }
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value && !uploading.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(confirmLeave)
onMounted(() => {
  void load()
  void loadUploadConfig()
  window.addEventListener('beforeunload', beforeUnload)
})
onBeforeUnmount(() => {
  active = false
  loadController?.abort()
  configController?.abort()
  cancelUpload()
  window.removeEventListener('beforeunload', beforeUnload)
  for (const audio of audioList.value?.querySelectorAll('audio') ?? []) audio.pause()
})
</script>

<template>
  <div class="music-admin">
    <header class="page-heading">
      <div><h2>音乐设置</h2><p class="save-status" role="status">{{ saveStatus }}</p></div>
      <el-button type="primary" :loading="saving" :disabled="!editable || uploading" @click="save">保存设置</el-button>
    </header>

    <el-result v-if="loadError" icon="error" title="音乐设置加载失败" sub-title="请检查网络后重试。">
      <template #extra><el-button type="primary" :loading="loading" @click="load">重新加载</el-button></template>
    </el-result>
    <div v-else v-loading="loading">
      <section class="settings-panel visibility-panel" aria-label="音乐显示设置">
        <div><h3>网站音乐播放器</h3><p>访客可主动播放音乐并切换曲目，浏览站内页面时持续播放。没有音频时自动隐藏播放器。</p><p class="hint">上传或调整列表后，点击“保存设置”发布到前台；关闭后保留已上传的曲目。</p></div>
        <el-switch v-model="form.enabled" :disabled="!editable || uploading" active-text="启用播放器" aria-label="启用网站音乐播放器" />
      </section>
      <div v-if="saveError" class="save-error" role="alert">{{ saveError }}<el-button text type="primary" :disabled="!editable || uploading" @click="save">重试保存</el-button></div>

      <section class="settings-panel upload-panel" aria-label="上传音频">
        <div class="upload-heading"><h3>添加音乐</h3><span class="hint">{{ form.tracks.length }} / {{ MAX_TRACKS }} 首</span></div>
        <input ref="fileInput" class="file-input" type="file" multiple :accept="accept" :disabled="!editable || uploading || !uploadConfig?.enabled" tabindex="-1" aria-hidden="true" @change="selectFiles" />
        <div class="upload-actions">
          <el-button :icon="Upload" :loading="configLoading" :disabled="!editable || uploading || !uploadConfig?.enabled || form.tracks.length >= MAX_TRACKS" @click="fileInput?.click()">上传音频（可多选）</el-button>
          <el-button v-if="uploading" text type="danger" @click="cancelUpload">取消剩余上传</el-button>
        </div>
        <p v-if="configError" class="hint" role="alert">上传配置加载失败。<el-button text type="primary" :disabled="configLoading" @click="loadUploadConfig">重新加载</el-button></p>
        <p v-else-if="uploadConfig && !uploadConfig.enabled" class="hint">音频上传暂未启用，请配置 OSS 和 CDN 后重新加载。<el-button text type="primary" :disabled="configLoading" @click="loadUploadConfig">重新加载</el-button></p>
        <p v-else class="hint">支持 MP3、M4A、WAV、OGG，单个文件不超过 {{ maxSize }} MB，可一次选择多首。不同浏览器对音频编码的支持不同，推荐 MP3。</p>
        <el-progress v-if="uploading" :percentage="uploadProgress" :stroke-width="5" />
        <p v-if="uploadStatus" class="hint upload-status" role="status">{{ uploadStatus }}</p>
        <ul v-if="uploadErrors.length" class="upload-errors" role="alert"><li v-for="(error, index) in uploadErrors" :key="index">{{ error }}</li></ul>
      </section>

      <p v-if="validationError" class="save-error" role="alert">{{ validationError }}</p>
      <div ref="audioList" class="track-list">
        <el-empty v-if="loaded && !form.tracks.length" description="还没有音频，前台播放器将自动隐藏" :image-size="90" />
        <section v-for="(track, index) in form.tracks" :key="track.url" class="settings-panel track-card" :aria-label="`第 ${index + 1} 首：${track.title || '未命名音频'}`">
          <header class="track-heading"><strong class="track-number">{{ String(index + 1).padStart(2, '0') }}</strong><div class="track-actions">
            <el-button :icon="ArrowUp" :disabled="!editable || uploading || index === 0" :aria-label="`上移第 ${index + 1} 首音频`" title="上移" @click="move(index, -1)" />
            <el-button :icon="ArrowDown" :disabled="!editable || uploading || index === form.tracks.length - 1" :aria-label="`下移第 ${index + 1} 首音频`" title="下移" @click="move(index, 1)" />
            <el-button :icon="Delete" type="danger" plain :disabled="!editable || uploading" :aria-label="`移除第 ${index + 1} 首音频`" @click="remove(index)">移除</el-button>
          </div></header>
          <el-form label-position="top" :disabled="!editable || uploading" class="track-fields" @submit.prevent="save">
            <el-form-item label="曲名" required><el-input v-model="track.title" :maxlength="120" :aria-label="`第 ${index + 1} 首曲名`" placeholder="请输入曲名" /></el-form-item>
            <el-form-item label="歌手（选填）"><el-input v-model="track.artist" :maxlength="120" :aria-label="`第 ${index + 1} 首歌手`" placeholder="歌手或作者" /></el-form-item>
          </el-form>
          <audio controls preload="none" :src="track.url" :aria-label="`试听：${track.title || '未命名音频'}`" @play="pauseOtherPreviews">当前浏览器不支持音频播放。</audio>
        </section>
      </div>
      <p v-if="form.tracks.length" class="hint">移除曲目并保存后，前台播放列表会同步更新。</p>
    </div>
  </div>
</template>

<style scoped>
.music-admin { max-width: 1080px; min-width: 0; margin: 0 auto; }
.page-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; margin-bottom: 20px; }
.page-heading h2 { margin: 0; font-size: 24px; }
.save-status { margin: 8px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.settings-panel { min-width: 0; padding: 22px 24px; margin-bottom: 20px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--app-surface); }
.settings-panel h3 { margin: 0; font-size: 17px; }
.settings-panel p { margin: 9px 0 0; font-size: 13px; line-height: 1.7; color: var(--el-text-color-regular); }
.settings-panel .hint, .hint { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.visibility-panel { display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.visibility-panel > :deep(.el-switch) { flex: 0 0 auto; }
.upload-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
.file-input { display: none; }
.upload-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.upload-actions :deep(.el-button + .el-button), .track-actions :deep(.el-button + .el-button) { margin-left: 0; }
.upload-panel :deep(.el-progress) { margin-top: 16px; }
.upload-status, .upload-errors { overflow-wrap: anywhere; }
.upload-errors { padding-left: 20px; color: var(--el-color-danger); font-size: 13px; line-height: 1.8; }
.save-error { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; color: var(--el-color-danger); font-size: 13px; }
.track-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.track-list > :deep(.el-empty) { grid-column: 1 / -1; }
.track-card { margin: 0; }
.track-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 18px; }
.track-number { color: var(--el-text-color-secondary); font: 600 17px monospace; }
.track-actions { display: flex; align-items: center; gap: 7px; }
.track-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.track-fields :deep(.el-form-item) { min-width: 0; }
.track-card audio { display: block; width: 100%; max-width: 100%; height: 42px; }
@media (max-width: 1000px) { .track-list { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 640px) {
  .settings-panel { padding: 20px 18px; }
  .visibility-panel { flex-direction: column; align-items: flex-start; gap: 12px; }
  .track-fields { grid-template-columns: minmax(0, 1fr); gap: 0; }
}
</style>
