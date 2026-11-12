<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CoffeeCup, RefreshRight } from '@element-plus/icons-vue'
import { donationsApi } from '@/api/donations'
import { getDonationChannels, type DonationConfiguration, type DonationChannel } from '@/utils/donations'

const settings = ref<DonationConfiguration | null>(null)
const channels = computed(() => getDonationChannels(settings.value))
const selected = ref<DonationChannel['key']>('wechat')
const currentChannel = computed(() => channels.value.find(channel => channel.key === selected.value) || channels.value[0])
const visible = ref(false)
const imageFailed = ref(false)
const imageLoading = ref(true)
const imageVersion = ref(0)
const controller = new AbortController()

watch(() => currentChannel.value?.url, () => {
  imageFailed.value = false
  imageLoading.value = true
  imageVersion.value = 0
})

function retryImage() {
  imageFailed.value = false
  imageLoading.value = true
  imageVersion.value++
}

onMounted(async () => {
  try {
    const data = await donationsApi.get(controller.signal)
    if (!controller.signal.aborted) settings.value = data
  } catch {
    // The optional support entry stays hidden if settings cannot be loaded.
  }
})
onBeforeUnmount(() => controller.abort())
</script>

<template>
  <section v-if="channels.length" class="donation-panel" aria-label="支持作者">
    <div class="donation-copy">
      <span class="donation-eyebrow">SUPPORT THIS SPACE</span>
      <h2>如果这些文字对你有帮助</h2>
      <p>可以请我喝杯咖啡，支持下一次探索与分享。</p>
    </div>
    <button class="donation-button" type="button" @click="visible = true"><CoffeeCup aria-hidden="true" />打赏支持</button>
    <el-dialog v-model="visible" title="支持作者" width="min(420px, calc(100vw - 32px))" class="donation-dialog" append-to-body destroy-on-close>
      <div v-if="currentChannel" class="donation-content">
        <p class="donation-intro">感谢你的支持，每一份心意都是继续写作的动力。</p>
        <div v-if="channels.length > 1" class="donation-methods" role="group" aria-label="选择打赏方式">
          <button v-for="channel in channels" :key="channel.key" type="button" :class="{ active: currentChannel.key === channel.key }" :aria-pressed="currentChannel.key === channel.key" @click="selected = channel.key">{{ channel.label }}</button>
        </div>
        <div v-else class="donation-method-name">{{ currentChannel.label }}打赏</div>
        <div class="donation-qr" :aria-busy="imageLoading && !imageFailed">
          <template v-if="!imageFailed">
            <img :key="`${currentChannel.url}-${imageVersion}`" :src="currentChannel.url" :alt="`${currentChannel.label}收款码`" @load="imageLoading = false" @error="imageFailed = true; imageLoading = false" />
            <span v-if="imageLoading" class="donation-loading" role="status">正在加载收款码…</span>
          </template>
          <div v-else class="donation-image-error" role="alert"><span>收款码暂时无法加载</span><button type="button" @click="retryImage"><RefreshRight aria-hidden="true" />重试</button></div>
        </div>
        <p class="donation-scan">使用{{ currentChannel.label }}扫描收款码，自愿打赏。</p>
        <p class="donation-thanks">心意随喜，感谢阅读。</p>
      </div>
    </el-dialog>
  </section>
</template>

<style scoped>
.donation-panel { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 24px; margin-top: 48px; padding: 26px 28px; border: 1px solid var(--blog-border); border-radius: 10px; background: var(--blog-surface-alt); }
.donation-copy { min-width: 0; }
.donation-eyebrow { color: var(--blog-accent); font: 10px var(--blog-mono); letter-spacing: .12em; }
.donation-copy h2 { margin: 12px 0 8px; color: var(--blog-text); font-size: 17px; line-height: 1.6; font-weight: 600; }
.donation-copy p { margin: 0; color: var(--blog-muted); font-size: 13px; line-height: 1.8; }
.donation-button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; flex-shrink: 0; padding: 12px 18px; border: 1px solid var(--blog-accent); border-radius: 7px; color: var(--blog-accent); background: var(--blog-surface); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; transition: background .15s; }
.donation-button:hover { background: var(--blog-accent-soft); }
.donation-button svg { width: 17px; height: 17px; }
.donation-button:focus-visible, .donation-methods button:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 4px; }
.donation-content { text-align: center; }
.donation-intro { margin: 0 0 22px; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.8; }
.donation-methods { display: flex; gap: 4px; padding: 4px; margin: 0 auto 20px; max-width: 260px; border: 1px solid var(--el-border-color); border-radius: 8px; background: var(--el-fill-color-light); }
.donation-methods button { flex: 1; padding: 9px 14px; border: 0; border-radius: 5px; background: transparent; color: var(--el-text-color-regular); font: inherit; font-size: 13px; cursor: pointer; }
.donation-methods button.active { background: var(--el-bg-color); color: var(--el-color-primary); box-shadow: 0 1px 5px rgb(0 0 0 / .08); font-weight: 600; }
.donation-method-name { margin-bottom: 18px; color: var(--el-text-color-primary); font-weight: 600; }
.donation-qr { position: relative; display: grid; place-items: center; width: min(100%, 260px); min-height: 220px; margin: 0 auto; padding: 12px; border: 1px solid var(--el-border-color); border-radius: 8px; background: #fff; overflow: hidden; }
.donation-qr img { display: block; max-width: 100%; width: auto; max-height: 320px; object-fit: contain; }
.donation-loading { position: absolute; inset: 0; display: grid; place-items: center; background: #fff; color: #617368; font-size: 13px; }
.donation-image-error { display: flex; flex-direction: column; align-items: center; gap: 16px; color: #617368; font-size: 13px; }
.donation-image-error button { display: flex; align-items: center; gap: 6px; padding: 8px 14px; border: 1px solid #dce5de; border-radius: 5px; background: #f8faf8; color: #08764f; font: inherit; cursor: pointer; }
.donation-image-error svg { width: 14px; height: 14px; }
.donation-scan { margin: 18px 0 6px; font-size: 13px; color: var(--el-text-color-primary); }
.donation-thanks { margin: 0; color: var(--el-text-color-secondary); font-size: 12px; }
@media (max-width: 640px) {
  .donation-panel { align-items: flex-start; flex-direction: column; padding: 22px; gap: 18px; }
  .donation-button { width: 100%; }
}
</style>
