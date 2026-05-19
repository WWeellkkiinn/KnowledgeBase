<script setup lang="ts">
import Button from './Button.vue'

withDefaults(defineProps<{
  message: string
  retryLabel?: string
}>(), {
  retryLabel: '重试',
})

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="flex flex-col items-center py-10 px-6">
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M20 6 L36 34 L4 34 Z" stroke="var(--color-danger)" stroke-width="1.5" stroke-linejoin="round" fill="none" />
      <line x1="20" y1="17" x2="20" y2="25" stroke="var(--color-danger)" stroke-width="1.5" stroke-linecap="round" />
      <circle cx="20" cy="29" r="1" fill="var(--color-danger)" />
    </svg>
    <p class="text-sm text-slate-700 mt-3 max-w-sm text-center">{{ message }}</p>
    <div class="mt-4">
      <Button variant="secondary" size="sm" @click="emit('retry')">
        {{ retryLabel }}
      </Button>
    </div>
  </div>
</template>
