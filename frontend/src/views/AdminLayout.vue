<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Back, ChatLineRound, DataAnalysis, Document, Folder, Present, PriceTag, Setting, User, UserFilled } from '@element-plus/icons-vue'
import { PUBLIC_SITE_URL } from '@/site'

const route = useRoute()
</script>

<template>
  <div class="admin-layout">
    <el-container>
      <el-aside width="200px" class="sidebar">
        <h3 class="logo">管理后台</h3>
        <el-menu :default-active="route.path" router>
          <el-menu-item index="/admin">
            <el-icon aria-hidden="true"><DataAnalysis /></el-icon>
            <span>概览</span>
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
  border-right: 1px solid var(--el-border-color);
}
.logo {
  margin: 0;
  padding: 16px;
  font-size: 18px;
  text-align: center;
  color: var(--el-text-color-primary);
}
.return-link {
  display: flex;
  align-items: center;
  gap: 5px;
  box-sizing: border-box;
  height: 56px;
  padding: 0 20px;
  color: var(--el-text-color-primary);
  font-size: 14px;
  text-decoration: none;
}
.return-link :deep(.el-icon) { flex: 0 0 24px; font-size: 18px; }
.return-link:hover { color: var(--el-color-primary); background: var(--el-menu-hover-bg-color, var(--el-color-primary-light-9)); }
.return-link:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: -2px; }
.main {
  padding: 24px;
  min-width: 0;
}
@media (max-width: 700px) {
  .admin-layout > :deep(.el-container) { flex-direction: column; }
  .sidebar { width: 100%; border-right: 0; border-bottom: 1px solid var(--el-border-color); }
  .logo { text-align: left; padding: 12px 16px; }
  .sidebar :deep(.el-menu) { display: flex; overflow-x: auto; border-right: 0; }
  .sidebar :deep(.el-menu-item) { flex-shrink: 0; padding: 0 14px; height: 48px; }
  .return-link { height: 48px; padding: 0 14px; }
  .main { padding: 18px 14px; }
}
</style>
