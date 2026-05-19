<script setup lang="ts">
const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
}>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  type: 'button',
})

const emit = defineEmits<{ click: [e: MouseEvent] }>()

const sizeClass = props.size === 'sm' ? 'text-xs px-2.5 py-1.5' : 'text-sm px-3.5 py-2'

const variantStyle: Record<string, string> = {
  primary: 'text-white',
  secondary: 'bg-white border text-sm',
  ghost: 'bg-transparent',
  danger: 'text-white',
}
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="[
      'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors',
      sizeClass,
      (disabled || loading) ? 'opacity-60 cursor-not-allowed' : '',
      variant === 'primary' ? 'text-white' : '',
      variant === 'secondary' ? 'bg-white border text-sm' : '',
      variant === 'ghost' ? 'bg-transparent' : '',
      variant === 'danger' ? 'text-white' : '',
    ]"
    :style="{
      ...(variant === 'primary' ? { background: 'var(--color-accent)', '--hover-bg': 'var(--color-accent-hover)' } : {}),
      ...(variant === 'secondary' ? { borderColor: 'var(--color-border)', color: 'var(--color-text)' } : {}),
      ...(variant === 'ghost' ? { color: 'var(--color-text-muted)' } : {}),
      ...(variant === 'danger' ? { background: 'var(--color-danger)' } : {}),
    }"
    @click="(e) => emit('click', e)"
    @mouseover="(e) => {
      if (disabled || loading) return
      const el = e.currentTarget as HTMLButtonElement
      if (variant === 'primary') el.style.background = 'var(--color-accent-hover)'
      if (variant === 'secondary') el.style.background = 'var(--color-bg-subtle)'
      if (variant === 'ghost') el.style.background = 'var(--color-bg-subtle)'
      if (variant === 'danger') el.style.filter = 'brightness(0.88)'
    }"
    @mouseout="(e) => {
      const el = e.currentTarget as HTMLButtonElement
      if (variant === 'primary') el.style.background = 'var(--color-accent)'
      if (variant === 'secondary') el.style.background = 'white'
      if (variant === 'ghost') el.style.background = 'transparent'
      if (variant === 'danger') el.style.filter = ''
    }"
  >
    <template v-if="loading">
      <svg
        width="14" height="14"
        viewBox="0 0 14 14"
        fill="none"
        class="animate-spin"
        xmlns="http://www.w3.org/2000/svg"
      >
        <circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 14" stroke-linecap="round" />
      </svg>
    </template>
    <template v-else>
      <slot />
    </template>
  </button>
</template>

<style>
@keyframes spin {
  to { transform: rotate(360deg); }
}
.animate-spin {
  animation: spin 0.75s linear infinite;
}
</style>
