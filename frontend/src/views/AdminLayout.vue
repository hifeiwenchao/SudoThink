<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Back, ChatLineRound, CircleCheck, DataAnalysis, Document, Folder, Headset, Present, PriceTag, Setting, User, UserFilled } from '@element-plus/icons-vue'
import { PUBLIC_SITE_URL } from '@/site'

const route = useRoute()
</script>

<template>
  <div class="admin-layout">
    <el-container>
      <el-aside width="200px" class="sidebar">
        <div class="sidebar-brand"><span class="sidebar-mark" aria-hidden="true">&gt;_</span><h3 class="logo">管理后台</h3></div>
        <el-menu :default-active="route.path" router>
          <el-menu-item index="/admin">
            <el-icon aria-hidden="true"><DataAnalysis /></el-icon>
            <span>概览</span>
          </el-menu-item>
          <el-menu-item index="/admin/todos">
            <el-icon aria-hidden="true"><CircleCheck /></el-icon>
            <span>待办事项</span>
          </el-menu-item>
          <el-menu-item index="/admin/users">
            <el-icon aria-hidden="true"><User /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/articles">
            <el-icon aria-hidden="true"><Document /></el-icon>
            <span>文章管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/comments">
            <el-icon aria-hidden="true"><ChatLineRound /></el-icon>
            <span>评论管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/categories">
            <el-icon aria-hidden="true"><Folder /></el-icon>
            <span>分类管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/tags">
            <el-icon aria-hidden="true"><PriceTag /></el-icon>
            <span>标签管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/about">
            <el-icon aria-hidden="true"><UserFilled /></el-icon>
            <span>关于我</span>
          </el-menu-item>
          <el-menu-item index="/admin/donations">
            <el-icon aria-hidden="true"><Present /></el-icon>
            <span>打赏设置</span>
          </el-menu-item>
          <el-menu-item index="/admin/operations">
            <el-icon aria-hidden="true"><Setting /></el-icon>
            <span>运维管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/music">
            <el-icon aria-hidden="true"><Headset /></el-icon>
            <span>音乐设置</span>
          </el-menu-item>
        </el-menu>
        <a :href="PUBLIC_SITE_URL" class="return-link">
          <el-icon aria-hidden="true"><Back /></el-icon>
          <span>返回前台</span>
        </a>
      </el-aside>
      <el-main class="main">
        <RouterView />
      </el-main>
    </el-container>
  </div>
</template>

<style scoped>
.admin-layout {
  min-height: 100vh;
  background: var(--app-page-bg);
}
.sidebar {
  background: var(--app-surface);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--app-radius-lg);
  align-self: flex-start;
  position: sticky;
  top: 20px;
  max-height: calc(100dvh - 40px);
  padding: 8px;
}
.sidebar-brand { display: flex; align-items: center; gap: 9px; padding: 12px 12px 20px; }
.sidebar-mark { font-family: monospace; font-size: 20px; color: var(--el-color-primary); }
.sidebar :deep(.el-menu) { border: 0; }
.sidebar :deep(.el-menu-item) { height: 44px; border-radius: 8px; margin-bottom: 4px; }
.sidebar :deep(.el-menu-item.is-active) { background: var(--el-color-primary-light-9); font-weight: 600; }
.logo {
  margin: 0;
  padding: 0;
  font-size: 16px;
  text-align: center;
  color: var(--el-text-color-primary);
}
.return-link {
  display: flex;
  align-items: center;
  gap: 5px;
  box-sizing: border-box;
  height: 44px;
  margin-top: 12px;
  padding: 0 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-primary);
  font-size: 14px;
  text-decoration: none;
}
.return-link :deep(.el-icon) { flex: 0 0 24px; font-size: 18px; }
.return-link:hover { color: var(--el-color-primary); background: var(--el-menu-hover-bg-color, var(--el-color-primary-light-9)); }
.return-link:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: -2px; }
.main {
  padding: 4px 0 24px 28px;
  min-width: 0;
  overflow: visible;
}
.admin-layout > :deep(.el-container) { max-width: 1600px; margin: 0 auto; gap: 0; }
@media (max-width: 700px) {
  .admin-layout > :deep(.el-container) { flex-direction: column; }
  .sidebar { position: static; width: 100%; max-width: 100%; max-height: none; padding: 6px; border-radius: 12px; }
  .sidebar-brand { display: none; }
  .logo { text-align: left; padding: 0; }
  .sidebar :deep(.el-menu) { display: flex; overflow-x: auto; border-right: 0; }
  .sidebar :deep(.el-menu-item) { flex-shrink: 0; padding: 0 14px; height: 44px; margin: 0 4px 0 0; }
  .return-link { display: none; }
  .main { padding: 24px 0; }
}
</style>
