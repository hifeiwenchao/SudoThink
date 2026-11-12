<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const route = useRoute()

const isAdmin = computed(() => userStore.user?.is_admin === true)
</script>

<template>
  <div class="admin-layout">
    <el-container>
      <el-aside width="200px" class="sidebar">
        <h3 class="logo">管理后台</h3>
        <el-menu :default-active="route.path" router>
          <el-menu-item index="/admin">
            <el-icon><i class="el-icon-data-analysis" /></el-icon>
            <span>概览</span>
          </el-menu-item>
          <el-menu-item index="/admin/users">
            <el-icon><i class="el-icon-user" /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/articles">
            <el-icon><i class="el-icon-document" /></el-icon>
            <span>文章管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/categories">
            <span>分类管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/tags">
            <span>标签管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/about">
            <span>关于我</span>
          </el-menu-item>
          <el-menu-item index="/admin/donations">
            <span>打赏设置</span>
          </el-menu-item>
          <el-menu-item index="/admin/comments">
            <el-icon><i class="el-icon-chat-line-round" /></el-icon>
            <span>评论审核</span>
          </el-menu-item>
          <el-menu-item index="/">
            <el-icon><i class="el-icon-back" /></el-icon>
            <span>返回前台</span>
          </el-menu-item>
        </el-menu>
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
  .main { padding: 18px 14px; }
}
</style>
