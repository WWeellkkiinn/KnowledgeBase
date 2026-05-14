import client from './client'
import type {
  BackwardTrackResult,
  FailuresResponse,
  ForwardTrackResult,
  InboxItem,
  ListResponse,
  NetworkGraph,
  Paper,
  PaperDetail,
  Subscription,
  Task,
} from '@/types/api'

export const networkApi = {
  get: (limit = 1000) =>
    client.get<NetworkGraph>('/network', { params: { limit } }).then((r) => r.data),
}

export const papersApi = {
  list: (params?: {
    status?: string
    source?: string
    tier?: 'core' | 'stub' | 'all'
    limit?: number
    offset?: number
  }) =>
    client
      .get<ListResponse<Paper> & { limit: number; offset: number }>('/papers', { params })
      .then((r) => r.data),
  stats: () =>
    client.get<{ total: number; analyzed: number }>('/papers/stats').then((r) => r.data),
  get: (id: number) =>
    client.get<PaperDetail>(`/papers/${id}`).then((r) => r.data),
  getInsight: (id: number) =>
    client.get<{ content: string | null }>(`/papers/${id}/insight`).then((r) => r.data),
  forwardTrack: (id: number, body?: { refresh?: boolean; limit?: number }) =>
    client
      .post<ForwardTrackResult>(`/papers/${id}/forward-track`, body ?? {})
      .then((r) => r.data),
  backwardTrack: (id: number, body?: { refresh?: boolean; limit?: number }) =>
    client
      .post<BackwardTrackResult>(`/papers/${id}/backward-track`, body ?? {})
      .then((r) => r.data),
  promote: (id: number) =>
    client.post<Paper>(`/papers/${id}/promote`).then((r) => r.data),
  citationBibUrl: (id: number) => `/api/papers/${id}/citations.bib`,
  generateCitation: (id: number) =>
    client.post(`/papers/${id}/citation`, {}).then((r) => r.data),
}

export const tasksApi = {
  list: (params?: { status?: string; type?: string; limit?: number }) =>
    client.get<ListResponse<Task>>('/tasks', { params }).then((r) => r.data.items),
}

export const subscriptionsApi = {
  list: (params?: { active?: boolean }) =>
    client
      .get<ListResponse<Subscription>>('/subscriptions', {
        params: params?.active ? { active: 1 } : undefined,
      })
      .then((r) => r.data.items),
  create: (body: {
    type: string
    target: Record<string, unknown>
    cron_expr: string
    active?: boolean
  }) => client.post<Subscription>('/subscriptions', body).then((r) => r.data),
  update: (id: number, body: Partial<{ active: boolean; cron_expr: string; target: Record<string, unknown> }>) =>
    client.patch<Subscription>(`/subscriptions/${id}`, body).then((r) => r.data),
  delete: (id: number, force = false) =>
    client.delete(`/subscriptions/${id}`, { params: force ? { force: 1 } : undefined }),
}

export const inboxApi = {
  list: (params?: { unread?: boolean }) =>
    client
      .get<ListResponse<InboxItem>>('/inbox', {
        params: params?.unread ? { unread: 1 } : undefined,
      })
      .then((r) => r.data.items),
  markRead: (id: number) =>
    client.post<InboxItem>(`/inbox/${id}/read`).then((r) => r.data),
}

export const healthApi = {
  ping: () => client.get<{ ok: boolean }>('/health').then((r) => r.data),
}

export const failuresApi = {
  list: () => client.get<FailuresResponse>('/failures').then((r) => r.data),
}
