import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { getToken, isSafeBackPath } from '@/api/client'

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
  {
    path: '/subscriptions',
    name: 'subscriptions',
    component: () => import('@/pages/Subscriptions.vue'),
  },
  {
    path: '/explore',
    component: () => import('../pages/Explore.vue'),
  },
  { path: '/failures', name: 'failures', component: () => import('@/pages/Failures.vue') },
  { path: '/feed', redirect: '/subscriptions' },
  { path: '/recommendations', redirect: '/subscriptions' },
  { path: '/login', name: 'login', component: () => import('@/pages/Login.vue'), meta: { public: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const isPublic = to.matched.some((r) => r.meta?.public)
  const hasToken = !!getToken()
  // 已登录访问 /login 直接回首页
  if (hasToken && to.path === '/login') {
    return { path: '/' }
  }
  // 未登录访问受保护路由 → 跳登录页并带上 back
  if (!hasToken && !isPublic) {
    const current = to.fullPath
    const back = isSafeBackPath(current) ? current : '/'
    return { path: '/login', query: { back } }
  }
  return true
})

export default router
