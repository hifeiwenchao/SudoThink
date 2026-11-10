<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { convertRadix, MAX_RADIX_INPUT_LENGTH } from '@/utils/tools/radix'

const input = ref('')
const base = ref(10)
const error = ref('')
const result = ref<ReturnType<typeof convertRadix> | null>(null)
const fields = computed(() => result.value ? [
  { label: '二进制（Base 2）', text: result.value.binary },
  { label: '八进制（Base 8）', text: result.value.octal },
  { label: '十进制（Base 10）', text: result.value.decimal },
  { label: '十六进制（Base 16）', text: result.value.hexadecimal },
] : [])
watch([input, base], () => { result.value = null; error.value = '' })

function convert() {
  result.value = null
  error.value = ''
  try {
    result.value = convertRadix(input.value, base.value)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '转换失败，请检查输入'
  }
}

function clear() {
  input.value = ''
  result.value = null
  error.value = ''
}
</script>

<template>
  <div class="tool-stack">
    <p class="tool-note">使用 BigInt 精确转换整数，支持负数和超过 JavaScript 安全整数范围的大数。</p>
    <form class="tool-stack" @submit.prevent="convert">
      <div class="tool-field">
        <label for="radix-base">输入进制</label>
        <el-select id="radix-base" v-model="base" :teleported="false">
          <el-option label="二进制（2）" :value="2" />
          <el-option label="八进制（8）" :value="8" />
          <el-option label="十进制（10）" :value="10" />
          <el-option label="十六进制（16）" :value="16" />
        </el-select>
      </div>
      <div class="tool-field">
        <label for="radix-input">待转换整数</label>
        <textarea id="radix-input" v-model="input" class="tool-textarea tool-code radix-input" rows="3" placeholder="例如：9007199254740993" autocomplete="off" spellcheck="false" aria-describedby="radix-help" :maxlength="MAX_RADIX_INPUT_LENGTH" />
      </div>
      <p id="radix-help" class="tool-note">可带 + / - 号，二、八、十六进制可分别带 0b、0o、0x 前缀，前缀须与输入进制一致。不支持小数、科学计数法或分隔符。输出不含前缀。</p>
      <p class="tool-note">最多 4096 个数位，符号和前缀不计入数位；输入总长最多 4099 个字符（含空白）。</p>
      <div class="tool-actions">
        <button type="submit" class="tool-button primary">转换进制</button>
        <button type="button" class="tool-button" @click="clear">清空</button>
      </div>
    </form>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <section v-if="result" class="tool-result tool-stack" aria-live="polite" aria-label="进制转换结果">
      <div v-for="field in fields" :key="field.label" class="tool-field">
        <div class="tool-actions"><strong>{{ field.label }}</strong><CopyButton :text="field.text" :label="`复制${field.label}`" /></div>
        <pre class="tool-output tool-code">{{ field.text }}</pre>
      </div>
    </section>
  </div>
</template>

<style scoped>
.radix-input { min-height: 100px; }
</style>
