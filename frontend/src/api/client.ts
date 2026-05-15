import axios, { type AxiosInstance, AxiosError } from 'axios'
// 注意：故意不在此处 import { resetSocket } from './socket'。
// socket.ts 依赖本文件的 getToken，若顶层互相 import 会形成循环依赖，
// 在某些求值顺序下 resetSocket 可能为 undefined，导致 401 拦截器抛 TypeError 中断登出流程。
// 改为 401 拦截器内动态 import，单向化模块依赖。

export const TOKEN_KEY = 'KB_API_TOKEN'
export const API_BASE_URL = '/api'
export const API_TIMEOUT = 30_000

export function getToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    // SecurityError（隐私模式禁用 storage）等：降级为无 token
    return ''
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token)
  } catch (e) {
    // QuotaExceededError / SecurityError：不影响后续流程
    console.warn('[client] setToken failed:', e)
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY)
  } catch (e) {
    console.warn('[client] clearToken failed:', e)
  }
}

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

// dev：vite proxy 接管 /api → :5000
// prod：同源部署，baseURL 仍走相对路径
const client: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
})

// 用裸 axios 验证 token，避开 401 拦截器（否则验证失败会触发硬跳转）
export async function validateToken(token: string): Promise<void> {
  await axios.get(`${API_BASE_URL}/papers`, {
    params: { limit: 1 },
    timeout: API_TIMEOUT,
    headers: { Authorization: `Bearer ${token}` },
  })
}

// 公网部署：所有请求自动注入 Bearer token（本地 dev 未设 token 时为空，后端放行）
client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError) => {
    // 401：清掉无效 token 并跳登录页（避免无限刷新；登录页本身不会触发拦截）
    if (
      err.response?.status === 401
      && window.location.pathname !== '/login'
      && !redirecting
    ) {
      redirecting = true
      // 5 秒后允许下一波 401 触发跳转；防止跳转被浏览器/router 拦截后永久卡死
      setTimeout(() => { redirecting = false }, 5000)
      clearToken()
      // 断开旧 socket，避免登录后 /progress 仍用过期 token。
      // 动态 import 打破 client ↔ socket 循环依赖；await 确保 transport 关闭后再跳转，
      // 防止 in-flight 帧带旧 token 抵达 server。失败兜底为 noop。
      await import('./socket').then(({ resetSocket }) => resetSocket()).catch(() => {})
      const current = window.location.pathname + window.location.search
      const back = isSafeBackPath(current) ? encodeURIComponent(current) : '/'
      window.location.href = `/login?back=${back}`
    }
    return Promise.reject(err)
  },
)

export default client
