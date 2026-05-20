<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/ui/PageHeader.vue'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const authStore = useAuthStore()

const loggingOut = ref(false)
const switching = ref(false)
const switchError = ref<string | null>(null)

const activeTenant = computed(() =>
  authStore.tenants.find((t) => t.id === authStore.activeTenantId) ?? null,
)

async function handleSwitchTenant(tenantId: number) {
  if (tenantId === authStore.activeTenantId) return
  switching.value = true
  switchError.value = null
  try {
    await authStore.switchTenant(tenantId)
  } catch {
    switchError.value = '切换失败，请稍后重试'
  } finally {
    switching.value = false
  }
}

async function handleLogout() {
  loggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    loggingOut.value = false
  }
  router.replace('/login')
}
</script>

<template>
  <section class="space-y-6">
    <PageHeader title="账号" subtitle="个人信息与工作区" />

    <div class="rounded-panel border border-slate-200 bg-white p-6 shadow-lift space-y-5">
      <!-- 用户信息 -->
      <div class="space-y-1">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-400">邮箱</p>
        <p class="text-sm text-slate-800">{{ authStore.user?.email ?? '—' }}</p>
      </div>

      <div class="space-y-1">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-400">账号状态</p>
        <p class="text-sm text-slate-800 capitalize">{{ authStore.user?.approval_status ?? '—' }}</p>
      </div>

      <!-- 当前 Tenant + 角色 -->
      <div class="space-y-1">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-400">当前工作区</p>
        <p class="text-sm text-slate-800">
          {{ activeTenant?.name ?? '—' }}
          <span v-if="activeTenant" class="ml-2 text-xs text-slate-400">({{ activeTenant.role }})</span>
        </p>
      </div>

      <!-- 多 Tenant 切换 -->
      <div v-if="authStore.tenants.length > 1" class="space-y-1">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-400">切换工作区</p>
        <select
          class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          :value="authStore.activeTenantId"
          :disabled="switching"
          @change="handleSwitchTenant(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="t in authStore.tenants" :key="t.id" :value="t.id">
            {{ t.name }} ({{ t.role }})
          </option>
        </select>
        <p v-if="switchError" class="text-xs text-rose-600">{{ switchError }}</p>
      </div>
    </div>

    <div class="flex justify-end">
      <Button variant="danger" :loading="loggingOut" :disabled="loggingOut" @click="handleLogout">
        退出登录
      </Button>
    </div>
  </section>
</template>
