import client, { API_BASE_URL } from './client'
import type {
  BackwardTrackResult,
  DigestResult,
  FailuresResponse,
  ForwardTrackResult,
  InboxItem,
  ListResponse,
  NetworkGraph,
  Paper,
  PaperDetail,
  Subscription,
  Task,
  TrackResponse,
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
      .get<ListResponse<Paper> & { limit: number; offset: number; total: number }>('/papers', { params })
      .then((r) => r.data),
  stats: () =>
    client.get<{ total: number; analyzed: number }>('/papers/stats').then((r) => r.data),
  get: (id: number) =>
    client.get<PaperDetail>(`/papers/${id}`).then((r) => r.data),
  getInsight: (id: number) =>
    client.get<{ content: string | null }>(`/papers/${id}/insight`).then((r) => r.data),
  forwardTrack: (id: number, body?: { refresh?: boolean; page_limit?: number; offset?: number; limit?: number }) =>
    client
      .post<TrackResponse<ForwardTrackResult>>(`/papers/${id}/forward-track`, body ?? {})
      .then((r) => r.data),
  backwardTrack: (id: number, body?: { refresh?: boolean; page_limit?: number; offset?: number; limit?: number }) =>
    client
      .post<TrackResponse<BackwardTrackResult>>(`/papers/${id}/backward-track`, body ?? {})
      .then((r) => r.data),
  promote: (id: number) =>
    client.post<Paper>(`/papers/${id}/promote`).then((r) => r.data),
  deleteBatch: (ids: number[]) =>
    client.delete<{ deleted: number }>('/papers/batch', { data: { ids } }).then((r) => r.data),
  moveBatch: (ids: number[], is_core: boolean) =>
    client.patch<{ updated: number }>('/papers/batch/tier', { ids, is_core }).then((r) => r.data),
  // 走 client.baseURL（默认 /api），反代/路径前缀变化时跟 axios 一致
  citationBibUrl: (id: number) => `${API_BASE_URL}/papers/${id}/citations.bib`,
  generateCitation: (id: number) =>
    client.post(`/papers/${id}/citation`, {}).then((r) => r.data),
  aiAnalyze: (id: number) =>
    client.post<Paper>(`/papers/${id}/ai-analyze`).then((r) => r.data),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    // 不显式设 Content-Type：axios 会自动写入带 boundary 的 multipart 头
    // 大 PDF + 慢网络可能需要超过默认 30s；放宽到 5 分钟
    return client
      .post<{ paper_id: number; task_id: number | null; deduped: boolean; stem?: string; reason?: string }>(
        '/papers/upload',
        form,
        { timeout: 5 * 60 * 1000 },
      )
      .then((r) => r.data)
  },
}

export const digestApi = {
  send: () => client.post<DigestResult>('/digest/send').then((r) => r.data),
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

export interface Recommendation {
  id: number
  external_id: string
  source: string
  title: string
  abstract: string | null
  authors_json: string[] | null
  year: number | null
  url: string | null
  matched_theme: string | null
  relevance_score: number
  reason: string | null
  created_at: string
  dismissed: boolean
  saved_to_library: boolean
}

export const recommendationsApi = {
  list: (limit = 50) =>
    client
      .get<{ items: Recommendation[]; total: number }>('/recommendations', { params: { limit } })
      .then((r) => r.data),
  dismiss: (id: number) => client.post(`/recommendations/${id}/dismiss`).then((r) => r.data),
  saveToLibrary: (id: number) =>
    client.post<{ ok: boolean; paper_id: number }>(`/recommendations/${id}/save-to-library`).then((r) => r.data),
}

export const profileApi = {
  regenerate: () => client.post('/profile/regenerate').then((r) => r.data),
}
