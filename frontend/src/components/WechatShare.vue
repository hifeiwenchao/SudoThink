<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ChatDotRound, CopyDocument, Share, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { wechatApi } from '@/api/wechat'
import { createQrPng } from '@/utils/tools/qrcode'
import {
  buildWechatSharePayload,
  configureWechatShare,
  getSharePageUrl,
  isWeChatBrowser,
  loadWechatSdk,
} from '@/utils/wechatShare'

const props = defineProps<{
  title: string
  summary?: string
  cover?: string
  url?: string
}>()

const visible = ref(false)
const loading = ref(false)
const configured = ref(false)
const error = ref('')
const qrPng = ref('')
const inWeChat = computed(() => isWeChatBrowser())
const shareUrl = computed(() => getSharePageUrl(props.url?.trim() || (typeof window === 'undefined' ? '' : window.location.href)))
const payload = computed(() => buildWechatSharePayload({
  title: props.title,
  summary: props.summary,
  cover: props.cover,
  url: shareUrl.value,
}))

function generateQr() {
  try {
    qrPng.value = createQrPng(payload.value.link)
  } catch (cause) {
    qrPng.value = ''
    error.value = cause instanceof Error ? cause.message : '二维码生成失败，请复制链接后分享。'
  }
}

async function configureShare() {
  if (!inWeChat.value || configured.value || loading.value || !shareUrl.value) return
  loading.value = true
  error.value = ''
  try {
    const [sdk, signature] = await Promise.all([
      loadWechatSdk(),
      wechatApi.signature(shareUrl.value),
    ])
    await configureWechatShare(sdk, signature, payload.value)
    configured.value = true
  } catch (cause) {
    configured.value = false
    error.value = cause instanceof Error ? cause.message : '微信分享配置失败，请稍后重试。'
    generateQr()
  } finally {
    loading.value = false
  }
}

async function openShare() {
  visible.value = true
  error.value = ''
  if (!inWeChat.value) generateQr()
  else await configureShare()
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(payload.value.link)
    ElMessage.success('文章链接已复制')
  } catch {
    error.value = '复制失败，请手动复制下方链接。'
  }
}

onMounted(() => {
  if (inWeChat.value) void configureShare()
})
</script>

<template>
  <button class="wechat-share-button" type="button" aria-haspopup="dialog" @click="openShare">
    <Share aria-hidden="true" />
    <span>微信分享</span>
  </button>

  <el-dialog v-model="visible" title="微信分享" width="min(420px, calc(100vw - 32px))" append-to-body class="wechat-share-dialog">
    <div class="wechat-share-content">
      <template v-if="inWeChat">
        <div class="wechat-share-icon"><ChatDotRound aria-hidden="true" /></div>
        <h3>已准备好分享</h3>
        <p v-if="configured">请点击右上角菜单，选择“发送给朋友”或“分享到朋友圈”。</p>
        <p v-else-if="loading">正在配置微信分享…</p>
        <p v-else>微信分享配置未完成，请稍后重试或使用二维码分享。</p>
        <img v-if="qrPng" class="wechat-qr" :src="qrPng" alt="文章分享二维码" />
      </template>
      <template v-else>
        <p class="wechat-share-hint">请使用微信扫描二维码，然后点击右上角菜单分享给朋友或分享到朋友圈。</p>
        <img v-if="qrPng" class="wechat-qr" :src="qrPng" alt="文章分享二维码" />
        <div v-else class="wechat-qr-error"><WarningFilled aria-hidden="true" />{{ error || '二维码暂时无法生成' }}</div>
      </template>
      <p v-if="error && !qrPng" class="wechat-share-error" role="alert">{{ error }}</p>
      <div class="wechat-share-link">
        <span>{{ payload.link }}</span>
        <button type="button" title="复制文章链接" aria-label="复制文章链接" @click="copyLink"><CopyDocument aria-hidden="true" /></button>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.wechat-share-button { display: inline-flex; align-items: center; gap: 7px; padding: 0; border: 0; color: var(--blog-muted); background: transparent; font: inherit; font-size: 12px; cursor: pointer; transition: color .2s; }
.wechat-share-button:hover, .wechat-share-button:focus-visible { color: var(--blog-accent); }
.wechat-share-button:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 4px; border-radius: 4px; }
.wechat-share-button svg { width: 15px; height: 15px; }
.wechat-share-content { display: flex; flex-direction: column; align-items: center; color: var(--blog-text); text-align: center; }
.wechat-share-icon { display: flex; align-items: center; justify-content: center; width: 46px; height: 46px; margin-bottom: 14px; border: 1px solid var(--blog-border); border-radius: 50%; color: var(--blog-accent); background: var(--blog-surface-alt); }
.wechat-share-icon svg { width: 24px; height: 24px; }
.wechat-share-content h3 { margin: 0 0 9px; font-size: 17px; }
.wechat-share-content p { max-width: 300px; margin: 0; color: var(--blog-muted); font-size: 13px; line-height: 1.8; }
.wechat-qr { width: 210px; height: 210px; margin: 18px 0 8px; border: 1px solid var(--blog-border); border-radius: 6px; background: #fff; image-rendering: pixelated; }
.wechat-qr-error { display: flex; align-items: center; gap: 7px; margin: 24px 0; color: var(--el-color-danger); font-size: 13px; }
.wechat-qr-error svg { width: 16px; height: 16px; }
.wechat-share-error { margin-top: 11px !important; color: var(--el-color-danger) !important; }
.wechat-share-link { display: flex; align-items: center; gap: 7px; width: 100%; max-width: 340px; margin-top: 16px; padding: 8px 9px; border: 1px solid var(--blog-border); border-radius: 5px; color: var(--blog-muted); background: var(--blog-surface-alt); font: 10px var(--blog-mono); text-align: left; }
.wechat-share-link span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wechat-share-link button { display: inline-flex; flex: 0 0 auto; padding: 2px; border: 0; color: var(--blog-accent); background: transparent; cursor: pointer; }
.wechat-share-link button:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 2px; }
.wechat-share-link svg { width: 15px; height: 15px; }
</style>
