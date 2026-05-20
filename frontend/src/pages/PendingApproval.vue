<script setup lang="ts">
</script>

<template>
  <main
    class="min-h-screen flex items-center justify-center p-4"
    style="background: linear-gradient(180deg, var(--color-bg) 0%, var(--color-bg-subtle) 100%)"
  >
    <div class="w-full max-w-sm space-y-6 text-center">
      <div
        class="mx-auto flex h-14 w-14 items-center justify-center rounded-full"
        style="background: var(--color-bg-subtle); border: 1px solid var(--color-border)"
      >
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--color-accent)">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
      </div>

      <div class="space-y-2">
        <h1 class="text-xl font-semibold text-slate-900">申请已收到</h1>
        <p class="text-sm text-slate-500 leading-relaxed">
          你的账号申请已提交，正在等待管理员审批。<br />
          审批通过后，我们会通过邮件通知你。
        </p>
      </div>

      <router-link
        to="/login"
        class="inline-flex items-center justify-center gap-1.5 rounded-md font-medium text-sm px-3.5 py-2 bg-white border transition-colors"
        style="border-color: var(--color-border); color: var(--color-text)"
      >
        返回登录页
      </router-link>
    </div>
  </main>
</template>
