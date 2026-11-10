<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Check, CopyDocument } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{ text: string; label?: string }>(), { label: '复制结果' })
const copied = ref(false)
const error = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let copyVersion = 0

function fallbackCopy(text: string) {
  const focused = document.activeElement as HTMLElement | null
  const input = document.createElement('textarea')
  input.value = text
  input.readOnly = true
  input.tabIndex = -1
  input.setAttribute('aria-hidden', 'true')
  Object.assign(input.style, { position: 'fixed', left: '-9999px', top: '0' })
  document.body.append(input)
  try {
    input.focus()
    input.select()
    if (!document.execCommand('copy')) throw new Error('Copy unavailable')
  } finally {
    input.remove()
    focused?.focus({ preventScroll: true })
  }
}

async function copy() {
  const version = ++copyVersion
  const text = props.text
  clearTimeout(timer)
  copied.value = false
  error.value = ''
  try {
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(text) }
      catch {
        if (version !== copyVersion) return
        fallbackCopy(text)
      }
    } else {
      fallbackCopy(text)
    }
    if (version !== copyVersion) return
    copied.value = true
    timer = setTimeout(() => { copied.value = false }, 2000)
  } catch {
    if (version === copyVersion) error.value = '无法自动复制，请选中结果后手动复制。'
  }
}
watch(() => props.text, () => { copyVersion++; clearTimeout(timer); copied.value = false; error.value = '' })
onBeforeUnmount(() => { copyVersion++; clearTimeout(timer) })
</script>

<template>
  <span class="tool-copy">
    <button type="button" class="tool-button tool-copy-button" :disabled="!text" @click="copy">
      <el-icon aria-hidden="true"><Check v-if="copied" /><CopyDocument v-else /></el-icon>{{ copied ? '已复制' : label }}
    </button>
    <span v-if="error" class="tool-error" role="alert">{{ error }}</span>
    <span class="tool-sr-only" role="status">{{ copied ? '已复制到剪贴板' : '' }}</span>
  </span>
</template>
