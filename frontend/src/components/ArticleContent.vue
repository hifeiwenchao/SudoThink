<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { toArticleHtml } from '@/utils/articleContent'
import { enhanceArticle } from '@/utils/articleReader'
import '@/styles/article.css'

const props = defineProps<{ content: string }>()
const html = computed(() => toArticleHtml(props.content))
const prose = ref<HTMLElement | null>(null)
const dialog = ref<HTMLDialogElement | null>(null)
const preview = ref<{ src: string; alt: string } | null>(null)
let origin: HTMLImageElement | null = null
let cleanup: (() => void) | undefined
let version = 0

async function openPreview(image: HTMLImageElement) {
  origin = image
  preview.value = { src: image.getAttribute('src')!, alt: image.alt || '文章图片' }
  await nextTick()
  if (preview.value && dialog.value && !dialog.value.open) dialog.value.showModal()
}
function closePreview() {
  dialog.value?.close()
  preview.value = null
  if (origin?.isConnected) origin.focus({ preventScroll: true })
  origin = null
}
watch([html, prose], async () => {
  const current = ++version
  cleanup?.()
  closePreview()
  await nextTick()
  if (current === version && prose.value) cleanup = enhanceArticle(prose.value, openPreview)
}, { flush: 'post', immediate: true })
onBeforeUnmount(() => { version++; cleanup?.(); closePreview() })
</script>

<template>
  <div ref="prose" class="article-prose" v-html="html" />
  <dialog ref="dialog" class="article-image-dialog" aria-label="文章图片预览" @cancel.prevent="closePreview" @click="($event.target === dialog) && closePreview()">
    <template v-if="preview">
      <button type="button" class="article-preview-close" autofocus aria-label="关闭图片预览" @click="closePreview">关闭 <span aria-hidden="true">×</span></button>
      <img :src="preview.src" :alt="preview.alt" />
    </template>
  </dialog>
</template>

<style scoped>
.article-prose :deep(pre) { position: relative; padding-top: 3.4rem; }
.article-prose :deep(.article-code-copy) { position: absolute; top: .6rem; right: .7rem; padding: .3rem .65rem; border: 1px solid var(--blog-border); border-radius: 5px; background: var(--blog-surface); color: var(--blog-muted); font: 12px var(--blog-mono); cursor: pointer; }
.article-prose :deep(.article-code-copy:hover) { color: var(--blog-accent); }
.article-prose :deep(.article-preview-image) { cursor: zoom-in; }
.article-prose :deep(.article-preview-image:focus-visible), .article-prose :deep(.article-code-copy:focus-visible), .article-preview-close:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 4px; }
.article-image-dialog { box-sizing: border-box; max-width: 96vw; max-height: 94dvh; padding: 52px 16px 16px; border: 1px solid var(--blog-border); border-radius: 10px; background: var(--blog-surface); color: var(--blog-text); }
.article-image-dialog::backdrop { background: rgb(0 0 0 / .8); }
.article-image-dialog img { display: block; max-width: min(90vw, 1600px); max-height: calc(94dvh - 84px); object-fit: contain; }
.article-preview-close { position: absolute; top: 12px; right: 16px; border: 0; background: transparent; color: inherit; font-size: 14px; cursor: pointer; }
</style>
