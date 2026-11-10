<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import { describeTimestamp, formatDateTime, formatTimestamp, MAX_TIMESTAMP_INPUT_LENGTH, parseDateTime, parseTimestamp, type DateZone, type TimestampUnit } from '@/utils/tools/timestamp'

const timestamp = ref('')
const unit = ref<TimestampUnit>('seconds')
const dateTime = ref(formatDateTime(Date.now(), 'local'))
const zone = ref<DateZone>('local')
const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const result = ref<ReturnType<typeof describeTimestamp> | null>(null)
const error = ref('')
const resultFields = computed(() => result.value ? [
  { label: '秒时间戳', text: result.value.seconds },
  { label: '毫秒时间戳', text: result.value.milliseconds },
  { label: 'UTC 日期时间（ISO 8601）', text: result.value.utc },
  { label: `本地日期时间（${localZone}）`, text: result.value.local },
] : [])

watch([timestamp, unit, dateTime, zone], () => { result.value = null; error.value = '' }, { flush: 'sync' })

function convert(direction: 'timestamp' | 'date') {
  error.value = ''
  result.value = null
  try {
    result.value = describeTimestamp(direction === 'timestamp' ? parseTimestamp(timestamp.value, unit.value) : parseDateTime(dateTime.value, zone.value))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '转换失败，请检查输入'
  }
}

function fillNow() {
  const now = Date.now()
  timestamp.value = formatTimestamp(now, unit.value)
  dateTime.value = formatDateTime(now, zone.value)
  result.value = describeTimestamp(now)
}

function clear() {
  timestamp.value = ''
  dateTime.value = ''
  error.value = ''
  result.value = null
}
</script>

<template>
  <div class="tool-stack">
    <p class="tool-note">Unix 时间戳以 1970-01-01 00:00:00 UTC 为起点，支持此前的负数时间。请选择输入单位和日期时区。</p>
    <div class="tool-grid">
      <form class="tool-stack" @submit.prevent="convert('timestamp')">
        <h2 class="tool-section-title">时间戳 → 日期</h2>
        <div class="tool-field">
          <label for="timestamp-value">时间戳</label>
          <input id="timestamp-value" v-model="timestamp" class="tool-input tool-code" type="text" inputmode="decimal" placeholder="例如：1700000000" autocomplete="off" spellcheck="false" :maxlength="MAX_TIMESTAMP_INPUT_LENGTH">
        </div>
        <div class="tool-field">
          <label for="timestamp-unit">时间戳单位</label>
          <el-select id="timestamp-unit" v-model="unit" :teleported="false">
            <el-option label="秒（可保留三位小数）" value="seconds" />
            <el-option label="毫秒（整数）" value="milliseconds" />
          </el-select>
        </div>
        <div class="tool-actions"><button type="submit" class="tool-button primary">转换为日期</button></div>
      </form>
      <form class="tool-stack" @submit.prevent="convert('date')">
        <h2 class="tool-section-title">日期 → 时间戳</h2>
        <div class="tool-field">
          <label for="timestamp-datetime">日期时间</label>
          <input id="timestamp-datetime" v-model="dateTime" class="tool-input tool-code" type="text" placeholder="2026-11-10 12:00:00.000" autocomplete="off" spellcheck="false" aria-describedby="timestamp-date-help" :maxlength="MAX_TIMESTAMP_INPUT_LENGTH">
        </div>
        <div class="tool-field">
          <label for="timestamp-zone">无时区偏移时，按此时区解释</label>
          <el-select id="timestamp-zone" v-model="zone" :teleported="false">
            <el-option :label="`本地时区（${localZone}）`" value="local" />
            <el-option label="UTC" value="utc" />
          </el-select>
        </div>
        <div class="tool-actions"><button type="submit" class="tool-button primary">转换为时间戳</button></div>
      </form>
    </div>
    <p id="timestamp-date-help" class="tool-note">日期格式：YYYY-MM-DD HH:mm:ss，秒和毫秒可省略。也支持 ISO 8601，例如 2026-11-10T12:00:00+08:00；带 Z 或偏移时按输入中的时区解释。每项输入最多 128 个字符（含空白）。</p>
    <div class="tool-actions">
      <button type="button" class="tool-button" @click="fillNow">填入当前时间</button>
      <button type="button" class="tool-button" @click="clear">清空</button>
    </div>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <section v-if="result" class="tool-result tool-stack" aria-live="polite" aria-label="时间转换结果">
      <div v-for="field in resultFields" :key="field.label" class="tool-field">
        <div class="tool-actions"><strong>{{ field.label }}</strong><CopyButton :text="field.text" :label="`复制${field.label}`" /></div>
        <pre class="tool-output tool-code">{{ field.text }}</pre>
      </div>
    </section>
  </div>
</template>

<style scoped>
.tool-section-title { margin: 0; font-size: 16px; font-weight: 650; }
</style>
