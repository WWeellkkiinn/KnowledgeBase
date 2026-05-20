<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const error = ref<string | null>(null)

onMounted(async () => {
  const sesame = route.query.sesame as string | undefined
  if (!sesame) {
    error.value = '链接无效（缺少 sesame 参数）'
    return
  }
  try {
    await authStore.consumeMagicLink(sesame)
    router.replace('/')
  } catch {
    error.value = '链接已失效或已使用，请重新申请魔法链接登录。'
  }
})
</script>

<template>
  <main
    class="min-h-screen flex items-center justify-center p-4"
    style="background: linear-gradient(180deg, var(--color-bg) 0%, var(--color-bg-subtle) 100%)"
  >
    <div class="w-full max-w-sm text-center space-y-6">
      <template v-if="!error">
        <div
          class="mx-auto flex h-14 w-14 items-center justify-center rounded-full"
          style="background: var(--color-bg-subtle); border: 1px solid var(--color-border)"
        >
          <svg width="24" height="24" viewBox="0 0 14 14" fill="none" class="animate-spin" xmlns="http://www.w3.org/2000/svg" style="color: var(--color-accent)">
            <circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 14" stroke-linecap="round" />
          </svg>
        </div>
        <p class="text-sm text-slate-500">正在验证链接，请稍候…</p>
      </template>
      <template v-else>
        <div class="space-y-2">
          <h1 class="text-xl font-semibold text-slate-900">链接无效</h1>
          <p class="text-sm text-slate-500">{{ error }}</p>
        </div>
        <router-link
          to="/login"
          class="inline-flex items-center justify-center gap-1.5 rounded-md font-medium text-sm px-3.5 py-2 bg-white border transition-colors"
          style="border-color: var(--color-border); color: var(--color-text)"
        >
          返回登录页
        </router-link>
      </template>
    </div>
  </main>
</template>

<style>
@keyframes spin {
  to { transform: rotate(360deg); }
}
.animate-spin {
  animation: spin 0.75s linear infinite;
}
</style>
