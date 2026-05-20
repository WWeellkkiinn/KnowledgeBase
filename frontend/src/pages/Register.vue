<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const reason = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function submit() {
  const e = email.value.trim()
  const r = reason.value.trim()
  if (!e) {
    error.value = '请填写邮箱'
    return
  }
  if (!r) {
    error.value = '请填写申请说明'
    return
  }
  submitting.value = true
  error.value = null
  try {
    await authStore.register({
      email: e,
      ...(password.value ? { password: password.value } : {}),
      reason: r,
    })
    router.replace('/pending-approval')
  } catch (err_: unknown) {
    if (axios.isAxiosError(err_)) {
      const status = err_.response?.status
      if (status === 409) {
        error.value = '该邮箱已注册'
      } else if (status === 422) {
        error.value = '邮箱格式不正确'
      } else {
        error.value = '提交失败，请检查网络'
      }
    } else {
      error.value = '提交失败，请检查网络'
    }
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
        <h1 class="text-xl font-semibold text-slate-900">申请账号</h1>
        <p class="text-sm text-slate-500 mt-1">提交申请，待管理员审批后即可使用</p>
      </div>

      <form
        class="space-y-4 rounded-panel border border-slate-200 bg-white p-6 shadow-lift"
        @submit.prevent="submit"
      >
        <label class="block">
          <span class="text-xs font-medium uppercase tracking-wide text-slate-400">邮箱 <span class="text-rose-400">*</span></span>
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
          <span class="text-xs font-medium uppercase tracking-wide text-slate-400">
            密码 <span class="text-slate-300">（可选，不设则只能用魔法链接登录）</span>
          </span>
          <input
            v-model="password"
            type="password"
            autocomplete="new-password"
            class="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="留空则不设密码"
            :disabled="submitting"
          />
        </label>

        <label class="block">
          <span class="text-xs font-medium uppercase tracking-wide text-slate-400">申请说明 <span class="text-rose-400">*</span></span>
          <textarea
            v-model="reason"
            rows="3"
            class="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
            placeholder="简要说明你的使用场景或身份"
            :disabled="submitting"
          />
        </label>

        <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>

        <Button type="submit" variant="primary" class="w-full" :loading="submitting" :disabled="submitting">
          提交申请
        </Button>
      </form>

      <p class="text-center text-sm text-slate-500">
        已有账号？
        <router-link to="/login" class="text-blue-600 hover:underline">返回登录</router-link>
      </p>
    </div>
  </main>
</template>
