<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { isSafeBackPath } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import Button from '@/components/ui/Button.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const tab = ref<'password' | 'magic'>('password')
const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)
const magicSent = ref(false)

async function submitPassword() {
  const e = email.value.trim()
  const p = password.value
  if (!e || !p) {
    error.value = '请填写邮箱和密码'
    return
  }
  submitting.value = true
  error.value = null
  try {
    await authStore.login(e, p)
    const rawBack = (route.query.back as string) || '/'
    const back = isSafeBackPath(rawBack) ? rawBack : '/'
    router.replace(back)
  } catch (err_: unknown) {
    if (axios.isAxiosError(err_)) {
      const status = err_.response?.status
      const data = err_.response?.data as Record<string, unknown> | undefined
      if (status === 401) {
        error.value = '邮箱或密码错误'
      } else if (status === 403 && data?.code === 'pending_approval') {
        router.replace('/pending-approval')
      } else if (status === 403 && data?.code === 'rejected') {
        error.value = '账号申请已被拒绝，请联系管理员'
      } else {
        error.value = '登录失败，请检查网络'
      }
    } else {
      error.value = '登录失败，请检查网络'
    }
  } finally {
    submitting.value = false
  }
}

async function submitMagicLink() {
  const e = email.value.trim()
  if (!e) {
    error.value = '请输入邮箱'
    return
  }
  submitting.value = true
  error.value = null
  try {
    await authStore.requestMagicLink(e)
    magicSent.value = true
  } catch {
    error.value = '发送失败，请检查邮箱地址或网络'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main
    class="min-h-screen flex items-center justify-center p-4"
    style="background: linear-gradient(180deg, var(--color-bg) 0%, var(--color-bg-subtle) 100%)"
  >
    <div class="w-full max-w-sm space-y-6">
      <div class="text-center">
        <h1 class="text-xl font-semibold text-slate-900">KnowledgeBase</h1>
        <p class="text-sm text-slate-500 mt-1">学术文献知识库</p>
      </div>

      <div class="rounded-panel border border-slate-200 bg-white shadow-lift overflow-hidden">
        <!-- Tabs -->
        <div class="flex border-b border-slate-200">
          <button
            class="flex-1 py-2.5 text-sm font-medium transition-colors"
            :class="tab === 'password' ? 'text-slate-900 border-b-2 border-blue-500 -mb-px' : 'text-slate-400 hover:text-slate-600'"
            @click="tab = 'password'; error = null; magicSent = false"
          >
            密码登录
          </button>
          <button
            class="flex-1 py-2.5 text-sm font-medium transition-colors"
            :class="tab === 'magic' ? 'text-slate-900 border-b-2 border-blue-500 -mb-px' : 'text-slate-400 hover:text-slate-600'"
            @click="tab = 'magic'; error = null; magicSent = false"
          >
            魔法链接
          </button>
        </div>

        <!-- Password tab -->
        <form v-if="tab === 'password'" class="space-y-4 p-6" @submit.prevent="submitPassword">
          <label class="block">
            <span class="text-xs font-medium uppercase tracking-wide text-slate-400">邮箱</span>
            <input
              v-model="email"
              type="email"
              autocomplete="email"
              class="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="you@example.com"
              :disabled="submitting"
            />
          </label>
          <label class="block">
            <span class="text-xs font-medium uppercase tracking-wide text-slate-400">密码</span>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              class="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="••••••••"
              :disabled="submitting"
            />
          </label>
          <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
          <Button type="submit" variant="primary" class="w-full" :loading="submitting" :disabled="submitting">
            登录
          </Button>
        </form>

        <!-- Magic link tab -->
        <form v-else class="space-y-4 p-6" @submit.prevent="submitMagicLink">
          <template v-if="!magicSent">
            <p class="text-sm text-slate-500">输入邮箱，我们会发送一个免密登录链接。</p>
            <label class="block">
              <span class="text-xs font-medium uppercase tracking-wide text-slate-400">邮箱</span>
              <input
                v-model="email"
                type="email"
                autocomplete="email"
                class="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="you@example.com"
                :disabled="submitting"
              />
            </label>
            <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
            <Button type="submit" variant="primary" class="w-full" :loading="submitting" :disabled="submitting">
              发送魔法链接
            </Button>
          </template>
          <template v-else>
            <p class="text-sm text-slate-700">
              魔法链接已发送至 <strong>{{ email }}</strong>，请查收邮件并点击链接登录。
            </p>
            <Button variant="ghost" class="w-full" @click="magicSent = false; email = ''">
              重新发送
            </Button>
          </template>
        </form>
      </div>

      <p class="text-center text-sm text-slate-500">
        没有账号？
        <router-link to="/register" class="text-blue-600 hover:underline">申请账号</router-link>
      </p>
    </div>
  </main>
</template>
