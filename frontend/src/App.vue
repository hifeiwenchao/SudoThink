<script setup lang="ts">
import { RouterView, RouterLink } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import { isAdminSite } from '@/site'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'

const userStore = useUserStore()
const { isLoggedIn, user } = storeToRefs(userStore)

const isAdmin = computed(() => user.value?.is_admin === true)
const adminSite = isAdminSite()

const onLogout = () => {
  userStore.logout()
}
</script>

<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="brand">
        <RouterLink to="/">SudoThink</RouterLink>
      </div>
      <div class="nav">
        <RouterLink to="/">首页</RouterLink>
        <RouterLink v-if="adminSite && isLoggedIn" to="/articles/new">写文章</RouterLink>
        <RouterLink v-if="adminSite && isAdmin" to="/admin">管理后台</RouterLink>
        <RouterLink v-if="adminSite && !isLoggedIn" to="/login">登录</RouterLink>
        <template v-if="adminSite && isLoggedIn && user">
          <span class="user">你好，{{ user.nickname || user.username }}</span>
          <el-button size="small" @click="onLogout">退出</el-button>
        </template>
        <ThemeSwitcher />
      </div>
    </el-header>
    <el-main>
      <RouterView />
    </el-main>
    <el-footer class="footer">© SudoThink Blog</el-footer>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--app-surface);
}
.brand a {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  text-decoration: none;
}
.nav {
  display: flex;
  gap: 16px;
  align-items: center;
}
.nav a {
  color: var(--el-text-color-regular);
  text-decoration: none;
}
.nav a.router-link-active {
  color: var(--el-color-primary);
}
.user {
  color: var(--el-text-color-regular);
}
.footer {
  text-align: center;
  color: var(--el-text-color-secondary);
}
@media (max-width: 640px) {
  .header { height: auto; min-height: 60px; padding: 14px 16px; gap: 12px; flex-wrap: wrap; }
  .brand { flex-shrink: 0; }
  .nav { width: 100%; gap: 12px; flex-wrap: wrap; font-size: 13px; }
  .nav a { white-space: nowrap; }
  .user { margin-left: auto; }
}
</style>
