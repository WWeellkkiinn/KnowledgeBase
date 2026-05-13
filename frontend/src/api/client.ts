import axios, { type AxiosInstance, AxiosError } from 'axios'

// dev：vite proxy 接管 /api → :5000
// prod：同源部署，baseURL 仍走相对路径
const client: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

client.interceptors.response.use(
  (resp) => resp,
  (err: AxiosError) => {
    // M3.1：先只透传，M3.2 起接全局错误 toast
    return Promise.reject(err)
  },
)

export default client
