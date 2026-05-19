<script setup lang="ts">
const props = withDefaults(defineProps<{
  variant?: 'text' | 'card' | 'row' | 'avatar'
  count?: number
  className?: string
}>(), {
  variant: 'text',
  count: 3,
  className: '',
})

const itemClass = (index: number): string => {
  const base = 'bg-slate-200 animate-pulse rounded'
  switch (props.variant) {
    case 'text':
      return `${base} h-3 ${index === props.count - 1 ? 'w-2/3' : 'w-full'}`
    case 'card':
      return `${base} h-32 w-full`
    case 'row':
      return `${base} h-12 w-full`
    case 'avatar':
      return `${base} h-10 w-10 rounded-full`
    default:
      return `${base} h-3 w-full`
  }
}
</script>

<template>
  <div :class="[variant === 'card' ? 'space-y-3' : 'space-y-2', className]">
    <div
      v-for="i in count"
      :key="i"
      :class="itemClass(i - 1)"
    />
  </div>
</template>
