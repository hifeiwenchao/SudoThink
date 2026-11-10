<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { generateRandomNumbers, type RandomOptions } from '@/utils/tools/random'

const options = reactive<RandomOptions>({
  min: '1', max: '100', count: 10, kind: 'integer', precision: 2,
  allowDuplicates: true, sort: 'none',
})
const result = ref<string[]>([])
const rule = ref('')
const error = ref('')
const resultText = computed(() => result.value.join(', '))

watch(options, () => {
  result.value = []
  rule.value = ''
  error.value = ''
})

function generate() {
  result.value = []
  rule.value = ''
  error.value = ''
  try {
    const generated = generateRandomNumbers(options)
    result.value = generated.values
    rule.value = generated.rule
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '生成失败，请检查输入后重试'
  }
}
</script>

<template>
  <form class="tool-stack" @submit.prevent="generate">
    <p class="tool-note">在指定范围内随机取数，包含最小值和最大值。所有生成操作均在当前浏览器完成。</p>
    <div class="tool-grid">
      <div class="tool-field">
        <label for="random-min">最小值</label>
        <input id="random-min" v-model="options.min" class="tool-input" type="text" inputmode="decimal" maxlength="64" autocomplete="off" placeholder="例如 1">
      </div>
      <div class="tool-field">
        <label for="random-max">最大值</label>
        <input id="random-max" v-model="options.max" class="tool-input" type="text" inputmode="decimal" maxlength="64" autocomplete="off" placeholder="例如 100">
      </div>
      <div class="tool-field">
        <label for="random-kind">数值类型</label>
        <el-select id="random-kind" v-model="options.kind" :teleported="false">
          <el-option label="整数" value="integer" />
          <el-option label="小数" value="decimal" />
        </el-select>
      </div>
      <div class="tool-field">
        <label for="random-count">生成数量</label>
        <input id="random-count" v-model.number="options.count" class="tool-input" type="number" min="1" max="1000" step="1">
      </div>
      <div class="tool-field">
        <label for="random-precision">小数位数（0–8）</label>
        <input id="random-precision" v-model.number="options.precision" class="tool-input" type="number" min="0" max="8" step="1" :disabled="options.kind === 'integer'">
      </div>
      <div class="tool-field">
        <label for="random-duplicates">是否允许重复</label>
        <el-select id="random-duplicates" v-model="options.allowDuplicates" :teleported="false">
          <el-option label="允许重复" :value="true" />
          <el-option label="不重复" :value="false" />
        </el-select>
      </div>
      <div class="tool-field">
        <label for="random-sort">结果排序</label>
        <el-select id="random-sort" v-model="options.sort" :teleported="false">
          <el-option label="保留生成顺序" value="none" />
          <el-option label="从小到大" value="ascending" />
          <el-option label="从大到小" value="descending" />
        </el-select>
      </div>
    </div>
    <p class="tool-note">支持普通十进制输入；端点的小数位数须符合所选精度。不重复模式按离散数值抽取，范围不足会提示。</p>
    <div class="tool-actions">
      <button class="tool-button primary" type="submit">生成随机数</button>
      <CopyButton v-if="result.length" :text="resultText" label="复制全部结果" />
    </div>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <section v-if="result.length" class="tool-result" aria-live="polite" aria-label="随机数生成结果">
      <p class="tool-note">{{ rule }}</p>
      <pre class="tool-output">{{ resultText }}</pre>
    </section>
  </form>
</template>
