<script setup lang="ts">
import { computed } from 'vue'
import { Monitor, Moon, Sunny } from '@element-plus/icons-vue'
import { useTheme } from '@/composables/useTheme'
import type { ThemePreference } from '@/utils/theme'

const { preference, setPreference } = useTheme()
const icon = computed(() => ({ system: Monitor, light: Sunny, dark: Moon })[preference.value])

function onChange(event: Event) {
  setPreference((event.target as HTMLSelectElement).value as ThemePreference)
}
</script>

<template>
  <label class="theme-switcher" title="外观模式">
    <el-icon aria-hidden="true"><component :is="icon" /></el-icon>
    <select aria-label="外观模式" :value="preference" @change="onChange">
      <option value="system">跟随系统</option>
      <option value="light">浅色模式</option>
      <option value="dark">深色模式</option>
    </select>
  </label>
</template>

<style scoped>
.theme-switcher {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 8px;
  box-sizing: border-box;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-blank);
  flex-shrink: 0;
}
.theme-switcher:hover { border-color: var(--el-color-primary); }
.theme-switcher:focus-within { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
select {
  min-height: 30px;
  padding: 0 2px;
  border: 0;
  outline: none;
  color: inherit;
  background: transparent;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
option { color: var(--el-text-color-primary); background: var(--el-bg-color-overlay); }
</style>
