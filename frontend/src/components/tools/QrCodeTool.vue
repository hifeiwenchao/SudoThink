<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { createQrPng, readQrImage } from '@/utils/tools/qrcode'

const content = ref('')
const png = ref('')
const generationError = ref('')
const recognitionError = ref('')
const recognized = ref('')
const recognizedReady = ref(false)
const reading = ref(false)
const fileName = ref('')
const byteLength = computed(() => new TextEncoder().encode(content.value).length)
let readVersion = 0

watch(content, () => {
  png.value = ''
  generationError.value = ''
})

function generate() {
  png.value = ''
  generationError.value = ''
  try {
    png.value = createQrPng(content.value)
  } catch (error) {
    generationError.value = error instanceof Error ? error.message : '二维码生成失败，请缩短内容后重试。'
  }
}

async function readFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // Reset so selecting the same file again always emits change.
  input.value = ''
  if (!file) return
  const version = ++readVersion
  reading.value = true
  fileName.value = file.name
  recognized.value = ''
  recognizedReady.value = false
  recognitionError.value = ''
  try {
    const result = await readQrImage(file)
    if (version !== readVersion) return
    recognized.value = result
    recognizedReady.value = true
  } catch (error) {
    if (version !== readVersion) return
    recognitionError.value = error instanceof Error ? error.message : '图片读取失败，请重新选择图片。'
  } finally {
    if (version === readVersion) reading.value = false
  }
}

onBeforeUnmount(() => { readVersion++ })
</script>

<template>
  <div class="tool-stack">
    <p class="tool-note">生成和识别都在当前浏览器完成，内容与图片不会上传到服务器。</p>
    <div class="tool-grid">
      <section class="tool-stack" aria-labelledby="qr-generate-title">
        <h3 id="qr-generate-title">生成二维码</h3>
        <label class="tool-field" for="qr-content">
          <span>文本或链接</span>
          <textarea id="qr-content" v-model="content" class="tool-textarea" rows="6" maxlength="5000" placeholder="输入网址、中文或其他文本" spellcheck="false" />
        </label>
        <p class="tool-note">{{ byteLength }} / 2000 UTF-8 字节；中文通常占 3 字节。</p>
        <div class="tool-actions">
          <button class="tool-button primary" type="button" @click="generate">生成二维码</button>
          <a v-if="png" class="tool-button" :href="png" download="sudothink-qrcode.png">下载 PNG</a>
        </div>
        <p v-if="generationError" class="tool-error" role="alert">{{ generationError }}</p>
        <div v-if="png" class="qr-preview tool-result">
          <img :src="png" alt="根据输入内容生成的二维码" />
        </div>
      </section>

      <section class="tool-stack" aria-labelledby="qr-read-title" :aria-busy="reading">
        <h3 id="qr-read-title">识别图片中的二维码</h3>
        <label class="tool-field" for="qr-image">
          <span>选择本地图片</span>
          <input id="qr-image" class="tool-input" type="file" accept="image/*" @change="readFile" />
        </label>
        <p class="tool-note">支持浏览器可读取的图片，最大 10 MB、1600 万像素。建议使用 PNG、JPEG 或 WebP；每次读取一个二维码。</p>
        <p v-if="fileName" class="tool-note qr-file-name">{{ reading ? '正在识别：' : '已选择：' }}{{ fileName }}</p>
        <p v-if="recognitionError" class="tool-error" role="alert">{{ recognitionError }}</p>
        <div v-if="recognizedReady" class="tool-result tool-stack" aria-live="polite">
          <div class="tool-actions">
            <span>识别结果</span>
            <CopyButton :text="recognized" label="复制识别结果" />
          </div>
          <pre class="tool-output">{{ recognized || '（二维码内容为空）' }}</pre>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
h3 { margin: 0; font-size: 1rem; }
.qr-preview { display: flex; justify-content: center; padding: 1rem; background: #fff; border-radius: 0.75rem; }
.qr-preview img { width: min(100%, 320px); height: auto; image-rendering: pixelated; }
.qr-file-name { overflow-wrap: anywhere; }
</style>
