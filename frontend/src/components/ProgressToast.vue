<script setup lang="ts">
import { computed } from 'vue'
import { useProgressStore } from '@/stores/progress'

const progress = useProgressStore()
// SSE is per-task lazy: streams open in subscribe(), no global init needed.

const visible = computed(() => progress.recent.slice(0, 5))
</script>

<template>
  <div
    v-if="visible.length > 0"
    class="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
  >
    <div
      v-for="(ev, i) in visible"
      :key="`${ev.task_id}-${ev.ts}-${i}`"
      class="rounded-md border border-slate-200 bg-white p-3 shadow-md text-sm"
    >
      <div class="flex items-center justify-between">
        <span class="font-semibold text-slate-700">{{ ev.type }}</span>
        <span class="text-xs text-slate-400">#{{ ev.task_id }}</span>
      </div>
      <div v-if="ev.payload" class="mt-1 text-xs text-slate-600 truncate">
        {{ JSON.stringify(ev.payload) }}
      </div>
    </div>
  </div>
</template>
