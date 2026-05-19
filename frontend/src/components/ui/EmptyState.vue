<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description?: string
}>(), {
  description: undefined,
})
</script>

<template>
  <div class="flex flex-col items-center py-12 px-6">
    <slot name="icon">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="24" cy="24" r="20" stroke="var(--color-text-soft)" stroke-width="1.5" stroke-dasharray="4 3" />
        <path d="M24 16 L30 28 L18 28 Z" stroke="var(--color-text-soft)" stroke-width="1.5" stroke-linejoin="round" fill="none" />
      </svg>
    </slot>
    <p class="text-sm font-medium text-slate-700 mt-4">{{ title }}</p>
    <p v-if="description" class="text-xs text-slate-500 mt-1.5 max-w-sm text-center">{{ description }}</p>
    <div v-if="$slots.action" class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>
