<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import ProgressToast from '@/components/ProgressToast.vue'

const route = useRoute()

const nav = [
  { to: '/', label: '概览' },
  { to: '/papers', label: '论文库' },
  { to: '/network', label: '引用图' },
  { to: '/review', label: '综述' },
  { to: '/explore', label: '探索' },
]
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header class="bg-white border-b border-slate-200">
      <nav class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center gap-6">
        <div class="text-lg font-sans font-semibold text-slate-800 shrink-0">KnowledgeBase</div>
        <div class="overflow-x-auto">
          <ul class="flex gap-4 text-sm whitespace-nowrap">
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
        </div>
      </nav>
    </header>
    <main :class="['flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 lg:px-8', route.path !== '/explore' ? 'py-6' : 'h-[calc(100dvh-3.25rem)] min-h-0 overflow-hidden']">
      <RouterView />
    </main>
    <ProgressToast />
  </div>
</template>
