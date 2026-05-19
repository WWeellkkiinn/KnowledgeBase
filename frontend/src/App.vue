<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import ProgressToast from '@/components/ProgressToast.vue'
import Sidebar from '@/components/layout/Sidebar.vue'
import TopBar from '@/components/layout/TopBar.vue'
import MobileTabBar from '@/components/layout/MobileTabBar.vue'

const route = useRoute()

const showLayout = computed(() => route.meta.sidebar !== false)
const isExplore = computed(() => route.path === '/explore')
const isWide = computed(() => route.path === '/network' || route.path === '/papers')
</script>

<template>
  <!-- 登录页：跳过整套 layout -->
  <RouterView v-if="!showLayout" />

  <!-- 主 layout：侧栏 + 顶栏 + 主区域 + 移动 TabBar -->
  <div v-else class="h-dvh flex">
    <Sidebar />
    <div class="flex-1 flex flex-col min-w-0">
      <TopBar />
      <main
        :class="[
          'flex-1 w-full overflow-y-auto',
          isExplore
            ? 'flex flex-col min-h-0 overflow-hidden bg-[color:var(--color-bg-subtle)] pb-[calc(56px+env(safe-area-inset-bottom))] md:pb-0'
            : isWide
              ? 'w-full px-4 sm:px-6 lg:px-10 py-6 pb-20 md:pb-6'
              : 'max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-10 py-6 pb-20 md:pb-6'
        ]"
      >
        <RouterView />
      </main>
    </div>
    <MobileTabBar />
  </div>

  <ProgressToast />
</template>
