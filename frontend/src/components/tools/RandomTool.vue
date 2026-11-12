<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { generateRandomStrings, resolveRandomCharacters, type RandomStringOptions } from '@/utils/tools/random'

const options = reactive<RandomStringOptions>({
  length: 16, count: 10, lowercase: true, uppercase: true, digits: true, symbols: false,
  customCharacters: '', excludedCharacters: '', excludeSimilar: false,
  allowRepeatedCharacters: true, prefix: '', suffix: '',
})
const characterTypes = [
  { key: 'lowercase', label: '小写字母', example: 'a–z' },
  { key: 'uppercase', label: '大写字母', example: 'A–Z' },
  { key: 'digits', label: '数字', example: '0–9' },
  { key: 'symbols', label: '符号', example: '!@#$…' },
] as const
const result = ref<string[]>([])
const rule = ref('')
const error = ref('')
const resultText = computed(() => result.value.join('\n'))
const alphabetPreview = computed(() => {
  try {
    const characters = resolveRandomCharacters(options)
    return { text: characters.join(''), count: characters.length, message: '' }
  } catch (cause) {
    return { text: '', count: 0, message: cause instanceof Error ? cause.message : '请调整字符规则' }
  }
})

function clearResult() {
  result.value = []
  rule.value = ''
  error.value = ''
}

watch(options, clearResult, { flush: 'sync' })

function generate() {
  clearResult()
  try {
    const generated = generateRandomStrings(options)
    result.value = generated.values
    rule.value = generated.rule
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '生成失败，请检查输入后重试'
  }
}
</script>

<template>
  <form class="tool-stack" @submit.prevent="generate">
    <p class="tool-note">按你的字符规则批量生成随机字符串，所有生成操作均在当前浏览器完成。</p>
    <div class="tool-grid">
      <div class="tool-field">
        <label for="random-length">随机部分长度（1–256）</label>
        <input id="random-length" v-model.number="options.length" class="tool-input" type="number" min="1" max="256" step="1" aria-describedby="random-length-help">
      </div>
      <div class="tool-field">
        <label for="random-count">生成数量（1–100）</label>
        <input id="random-count" v-model.number="options.count" class="tool-input" type="number" min="1" max="100" step="1">
      </div>
    </div>
    <p id="random-length-help" class="tool-note">长度只计算随机部分，前后缀另加。中文和单个表情各计一个字符。</p>

    <fieldset class="random-character-types">
      <legend class="tool-label">字符类型</legend>
      <div class="random-character-grid">
        <label v-for="type in characterTypes" :key="type.key" class="random-character-option" :class="{ 'is-selected': options[type.key] }">
          <input :id="`random-${type.key}`" v-model="options[type.key]" type="checkbox">
          <span>{{ type.label }} <small>{{ type.example }}</small></span>
        </label>
      </div>
    </fieldset>
    <div class="tool-grid">
      <div class="tool-field">
        <label for="random-custom">追加自定义字符</label>
        <input id="random-custom" v-model="options.customCharacters" class="tool-input tool-code" type="text" maxlength="1024" autocomplete="off" spellcheck="false" placeholder="例如 abc甲乙🌍">
      </div>
      <div class="tool-field">
        <label for="random-excluded">排除指定字符</label>
        <input id="random-excluded" v-model="options.excludedCharacters" class="tool-input tool-code" type="text" maxlength="1024" autocomplete="off" spellcheck="false" placeholder="例如 abc123">
      </div>
    </div>
    <p class="tool-note">勾选的类型与自定义字符共同组成可用字符集，重复字符会合并；每个位置从中随机选取，不保证每种类型都会出现。自定义字符中请勿加入空白或不可见字符。</p>
    <div class="random-options">
      <label class="tool-check"><input id="random-exclude-similar" v-model="options.excludeSimilar" type="checkbox">排除易混淆字符（0 O o 1 I l）</label>
      <label class="tool-check"><input id="random-allow-repeated" v-model="options.allowRepeatedCharacters" type="checkbox">允许同一字符串内字符重复</label>
    </div>
    <div class="tool-field">
      <span class="tool-label">可用字符集 · {{ alphabetPreview.count }} 个字符</span>
      <p v-if="alphabetPreview.message" class="tool-note">{{ alphabetPreview.message }}</p>
      <pre v-else class="tool-output tool-code random-alphabet">{{ alphabetPreview.text }}</pre>
    </div>
    <div class="tool-grid">
      <div class="tool-field">
        <label for="random-prefix">固定前缀（可选）</label>
        <input id="random-prefix" v-model="options.prefix" class="tool-input tool-code" type="text" maxlength="64" autocomplete="off" spellcheck="false" placeholder="例如 user_">
      </div>
      <div class="tool-field">
        <label for="random-suffix">固定后缀（可选）</label>
        <input id="random-suffix" v-model="options.suffix" class="tool-input tool-code" type="text" maxlength="64" autocomplete="off" spellcheck="false" placeholder="例如 _test">
      </div>
    </div>
    <p class="tool-note">关闭字符重复时，随机部分长度不能超过可用字符数；前后缀不参与此限制，多条结果之间可能相同。</p>
    <div class="tool-actions">
      <button class="tool-button primary" type="submit">生成随机字符串</button>
      <CopyButton v-if="result.length" :text="resultText" label="复制全部结果" />
      <button v-if="result.length" class="tool-button" type="button" @click="clearResult">清空结果</button>
    </div>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <section v-if="result.length" class="tool-result" aria-live="polite" aria-label="随机字符串生成结果">
      <p class="tool-note">{{ rule }}</p>
      <pre class="tool-output random-result-output">{{ resultText }}</pre>
    </section>
  </form>
</template>

<style scoped>
.random-character-types { min-width: 0; margin: 0; padding: 0; border: 0; }
.random-character-types legend { margin-bottom: 12px; }
.random-character-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
.random-character-option { display: flex; align-items: center; gap: 8px; padding: 11px; border: 1px solid var(--blog-border); border-radius: 6px; font-size: 12px; cursor: pointer; }
.random-character-option.is-selected { border-color: var(--blog-accent); background: var(--blog-accent-soft); }
.random-character-option input { width: 14px; height: 14px; margin: 0; flex-shrink: 0; }
.random-character-option small { color: var(--blog-muted); font: 11px var(--blog-mono); }
.random-options { display: grid; gap: 12px; }
.random-options input { margin: 0; }
.random-alphabet { max-height: 130px; overflow: auto; }
.random-result-output { max-height: 420px; overflow: auto; }
</style>
