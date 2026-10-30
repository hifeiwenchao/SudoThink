<script setup lang="ts">
import { RouterView, RouterLink } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const userStore = useUserStore()
const { isLoggedIn, user } = storeToRefs(userStore)

const isAdmin = computed(() => user.value?.is_admin === true)

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
        <RouterLink v-if="isLoggedIn" to="/articles/new">写文章</RouterLink>
        <RouterLink v-if="isAdmin" to="/admin">管理后台</RouterLink>
        <RouterLink v-if="!isLoggedIn" to="/login">登录</RouterLink>
        <RouterLink v-if="!isLoggedIn" to="/register">注册</RouterLink>
        <template v-if="isLoggedIn && user">
          <span class="user">你好，{{ user.nickname || user.username }}</span>
          <el-button size="small" @click="onLogout">退出</el-button>
        </template>
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
  border-bottom: 1px solid #eee;
  background: #fff;
}
.brand a {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  text-decoration: none;
}
.nav {
  display: flex;
  gap: 16px;
  align-items: center;
}
.nav a {
  color: #606266;
  text-decoration: none;
}
.nav a.router-link-active {
  color: #409eff;
}
.user {
  color: #606266;
}
.footer {
  text-align: center;
  color: #909399;
}
</style>
