<script setup lang="ts">
import { ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { transformJson, type JsonOperation } from '@/utils/tools/json'

const input = ref('')
const output = ref('')
const hasOutput = ref(false)
const outputLabel = ref('处理结果')
const indent = ref<2 | 4>(2)
const error = ref('')
const operationLabels: Record<JsonOperation, string> = {
  validate: '校验结果', format: '格式化结果', compact: '压缩结果',
  serialize: 'JSON 字符串（已转义）', deserialize: '还原后的文本',
}

function resetResult() {
  output.value = ''
  hasOutput.value = false
  error.value = ''
}

watch(input, resetResult, { flush: 'sync' })

function run(operation: JsonOperation) {
  resetResult()
  try {
    output.value = transformJson(input.value, operation, indent.value)
    outputLabel.value = operationLabels[operation]
    hasOutput.value = true
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '处理失败，请检查输入内容'
  }
}

function fillExample() {
  input.value = '{"网站":"SudoThink","语言":["中文","English"],"公开":true,"备注":null}'
}

function clear() {
  input.value = ''
  resetResult()
}
</script>

<template>
  <div class="tool-stack">
    <p class="tool-note">校验、格式化或压缩 JSON，也可以将任意文本转为 JSON 字符串。内容仅在当前浏览器处理。</p>
    <div class="tool-field">
      <label for="json-input">输入内容</label>
      <textarea id="json-input" v-model="input" class="tool-textarea tool-code" rows="10" maxlength="1000001" spellcheck="false" placeholder='粘贴 JSON，例如 {"message":"你好","items":[1,null]}' />
      <span class="tool-note">{{ input.length.toLocaleString() }} / 1,000,000 个字符</span>
    </div>
    <div class="tool-field json-indent">
      <label for="json-indent">格式化缩进</label>
      <el-select id="json-indent" v-model="indent" :teleported="false">
        <el-option label="2 个空格" :value="2" />
        <el-option label="4 个空格" :value="4" />
      </el-select>
    </div>
    <div class="tool-actions">
      <button class="tool-button primary" type="button" @click="run('format')">格式化</button>
      <button class="tool-button" type="button" @click="run('validate')">校验</button>
      <button class="tool-button" type="button" @click="run('compact')">压缩</button>
      <button class="tool-button" type="button" @click="fillExample">填入示例</button>
      <button class="tool-button" type="button" @click="clear">清空</button>
    </div>
    <div class="tool-actions">
      <button class="tool-button" type="button" @click="run('serialize')">文本 → JSON 字符串（转义）</button>
      <button class="tool-button" type="button" @click="run('deserialize')">JSON 字符串 → 文本（还原）</button>
    </div>
    <p class="tool-note">“转义”会为整段文本添加引号并转义换行、引号和反斜杠；“还原”要求输入带引号的 JSON 字符串。格式化和压缩会保留长整数及高精度小数。</p>
    <p class="tool-note">最多处理 128 层嵌套，输出上限为 2,000,000 个字符；缩进后内容过大时可尝试压缩。</p>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <section v-if="hasOutput" class="tool-result" aria-live="polite" :aria-label="outputLabel">
      <div class="tool-actions">
        <span>{{ outputLabel }}</span>
        <CopyButton :text="output" label="复制结果" />
      </div>
      <pre class="tool-output tool-code">{{ output || '（空文本）' }}</pre>
    </section>
  </div>
</template>

<style scoped>
.json-indent { width: min(240px, 100%); }
</style>
