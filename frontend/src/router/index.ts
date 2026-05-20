import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { isSafeBackPath } from '@/api/client'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'dashboard', component: () => import('@/pages/Dashboard.vue') },
  { path: '/papers', name: 'papers', component: () => import('@/pages/Papers.vue') },
  {
    path: '/papers/:id',
    name: 'paper-detail',
    component: () => import('@/pages/PaperDetail.vue'),
    props: true,
  },
  { path: '/network', name: 'network', component: () => import('@/pages/Network.vue') },
  { path: '/review', name: 'review', component: () => import('@/pages/Review.vue') },
  { path: '/subscriptions', redirect: '/explore' },
  {
    path: '/explore',
    component: () => import('../pages/Explore.vue'),
  },
  { path: '/feed', redirect: '/explore' },
  { path: '/recommendations', redirect: '/explore' },
  { path: '/login', name: 'login', component: () => import('@/pages/Login.vue'), meta: { public: true, sidebar: false } },
  // --- SaaS auth routes ---
  { path: '/register', name: 'register', component: () => import('@/pages/Register.vue'), meta: { public: true, sidebar: false } },
  { path: '/pending-approval', name: 'pending-approval', component: () => import('@/pages/PendingApproval.vue'), meta: { public: true, sidebar: false } },
  { path: '/auth/magic', name: 'magic-link-consume', component: () => import('@/pages/MagicLinkConsume.vue'), meta: { public: true, sidebar: false } },
  { path: '/account', name: 'account', component: () => import('@/pages/Account.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const isPublic = to.matched.some((r) => r.meta?.public)

  // Lazy-import store here to avoid circular dep at module level
  const { useAuthStore } = await import('@/stores/auth')
  const authStore = useAuthStore()

  const authed = authStore.isAuthenticated

  // Already logged-in → redirect away from public auth pages
  if (authed && (to.path === '/login' || to.path === '/register')) {
    return { path: '/' }
  }

  // Not logged in → try fetchMe (session cookie may already be valid)
  if (!authed && !isPublic) {
    try {
      await authStore.fetchMe()
    } catch {
      // fetchMe failed → not authenticated
    }
    // Re-check after fetchMe attempt
    if (!authStore.isAuthenticated) {
      const current = to.fullPath
      const back = isSafeBackPath(current) ? current : '/'
      return { path: '/login', query: { back } }
    }
  }

  // Approved check for authenticated users on non-public routes
  if (authStore.isAuthenticated && !isPublic) {
    const status = authStore.user?.approval_status
    if (status === 'pending' && to.path !== '/pending-approval') {
      return { path: '/pending-approval' }
    }
  }

  return true
})

export default router
