<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { donationsApi, type DonationSettings, type DonationSettingsInput } from '@/api/donations'
import MediaUpload from '@/components/MediaUpload.vue'
import { isDonationQrUrl } from '@/utils/donations'

const channels = [
  { key: 'wechat_qr_url', label: '微信', mark: '微', className: 'wechat' },
  { key: 'alipay_qr_url', label: '支付宝', mark: '支', className: 'alipay' },
] as const
type QrField = typeof channels[number]['key']

const form = reactive<DonationSettingsInput>({ enabled: false, wechat_qr_url: '', alipay_qr_url: '' })
const loading = ref(false)
const loaded = ref(false)
const saving = ref(false)
const loadError = ref(false)
const saveError = ref('')
const enabledError = ref('')
const urlErrors = reactive<Record<QrField, string>>({ wechat_qr_url: '', alipay_qr_url: '' })
const uploadingFields = reactive<Record<QrField, boolean>>({ wechat_qr_url: false, alipay_qr_url: false })
const imageErrors = reactive<Record<QrField, boolean>>({ wechat_qr_url: false, alipay_qr_url: false })
const imageVersions = reactive<Record<QrField, number>>({ wechat_qr_url: 0, alipay_qr_url: 0 })
const updatedAt = ref<string | null>(null)
const snapshot = () => JSON.stringify(form)
const savedSnapshot = ref(snapshot())
const isDirty = computed(() => loaded.value && snapshot() !== savedSnapshot.value)
const uploading = computed(() => Object.values(uploadingFields).some(Boolean))
const editable = computed(() => loaded.value && !loading.value && !saving.value)
const previewUrls = computed(() => ({
  wechat_qr_url: isDonationQrUrl(form.wechat_qr_url.trim()) ? form.wechat_qr_url.trim() : '',
  alipay_qr_url: isDonationQrUrl(form.alipay_qr_url.trim()) ? form.alipay_qr_url.trim() : '',
}))
const saveStatus = computed(() => {
  if (loading.value) return '正在加载设置…'
  if (loadError.value) return '设置加载失败，请重试'
  if (saving.value) return '正在保存…'
  if (uploading.value) return '正在上传图片，请等待完成或取消…'
  if (isDirty.value) return '有未保存的修改'
  if (!loaded.value) return '等待加载'
  if (updatedAt.value) {
    const date = new Date(updatedAt.value)
    if (!Number.isNaN(date.getTime())) return `已保存于 ${date.toLocaleString('zh-CN')}`
  }
  return '设置已同步'
})
let active = true
let loadController: AbortController | null = null

function fill(data: DonationSettings) {
  form.enabled = data.enabled
  form.wechat_qr_url = data.wechat_qr_url
  form.alipay_qr_url = data.alipay_qr_url
  updatedAt.value = data.updated_at ?? null
  savedSnapshot.value = snapshot()
}

