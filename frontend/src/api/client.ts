import axios, { type AxiosInstance, AxiosError } from 'axios'

export const API_BASE_URL = '/api'
export const API_TIMEOUT = 30_000

// Stub kept for socket.ts compatibility — SaaS auth uses session cookies, no bearer token.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function getToken(): string { return '' }

// 防止并发 401 触发多次跳转
let redirecting = false

// 校验 back 参数，挡住 //evil.com、/\evil.com 这类 protocol-relative / 反斜杠绕过
export function isSafeBackPath(back: string | null | undefined): boolean {
  if (!back || typeof back !== 'string') return false
  if (!back.startsWith('/')) return false
  if (back.startsWith('//')) return false
  if (back.startsWith('/\\')) return false
  return true
}

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

// dev：vite proxy 接管 /api → :5000
// prod：同源部署，baseURL 仍走相对路径
const client: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
  withCredentials: true,
})

client.interceptors.request.use((config) => {
  const csrf = getCsrfToken()
  if (csrf) {
    config.headers['X-CSRFToken'] = csrf
  }
  return config
})

client.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError) => {
    const status = err.response?.status
    const data = err.response?.data as Record<string, unknown> | undefined

    if (status === 401 && window.location.pathname !== '/login' && !redirecting) {
      redirecting = true
      setTimeout(() => { redirecting = false }, 5000)
      const current = window.location.pathname + window.location.search
      const back = isSafeBackPath(current) ? encodeURIComponent(current) : '/'
      window.location.href = `/login?back=${back}`
    }

    if (
      status === 403
      && typeof data?.code === 'string'
      && data.code === 'pending_approval'
      && window.location.pathname !== '/pending-approval'
      && !redirecting
    ) {
      redirecting = true
      setTimeout(() => { redirecting = false }, 5000)
      window.location.href = '/pending-approval'
    }

    return Promise.reject(err)
  },
)

export default client
