<script setup lang="ts">
import { RouterView, RouterLink, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import { computed, onMounted } from 'vue'
import { isAdminSite } from '@/site'
import { useTaxonomyStore } from '@/stores/taxonomy'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
import '@/styles/blog.css'

const userStore = useUserStore()
const { isLoggedIn, user } = storeToRefs(userStore)

const isAdmin = computed(() => user.value?.is_admin === true)
const adminSite = isAdminSite()
const route = useRoute()
const year = new Date().getFullYear()
const taxonomyStore = useTaxonomyStore()
const { categories: navigationCategories } = storeToRefs(taxonomyStore)

onMounted(async () => {
  if (adminSite || taxonomyStore.loaded) return
  try {
    await taxonomyStore.loadCategories()
  } catch {
    // The article archive offers a retry for the shared category index.
  }
})

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
}

const onLogout = () => {
  userStore.logout()
}
</script>

<template>
  <div v-if="!adminSite" class="blog-shell">
    <a class="blog-skip" href="#main-content">跳到正文</a>
    <header class="blog-header">
      <div class="blog-header-inner">
        <RouterLink to="/" class="blog-brand" aria-label="SudoThink 博客首页">
          <span class="blog-brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m6 7 5 5-5 5m8 0h5" /></svg>
          </span>
          <span>SudoThink<span class="blog-brand-dot">.</span></span>
        </RouterLink>
        <div class="blog-header-right">
          <nav class="blog-nav" aria-label="博客导航">
            <RouterLink to="/#articles" :class="{ 'is-active': route.path !== '/about' && !route.query.category }" :aria-current="route.path === '/' && !route.query.category ? 'page' : undefined"><span>01</span> 文章</RouterLink>
            <RouterLink
              v-for="(category, index) in navigationCategories"
              :key="category.id"
              :to="{ path: '/', query: { category: String(category.id) }, hash: '#articles' }"
              :class="{ 'is-active': route.path === '/' && route.query.category === String(category.id) }"
              :aria-current="route.path === '/' && route.query.category === String(category.id) ? 'page' : undefined"
              :title="category.name"
            ><span>{{ String(index + 2).padStart(2, '0') }}</span><span class="blog-nav-label">{{ category.name }}</span></RouterLink>
            <RouterLink to="/about" :class="{ 'is-active': route.path === '/about' }"><span>{{ String(navigationCategories.length + 2).padStart(2, '0') }}</span> 关于我</RouterLink>
          </nav>
          <span class="blog-header-divider" aria-hidden="true" />
          <ThemeSwitcher />
        </div>
      </div>
    </header>
    <main id="main-content" class="blog-main" tabindex="-1">
      <RouterView />
    </main>
    <footer class="blog-footer">
      <div class="blog-footer-inner">
        <div class="blog-footer-note"><span class="blog-footer-prompt" aria-hidden="true">&gt;_</span><span>以文字整理思考，用代码验证想法。</span></div>
        <div class="blog-footer-bottom">
          <span>© {{ year }} SudoThink <span class="blog-footer-separator">/</span> THINK. BUILD. WRITE.</span>
          <button type="button" @click="scrollToTop">回到顶部 <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 10 6-6 6 6M12 4v16" /></svg></button>
        </div>
      </div>
    </footer>
  </div>
  <el-container v-else class="layout">
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
