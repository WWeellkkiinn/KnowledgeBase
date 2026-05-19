<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  subtitle?: string
}>(), {
  title: undefined,
  subtitle: undefined,
})
</script>

<template>
  <header class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-0">
    <div class="flex-1">
      <slot v-if="!title" />
      <template v-else>
        <h1 class="text-xl font-semibold text-slate-900">{{ title }}</h1>
        <p v-if="subtitle" class="text-sm text-slate-500 mt-1">{{ subtitle }}</p>
      </template>
    </div>
    <div>
      <slot name="actions" />
    </div>
  </header>
</template>
