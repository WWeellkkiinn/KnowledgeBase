<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { nav } from '@/composables/useNav'

const route = useRoute()
function isActive(to: string) {
  return route.path === to
}
</script>

<template>
  <aside
    class="hidden md:flex flex-col w-[200px] shrink-0 border-r border-[color:var(--color-border)] bg-[color:var(--color-bg)]"
    style="--sidebar-w: 200px"
  >
    <!-- 品牌区 -->
    <div class="px-5 py-5">
      <span class="font-bold text-lg text-slate-800">KnowledgeBase</span>
    </div>

    <!-- 导航 -->
    <nav class="flex-1 px-3 space-y-0.5">
      <RouterLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        :class="[
          'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors relative',
          isActive(item.to)
            ? 'bg-[color:var(--color-accent-soft)] text-[color:var(--color-accent)] sidebar-active'
            : 'text-slate-600 hover:bg-slate-50',
        ]"
      >
        <!-- 左侧蓝条（active 态） -->
        <span
          :class="[
            'active-bar absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 rounded-full bg-[color:var(--color-accent)]',
            isActive(item.to) ? 'opacity-100' : 'opacity-0',
          ]"
        ></span>
        <!-- icon -->
        <span class="w-[18px] h-[18px] shrink-0" v-html="item.icon"></span>
        {{ item.label }}
      </RouterLink>
    </nav>

    <!-- 底部留白 -->
    <div class="h-6"></div>
  </aside>
</template>
