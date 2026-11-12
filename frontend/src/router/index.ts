import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { isAdminSite } from '@/site'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
  },
  {
    path: '/tools',
    name: 'tools',
    component: () => import('@/views/ToolsView.vue'),
  },
  {
    path: '/about',
    name: 'about',
    component: () => import('@/views/AboutView.vue'),
  },
  {
    path: '/articles/:id(\\d+)',
    name: 'article-detail',
    component: () => import('@/views/ArticleDetailView.vue'),
  },
  {
    path: '/articles/new',
    name: 'article-new',
    component: () => import('@/views/ArticleEditView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, adminSiteOnly: true },
  },
  {
    path: '/articles/:id(\\d+)/edit',
    name: 'article-edit',
    component: () => import('@/views/ArticleEditView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, adminSiteOnly: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { adminSiteOnly: true },
  },
  {
    path: '/admin',
    component: () => import('@/views/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, adminSiteOnly: true },
    children: [
      {
        path: '',
        name: 'admin-dashboard',
        component: () => import('@/views/AdminDashboard.vue'),
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/AdminUsers.vue'),
      },
      {
        path: 'articles',
        name: 'admin-articles',
        component: () => import('@/views/AdminArticles.vue'),
      },
      {
        path: 'categories',
        name: 'admin-categories',
        component: () => import('@/views/AdminCategories.vue'),
      },
      {
        path: 'tags',
        name: 'admin-tags',
        component: () => import('@/views/AdminTags.vue'),
      },
      {
        path: 'about',
        name: 'admin-about',
        component: () => import('@/views/AdminAbout.vue'),
      },
      {
        path: 'donations',
        name: 'admin-donations',
        component: () => import('@/views/AdminDonations.vue'),
      },
      {
        path: 'comments',
        name: 'admin-comments',
        component: () => import('@/views/AdminComments.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.name === 'tools' && from.name === 'tools') return false
    if (to.hash) {
      if (!document.getElementById(to.hash.slice(1))) return false
      return { el: to.hash, top: 140, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }
    }
    return { top: 0 }
  },
})

router.beforeEach((to) => {
  if (to.meta?.adminSiteOnly && !isAdminSite()) {
    return { name: 'home' }
  }

  if (isAdminSite() && to.name === 'home') {
    return { name: 'admin-dashboard' }
  }

  if (to.meta?.requiresAuth) {
    const token = localStorage.getItem('access_token')
    if (!token) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
  if (to.meta?.requiresAdmin) {
    const raw = localStorage.getItem('user')
    const user = raw ? JSON.parse(raw) : null
    if (!user || !user.is_admin) {
      return { name: isAdminSite() ? 'login' : 'home' }
    }
  }
})

export default router
