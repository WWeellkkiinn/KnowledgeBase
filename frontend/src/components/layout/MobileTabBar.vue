<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { nav } from '@/composables/useNav'

const route = useRoute()
function isActive(to: string) {
  return route.path === to
}
</script>

<template>
  <nav
    class="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-slate-200 shadow-[0_-1px_4px_rgba(0,0,0,0.04)] pb-[env(safe-area-inset-bottom)]"
  >
    <div class="grid grid-cols-5 h-14">
      <RouterLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        :class="[
          'flex flex-col items-center justify-center gap-0.5 transition-colors',
          isActive(item.to) ? 'text-[color:var(--color-accent)]' : 'text-slate-500',
        ]"
      >
        <span class="w-[22px] h-[22px]" v-html="item.icon"></span>
        <span class="text-[11px] font-medium leading-none">{{ item.label }}</span>
      </RouterLink>
    </div>
  </nav>
</template>