async function load() {
  if (loading.value || saving.value) return
  const controller = new AbortController()
  loadController = controller
  loading.value = true
  loadError.value = false
  try {
    const data = await donationsApi.adminGet(controller.signal)
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

function fieldChanged(field: QrField) {
  urlErrors[field] = ''
  enabledError.value = ''
}

function setImage(field: QrField, url: string) {
  form[field] = url
  fieldChanged(field)
}

function retryImage(field: QrField) {
  imageErrors[field] = false
  ++imageVersions[field]
}

function imageFailed(field: QrField, event: Event) {
  if ((event.target as HTMLImageElement).getAttribute('src') === previewUrls.value[field]) imageErrors[field] = true
}

function validate() {
  let valid = true
  for (const channel of channels) {
    const value = form[channel.key].trim()
    urlErrors[channel.key] = value && !isDonationQrUrl(value)
      ? '请填写不超过 2048 字符的完整 HTTP/HTTPS 图片地址，不能包含账号密码、空白、控制字符、反斜杠或片段（#）。'
      : ''
    if (urlErrors[channel.key]) valid = false
  }
  enabledError.value = form.enabled && !form.wechat_qr_url.trim() && !form.alipay_qr_url.trim()
    ? '启用打赏前，请至少添加一张收款码。'
    : ''
  return valid && !enabledError.value
}

async function save() {
  if (!editable.value || uploading.value || !validate()) return
  saving.value = true
  saveError.value = ''
  try {
    const data = await donationsApi.save({
      enabled: form.enabled,
      wechat_qr_url: form.wechat_qr_url.trim(),
      alipay_qr_url: form.alipay_qr_url.trim(),
    })
    if (!active) return
    fill(data)
    ElMessage.success('打赏设置已保存')
  } catch {
    if (active) saveError.value = '保存失败，当前设置和图片地址已保留，请重试。'
  } finally {
    if (active) saving.value = false
  }
}

async function confirmLeave() {
  if (!isDirty.value && !uploading.value) return true
  try {
    await ElMessageBox.confirm(uploading.value ? '图片正在上传，离开会取消上传，未保存的修改也会丢失。确定离开吗？' : '当前修改尚未保存，离开后将丢失。确定离开吗？', '离开打赏设置', {
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

for (const channel of channels) {
  watch(() => form[channel.key], () => retryImage(channel.key))
}
onBeforeRouteLeave(confirmLeave)
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  active = false
  loadController?.abort()
  window.removeEventListener('beforeunload', beforeUnload)
})
onMounted(load)
</script>

<template>
  <div class="donations-admin">
    <header class="page-heading">
      <div>
        <h2>打赏设置</h2>
        <p class="save-status" role="status">{{ saveStatus }}</p>
      </div>
      <el-button type="primary" :loading="saving" :disabled="!editable || uploading" @click="save">保存设置</el-button>
    </header>

    <el-result v-if="loadError" icon="error" title="打赏设置加载失败" sub-title="请检查网络后重试，成功加载后即可继续编辑。">
      <template #extra><el-button type="primary" :loading="loading" @click="load">重新加载</el-button></template>
    </el-result>
    <el-form v-else v-loading="loading" label-position="top" :disabled="!editable" class="settings-form" @submit.prevent="save">
      <div v-if="saveError" class="save-error" role="alert">
        <span>{{ saveError }}</span>
        <el-button text type="primary" :disabled="!editable || uploading" @click="save">重试保存</el-button>
      </div>

      <section class="visibility-panel" aria-label="打赏显示设置">
        <div class="visibility-copy">
          <h3>文章打赏</h3>
          <p>启用后，文章页会显示已保存的收款码。微信、支付宝可任选一种或同时设置。</p>
          <p class="field-hint">上传、预览和清除后，点击“保存设置”才会更新公开站点；关闭后保留已设置的图片地址。</p>
        </div>
        <el-form-item class="visibility-field" :error="enabledError">
          <el-switch v-model="form.enabled" active-text="启用打赏" aria-label="启用文章打赏" @change="enabledError = ''" />
        </el-form-item>
      </section>

      <div class="qr-grid">
        <section v-for="channel in channels" :key="channel.key" class="qr-card" :aria-labelledby="`${channel.key}-heading`">
          <header class="card-heading">
            <span class="channel-mark" :class="channel.className" aria-hidden="true">{{ channel.mark }}</span>
            <div>
              <h3 :id="`${channel.key}-heading`">{{ channel.label }}收款码</h3>
              <p>上传收款码图片，或填写可公开访问的图片地址。</p>
            </div>
          </header>

          <div class="preview-frame" :aria-label="`${channel.label}收款码预览`">
            <img v-if="previewUrls[channel.key] && !imageErrors[channel.key]" :key="imageVersions[channel.key]" :src="previewUrls[channel.key]" :alt="`${channel.label}收款码预览`" referrerpolicy="no-referrer" @error="imageFailed(channel.key, $event)" />
            <div v-else-if="imageErrors[channel.key]" class="preview-message" role="alert">
              <strong>图片加载失败</strong>
              <span>请检查图片地址和访问权限。</span>
              <el-button text type="primary" :disabled="!editable" @click="retryImage(channel.key)">重新加载图片</el-button>
            </div>
            <div v-else class="preview-message">
              <span>{{ form[channel.key].trim() ? '填写有效图片地址后显示预览' : '暂未设置收款码' }}</span>
            </div>
          </div>

          <MediaUpload kind="image" :disabled="!editable" @uploaded="setImage(channel.key, $event.url)" @uploading-change="uploadingFields[channel.key] = $event" />

          <el-form-item :label="`${channel.label}收款码图片地址`" :error="urlErrors[channel.key]" class="url-field">
            <el-input :id="channel.key" v-model="form[channel.key]" :disabled="uploadingFields[channel.key]" :maxlength="2048" placeholder="https://…" clearable @input="fieldChanged(channel.key)" />
          </el-form-item>
          <div class="card-footer">
            <span class="field-hint">支持 HTTP/HTTPS 图片地址，可含查询参数。</span>
            <el-button text type="danger" :disabled="!editable || uploadingFields[channel.key] || !form[channel.key]" @click="setImage(channel.key, '')">清除收款码</el-button>
          </div>
        </section>
      </div>
    </el-form>
  </div>
</template>

<style scoped>
.donations-admin { max-width: 1120px; min-width: 0; margin: 0 auto; }
.page-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; margin-bottom: 20px; }
.page-heading h2 { margin: 0; font-size: 24px; }
.save-status { margin: 8px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.settings-form { min-height: 180px; }
.visibility-panel { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 20px; padding: 22px 24px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--app-surface); }
.visibility-copy { min-width: 0; }
.visibility-copy h3, .card-heading h3 { margin: 0; color: var(--el-text-color-primary); font-size: 17px; }
.visibility-copy p { margin: 9px 0 0; color: var(--el-text-color-regular); font-size: 13px; line-height: 1.7; }
.visibility-copy .field-hint { color: var(--el-text-color-secondary); font-size: 12px; }
.visibility-field { flex: 0 0 auto; margin: 0; }
.visibility-field :deep(.el-form-item__error) { position: static; max-width: 190px; line-height: 1.6; }
.qr-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.qr-card { min-width: 0; padding: 24px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--app-surface); }
.card-heading { display: flex; align-items: flex-start; gap: 12px; }
.card-heading p { margin: 7px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.channel-mark { display: grid; place-items: center; flex: 0 0 38px; height: 38px; border-radius: 10px; font-size: 18px; font-weight: 600; }
.wechat { color: var(--el-color-success); background: var(--el-color-success-light-9); }
.alipay { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.preview-frame { display: flex; align-items: center; justify-content: center; width: min(100%, 272px); aspect-ratio: 1; margin: 24px auto; padding: 14px; box-sizing: border-box; border: 1px solid #e4e7ed; border-radius: 10px; background: #fff; color: #606266; overflow: hidden; }
.preview-frame img { display: block; width: 100%; height: 100%; object-fit: contain; filter: none; mix-blend-mode: normal; }
.preview-message { display: flex; flex-direction: column; align-items: center; gap: 10px; max-width: 100%; text-align: center; font-size: 13px; line-height: 1.7; }
.preview-message strong { color: #303133; font-weight: 500; }
.preview-message :deep(.el-button) { margin: 0; }
.url-field { margin-top: 20px; margin-bottom: 28px; }
.url-field :deep(.el-form-item__error) { position: static; line-height: 1.6; }
.card-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px 12px; }
.field-hint { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.card-footer :deep(.el-button) { margin-left: auto; }
.save-error { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; color: var(--el-color-danger); font-size: 13px; }
@media (max-width: 1000px) {
  .qr-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 640px) {
  .visibility-panel { flex-direction: column; align-items: stretch; padding: 20px 18px; }
  .visibility-field :deep(.el-form-item__error) { max-width: none; }
  .qr-card { padding: 20px 18px; }
  .preview-frame { width: min(100%, 252px); margin: 20px auto; }
}
</style>
