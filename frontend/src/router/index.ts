import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

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
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
