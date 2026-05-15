<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { setToken, clearToken, validateToken, isSafeBackPath } from '@/api/client'
import { resetSocket } from '@/api/socket'

const route = useRoute()
const router = useRouter()
const token = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function submit() {
  const t = token.value.trim()
  if (!t) {
    error.value = '请输入访问令牌'
    return
  }
  submitting.value = true
  error.value = null
  try {
    // 先验证，成功后再写入 token，避免中间窗口留下无效 token
    await validateToken(t)
    setToken(t)
    // 让 socket 单例用新 token 重建
    resetSocket()
    const rawBack = (route.query.back as string) || '/'
    const back = isSafeBackPath(rawBack) ? rawBack : '/'
    router.replace(back)
  } catch (e: unknown) {
    clearToken()
    if (axios.isAxiosError(e)) {
      const status = e.response?.status
      if (status === 401) {
        error.value = '令牌无效'
      } else if (status === 429) {
        error.value = '请求过于频繁，请稍后再试'
      } else {
        error.value = '验证失败，请检查网络'
      }
    } else {
      error.value = '验证失败，请检查网络'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="min-h-screen flex items-center justify-center bg-[#F8FAFC] p-4">
    <form
      class="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
      @submit.prevent="submit"
    >
      <h1 class="text-lg font-semibold text-slate-900">KnowledgeBase 访问</h1>
      <p class="text-sm text-slate-500">需要访问令牌才能继续。</p>
      <label class="block">
        <span class="text-xs font-medium uppercase tracking-wide text-slate-400">访问令牌</span>
        <input
          v-model="token"
          type="password"
          autocomplete="current-password"
          class="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="粘贴你的 token"
          :disabled="submitting"
        />
      </label>
      <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
      <button
        type="submit"
        class="w-full rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        :disabled="submitting"
      >
        {{ submitting ? '验证中…' : '进入' }}
      </button>
    </form>
  </main>
</template>
