<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { previewCron } from '@/utils/tools/cron'
import { MAX_TIMESTAMP_INPUT_LENGTH } from '@/utils/tools/timestamp'

const expression = ref('*/15 * * * *')
const startTime = ref(new Date().toISOString())
const timezone = ref('local')
const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const error = ref('')
const result = ref<ReturnType<typeof previewCron> | null>(null)
const copyText = computed(() => result.value
  ? `${expression.value}\n${result.value.description}\n执行时区：${result.value.timezone}\n${result.value.times.map((time, index) => `${index + 1}. ${time.formatted} | ${time.iso}`).join('\n')}`
  : '')

watch([expression, startTime, timezone], () => { result.value = null; error.value = '' })

function preview() {
  error.value = ''
  result.value = null
  try {
    result.value = previewCron(expression.value, { startTime: startTime.value, timezone: timezone.value })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '解析失败，请检查输入'
  }
}

function fillNow() {
  startTime.value = new Date().toISOString()
}

function clear() {
  expression.value = ''
  result.value = null
  error.value = ''
}
</script>

<template>
  <div class="tool-stack">
    <p class="tool-note">标准 crontab 使用 5 个字段：分 时 日 月 星期。也支持 6 个字段：秒 分 时 日 月 星期；不包含年份字段。日与星期同时指定时，满足任一条件即可执行。</p>
    <form class="tool-stack" @submit.prevent="preview">
      <div class="tool-field">
        <label for="cron-expression">Cron 表达式</label>
        <input id="cron-expression" v-model="expression" class="tool-input tool-code" type="text" placeholder="*/15 * * * *" autocomplete="off" spellcheck="false" maxlength="256" aria-describedby="cron-expression-help">
      </div>
      <p id="cron-expression-help" class="tool-note">示例：*/15 * * * * 为每 15 分钟；0 9 * * 1 为每周一 09:00；*/20 * * * * * 为每 20 秒。星期 0 和 7 都代表周日。</p>
      <div class="tool-grid">
        <div class="tool-field">
          <label for="cron-start-time">开始时间（包含 Z 或 ±HH:mm）</label>
          <input id="cron-start-time" v-model="startTime" class="tool-input tool-code" type="text" placeholder="2026-11-10T12:00:00+08:00" autocomplete="off" spellcheck="false" aria-describedby="cron-time-help" :maxlength="MAX_TIMESTAMP_INPUT_LENGTH">
        </div>
        <div class="tool-field">
          <label for="cron-timezone">执行时区</label>
          <el-select id="cron-timezone" v-model="timezone" :teleported="false" filterable allow-create default-first-option>
            <el-option :label="`本地时区（${localZone}）`" value="local" />
            <el-option label="UTC" value="UTC" />
            <el-option label="Asia/Shanghai（上海）" value="Asia/Shanghai" />
            <el-option label="Asia/Tokyo（东京）" value="Asia/Tokyo" />
            <el-option label="America/New_York（纽约）" value="America/New_York" />
            <el-option label="Europe/London（伦敦）" value="Europe/London" />
          </el-select>
        </div>
      </div>
      <p id="cron-time-help" class="tool-note">从开始时间之后计算未来 10 次执行。表达式按所选时区匹配，并遵循其夏令时规则。时区支持搜索或输入 IANA 名称。</p>
      <div class="tool-actions">
        <button type="submit" class="tool-button primary">解析并预览</button>
        <button type="button" class="tool-button" @click="fillNow">开始时间设为现在</button>
        <button type="button" class="tool-button" @click="clear">清空表达式</button>
      </div>
    </form>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <section v-if="result" class="tool-result tool-stack" aria-live="polite" aria-label="Cron 解析结果">
      <div class="tool-actions"><strong>{{ result.description }}</strong><CopyButton :text="copyText" label="复制解析结果" /></div>
      <p class="tool-note">未来 10 次执行 · {{ result.timezone }}（同时列出 UTC 时间供核对）</p>
      <ol class="cron-times tool-code">
        <li v-for="time in result.times" :key="time.iso">
          <time :datetime="time.iso">{{ time.formatted }}</time>
          <span class="tool-note">UTC：{{ time.iso }}</span>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.cron-times { margin: 0; padding-left: 28px; }
.cron-times li { padding: 7px 0; overflow-wrap: anywhere; }
.cron-times .tool-note { display: block; margin: 4px 0 0; font-size: 12px; }
</style>
