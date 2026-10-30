import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
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
    meta: { requiresAuth: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
  },
  {
    path: '/admin',
    component: () => import('@/views/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
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
})

router.beforeEach((to) => {
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
      return { name: 'home' }
    }
  }
})

export default router
