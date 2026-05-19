<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  hint?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
  to?: string
}>()
</script>

<template>
  <component
    :is="to ? 'router-link' : 'div'"
    v-bind="to ? { to } : {}"
    class="rounded-panel border border-slate-200 bg-white p-4 shadow-subtle transition-all duration-150 hover:-translate-y-0.5 hover:shadow-soft block"
    :class="to ? 'cursor-pointer' : 'cursor-default'"
  >
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
  </component>
</template>
