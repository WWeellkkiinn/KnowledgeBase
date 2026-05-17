<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import ProgressToast from '@/components/ProgressToast.vue'

const nav = [
  { to: '/', label: '概览' },
  { to: '/papers', label: '论文库' },
  { to: '/network', label: '引用图' },
  { to: '/review', label: '综述' },
{ to: '/explore', label: '探索' },
  { to: '/failures', label: '失败诊断' },
]
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header class="bg-white border-b border-slate-200">
      <nav class="max-w-6xl mx-auto px-4 py-3 flex items-center gap-6">
        <div class="text-lg font-bold text-slate-800">KnowledgeBase</div>
        <ul class="flex gap-4 text-sm">
          <li v-for="item in nav" :key="item.to">
            <RouterLink
              :to="item.to"
              class="text-slate-600 hover:text-slate-900"
              active-class="text-blue-600 font-semibold"
            >
              {{ item.label }}
            </RouterLink>
          </li>
        </ul>
      </nav>
    </header>
    <main class="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
      <RouterView />
    </main>
    <ProgressToast />
  </div>
</template>
