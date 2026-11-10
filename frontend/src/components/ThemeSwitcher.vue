<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDown, Check, Monitor, Moon, Sunny } from '@element-plus/icons-vue'
import { useTheme } from '@/composables/useTheme'
import type { ThemePreference } from '@/utils/theme'

const { preference, setPreference } = useTheme()
const options = [
  { value: 'system', label: '跟随系统', icon: Monitor },
  { value: 'light', label: '浅色模式', icon: Sunny },
  { value: 'dark', label: '深色模式', icon: Moon },
] as const
const selectedOption = computed(() => options.find(option => option.value === preference.value) ?? options[0])

function onCommand(value: ThemePreference) {
  setPreference(value)
}
</script>

<template>
  <el-dropdown
    class="theme-dropdown"
    trigger="click"
    placement="bottom-end"
    :teleported="false"
    :show-arrow="false"
    @command="onCommand"
  >
    <button type="button" class="theme-switcher" :aria-label="`外观模式：${selectedOption.label}`" title="外观模式">
      <el-icon aria-hidden="true"><component :is="selectedOption.icon" /></el-icon>
      <span>{{ selectedOption.label }}</span>
      <el-icon class="theme-switcher-arrow" aria-hidden="true"><ArrowDown /></el-icon>
    </button>
    <template #dropdown>
      <el-dropdown-menu class="theme-menu">
        <el-dropdown-item
          v-for="option in options"
          :key="option.value"
          :command="option.value"
          :text-value="option.label"
          :class="{ 'is-selected': preference === option.value }"
          :aria-label="option.label + (preference === option.value ? '，当前选择' : '')"
        >
          <el-icon aria-hidden="true"><component :is="option.icon" /></el-icon>
          <span>{{ option.label }}</span>
          <el-icon v-if="preference === option.value" class="theme-option-check" aria-hidden="true"><Check /></el-icon>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.theme-dropdown { flex-shrink: 0; }
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
  font: inherit;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
  flex-shrink: 0;
}
.theme-switcher:hover { border-color: var(--el-color-primary); }
.theme-switcher:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 3px; }
.theme-switcher-arrow { margin-left: 2px; font-size: 11px; }
.theme-menu {
  min-width: 156px;
  padding: 5px;
  background: var(--el-bg-color-overlay);
}
.theme-menu :deep(.el-dropdown-menu__item) {
  gap: 8px;
  min-height: 36px;
  padding: 0 10px;
  border-radius: 4px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.theme-menu :deep(.el-dropdown-menu__item.is-selected),
.theme-menu :deep(.el-dropdown-menu__item:not(.is-disabled):hover),
.theme-menu :deep(.el-dropdown-menu__item:not(.is-disabled):focus) {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.theme-menu :deep(.el-icon) { margin-right: 0; }
.theme-option-check { margin-left: auto; }
</style>
