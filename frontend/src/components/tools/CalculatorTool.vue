<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { calculateExpression, formatCalculatorResult } from '@/utils/tools/calculator'

const expression = ref('')
const result = ref('')
const error = ref('')
const expressionInput = ref<HTMLInputElement | null>(null)
const keys = [
  { label: 'C', value: 'clear', aria: '清空表达式' },
  { label: '(', value: '(' }, { label: ')', value: ')' },
  { label: '⌫', value: 'backspace', aria: '删除光标前一个字符' },
  { label: '7', value: '7' }, { label: '8', value: '8' }, { label: '9', value: '9' }, { label: '÷', value: '/', aria: '除' },
  { label: '4', value: '4' }, { label: '5', value: '5' }, { label: '6', value: '6' }, { label: '×', value: '*', aria: '乘' },
  { label: '1', value: '1' }, { label: '2', value: '2' }, { label: '3', value: '3' }, { label: '−', value: '-', aria: '减或负号' },
  { label: '0', value: '0' }, { label: '.', value: '.' }, { label: '%', value: '%', aria: '取模（余数）' }, { label: '+', value: '+', aria: '加' },
]

watch(expression, () => { result.value = ''; error.value = '' }, { flush: 'sync' })

function calculate() {
  result.value = ''
  error.value = ''
  try {
    result.value = formatCalculatorResult(calculateExpression(expression.value))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法计算，请检查表达式'
  }
}

function clear() {
  expression.value = ''
  result.value = ''
  error.value = ''
  expressionInput.value?.focus()
}

async function press(value: string) {
  if (value === 'clear') { clear(); return }
  const input = expressionInput.value
  const start = input?.selectionStart ?? expression.value.length
  const end = input?.selectionEnd ?? expression.value.length
  const deletionStart = value === 'backspace' && start === end ? Math.max(0, start - 1) : start
  const inserted = value === 'backspace' ? '' : value
  const nextExpression = expression.value.slice(0, deletionStart) + inserted + expression.value.slice(end)
  if (nextExpression.length > 1024) { error.value = '表达式过长，最多输入 1024 个字符'; return }
  expression.value = nextExpression
  await nextTick()
  input?.focus()
  input?.setSelectionRange(deletionStart + inserted.length, deletionStart + inserted.length)
}

function onKeydown(event: KeyboardEvent) {
  if (event.isComposing) return
  const target = event.target
  if (target instanceof HTMLInputElement && target !== expressionInput.value) return
  if (target instanceof HTMLTextAreaElement) return
  if (event.key === 'Escape') { event.preventDefault(); clear(); return }
  if (event.key === 'Enter' && target === expressionInput.value) { event.preventDefault(); calculate(); return }
  // The expression input keeps native editing, selection and clipboard shortcuts.
  if (target === expressionInput.value || event.ctrlKey || event.metaKey || event.altKey) return
  if (/^[0-9.+\-*/%()]$/.test(event.key)) { event.preventDefault(); void press(event.key) }
  else if (event.key === 'Backspace') { event.preventDefault(); void press('backspace') }
}
</script>

<template>
  <div class="tool-stack" @keydown="onKeydown">
    <p class="tool-note">支持括号、小数、负数及科学计数法。输入表达式后按 Enter 计算，Escape 清空，Backspace 删除。</p>
    <div class="tool-field">
      <label for="calculator-expression">数学表达式</label>
      <input id="calculator-expression" ref="expressionInput" v-model="expression" class="tool-input tool-code calculator-expression" type="text" maxlength="1024" inputmode="text" autocomplete="off" spellcheck="false" placeholder="例如 (12 + 3) * 4 / 2">
    </div>
    <div class="calculator-keypad" aria-label="计算器按键">
      <button v-for="key in keys" :key="key.value" class="tool-button calculator-key" type="button" :aria-label="key.aria ?? key.label" :title="key.aria" @mousedown.prevent @click="press(key.value)">{{ key.label }}</button>
      <button class="tool-button primary calculator-equals" type="button" aria-label="计算结果" @click="calculate">=</button>
    </div>
    <p class="tool-note">% 表示取模（余数），例如 10 % 3 = 1，余数符号随被除数。采用双精度数值计算，结果显示最多 15 位有效数字。</p>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <section v-if="result !== ''" class="tool-result" aria-live="polite" aria-label="计算结果">
      <pre class="tool-output calculator-result">{{ result }}</pre>
      <CopyButton :text="result" label="复制计算结果" />
    </section>
  </div>
</template>

<style scoped>
.calculator-expression { font-size: 18px; }
.calculator-keypad { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; max-width: 480px; }
.calculator-key { min-height: 46px; font-size: 18px; }
.calculator-equals { grid-column: 1 / -1; min-height: 46px; font-size: 22px; }
.calculator-result { font-size: 24px; }
</style>
