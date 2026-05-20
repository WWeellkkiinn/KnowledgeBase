<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { nav } from '@/composables/useNav'

const route = useRoute()
function isActive(to: string) {
  return route.path === to
}

// Bottom bar shows 4 primary tabs + a "更多" pill that opens the rest in a
// sheet. Pinning 4 primaries keeps thumb reach comfortable on small screens.
const PRIMARY = 4
const primaryNav = computed(() => nav.slice(0, PRIMARY))
const overflowNav = computed(() => nav.slice(PRIMARY))

const moreOpen = ref(false)
function toggleMore() {
  moreOpen.value = !moreOpen.value
}
function closeMore() {
  moreOpen.value = false
}

// Auto-close the sheet on route change so the bar doesn't linger over the new page.
watch(
  () => route.fullPath,
  () => {
    moreOpen.value = false
  },
)

const overflowActive = computed(() => overflowNav.value.some((item) => isActive(item.to)))
</script>

<template>
  <!-- Sheet (slides up from bottom). Mounted above the bar; only when open. -->
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="moreOpen"
        class="md:hidden fixed inset-0 z-40 bg-black/30"
        @click="closeMore"
      ></div>
    </Transition>
    <Transition
      enter-active-class="transition-transform duration-200"
      enter-from-class="translate-y-full"
      enter-to-class="translate-y-0"
      leave-active-class="transition-transform duration-200"
      leave-from-class="translate-y-0"
      leave-to-class="translate-y-full"
    >
      <nav
        v-if="moreOpen"
        class="md:hidden fixed bottom-14 left-0 right-0 z-40 bg-white border-t border-slate-200 shadow-[0_-4px_12px_rgba(0,0,0,0.08)] pb-[env(safe-area-inset-bottom)]"
      >
        <ul class="px-2 py-2">
          <li v-for="item in overflowNav" :key="item.to">
            <RouterLink
              :to="item.to"
              :class="[
                'flex items-center gap-3 px-4 py-3 rounded-md transition-colors',
                isActive(item.to)
                  ? 'bg-[color:var(--color-accent-soft)] text-[color:var(--color-accent)]'
                  : 'text-slate-700 hover:bg-slate-50',
              ]"
            >
              <span class="w-[22px] h-[22px]" v-html="item.icon"></span>
              <span class="text-sm font-medium">{{ item.label }}</span>
            </RouterLink>
          </li>
        </ul>
      </nav>
    </Transition>
  </Teleport>

  <nav
    class="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-slate-200 shadow-[0_-1px_4px_rgba(0,0,0,0.04)] pb-[env(safe-area-inset-bottom)]"
  >
    <div class="grid grid-cols-5 h-14">
      <RouterLink
        v-for="item in primaryNav"
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

      <!-- 更多 -->
      <button
        type="button"
        :class="[
          'flex flex-col items-center justify-center gap-0.5 transition-colors',
          moreOpen || overflowActive
            ? 'text-[color:var(--color-accent)]'
            : 'text-slate-500',
        ]"
        :aria-expanded="moreOpen"
        @click="toggleMore"
      >
        <span class="w-[22px] h-[22px]">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="5" cy="12" r="1.5" />
            <circle cx="12" cy="12" r="1.5" />
            <circle cx="19" cy="12" r="1.5" />
          </svg>
        </span>
        <span class="text-[11px] font-medium leading-none">更多</span>
      </button>
    </div>
  </nav>
</template>
