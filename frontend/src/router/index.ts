import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { isAdminSite } from '@/site'
import { routeSeo, setPageSeo } from '@/utils/seo'
import { readSession } from '@/utils/session'

const routes: RouteRecordRaw[] = [
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
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
        path: 'todos',
        name: 'admin-todos',
        component: () => import('@/views/AdminTodos.vue'),
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
      {
        path: 'operations',
        name: 'admin-operations',
        component: () => import('@/views/AdminOperations.vue'),
      },
      {
        path: 'music',
        name: 'admin-music',
        component: () => import('@/views/AdminMusic.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  async scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      // Wait for the archive height before restoring a position below the skeleton.
      if (to.name === 'home' && document.querySelector('.blog-home[data-list-loading="true"]')) {
        await new Promise<void>((resolve) => {
          const ready = () => { window.clearTimeout(timer); window.removeEventListener('sudothink:articles-ready', ready); resolve() }
          const timer = window.setTimeout(ready, 5000)
          window.addEventListener('sudothink:articles-ready', ready, { once: true })
        })
      }
      return savedPosition
    }
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
    const token = readSession().token
    if (!token) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
  if (to.meta?.requiresAdmin) {
    const user = readSession().user
    if (!user || !user.is_admin) {
      return { name: isAdminSite() ? 'login' : 'home', query: { redirect: to.fullPath } }
    }
  }
})

router.afterEach((to, from) => {
  if (to.path !== from.path || !document.head.querySelector('meta[property="og:url"]')) setPageSeo(routeSeo(to.path, isAdminSite()))
})

export default router
