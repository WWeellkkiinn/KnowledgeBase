<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  hint?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}>()
</script>

<template>
  <div class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
    <div class="text-xs uppercase tracking-wide text-slate-500">{{ label }}</div>
    <div
      class="mt-1 text-3xl font-bold"
      :class="{
        'text-slate-900': !tone || tone === 'default',
        'text-emerald-600': tone === 'good',
        'text-amber-600': tone === 'warn',
        'text-rose-600': tone === 'bad',
      }"
    >
      {{ value }}
    </div>
    <div v-if="hint" class="mt-1 text-xs text-slate-500">{{ hint }}</div>
  </div>
</template>
