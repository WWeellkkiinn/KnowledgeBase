import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type MeResponse } from '@/api/auth'

export interface TenantMembership {
  id: number
  name: string
  slug: string
  role: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<{ id: number; email: string; approval_status: string } | null>(null)
  const tenants = ref<TenantMembership[]>([])
  const activeTenantId = ref<number | null>(null)

  const isAuthenticated = computed(() => user.value !== null)

  function _applyMe(data: MeResponse) {
    user.value = {
      id: data.id,
      email: data.email,
      approval_status: data.approval_status,
    }
    tenants.value = data.memberships.map((m) => ({
      id: m.tenant_id,
      name: m.tenant_name,
      slug: m.tenant_slug,
      role: m.role,
    }))
    activeTenantId.value = data.active_tenant_id
  }

  async function fetchMe() {
    const data = await authApi.me()
    _applyMe(data)
  }

  async function login(email: string, password: string) {
    const data = await authApi.login({ email, password })
    _applyMe(data.user)
  }

  async function register(payload: { email: string; password?: string; reason: string }) {
    await authApi.register(payload)
  }

  async function requestMagicLink(email: string) {
    await authApi.requestMagicLink(email)
  }

  async function consumeMagicLink(sesame: string) {
    const data = await authApi.consumeMagicLink(sesame)
    _applyMe(data.user)
  }

  async function switchTenant(tenantId: number) {
    await authApi.switchTenant(tenantId)
    activeTenantId.value = tenantId
  }

  async function logout() {
    await authApi.logout()
    user.value = null
    tenants.value = []
    activeTenantId.value = null
  }

  function clear() {
    user.value = null
    tenants.value = []
    activeTenantId.value = null
  }

  return {
    user,
    tenants,
    activeTenantId,
    isAuthenticated,
    fetchMe,
    login,
    register,
    requestMagicLink,
    consumeMagicLink,
    switchTenant,
    logout,
    clear,
  }
})
