import client from './client'

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  email: string
  password?: string
  reason: string
}

export interface MeResponse {
  id: number
  email: string
  approval_status: 'pending' | 'approved' | 'rejected'
  memberships: Array<{ tenant_id: number; tenant_name: string; tenant_slug: string; role: string }>
  active_tenant_id: number | null
}

export interface LoginResponse {
  user: MeResponse
}

export interface RegisterResponse {
  message: string
}

export interface MagicLinkResponse {
  message: string
}

export interface ConsumeResponse {
  user: MeResponse
}

export const authApi = {
  me: () =>
    client.get<MeResponse>('/auth/me').then((r) => r.data),

  login: (payload: LoginPayload) =>
    client.post<LoginResponse>('/auth/login', payload).then((r) => r.data),

  register: (payload: RegisterPayload) =>
    client.post<RegisterResponse>('/auth/register', payload).then((r) => r.data),

  requestMagicLink: (email: string) =>
    client.post<MagicLinkResponse>('/auth/magic-link', { email }).then((r) => r.data),

  consumeMagicLink: (sesame: string) =>
    client.get<ConsumeResponse>('/auth/magic/consume', { params: { sesame } }).then((r) => r.data),

  switchTenant: (tenantId: number) =>
    client.post<{ ok: boolean }>('/auth/switch-tenant', { tenant_id: tenantId }).then((r) => r.data),

  logout: () =>
    client.post<{ ok: boolean }>('/auth/logout').then((r) => r.data),

  changePassword: (payload: { old_password: string; new_password: string }) =>
    client.post<{ status: string }>('/auth/change-password', payload).then((r) => r.data),
}
