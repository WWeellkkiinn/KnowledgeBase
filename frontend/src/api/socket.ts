// /progress namespace 的 Socket.IO 客户端单例。
// 后端定义见 app/sockets/progress.py：subscribe/unsubscribe by task_id，回放缓冲。
// dev：vite proxy 转发 ws；prod：同源部署。
import { io, type Socket } from 'socket.io-client'
import { getToken } from './client'

let _socket: Socket | null = null

export function useProgressSocket(): Socket {
  if (_socket === null) {
    _socket = io('/progress', {
      autoConnect: false,
      // 函数形式：每次（重）连接前重新读取，token 在登录页改了立刻生效
      auth: (cb) => cb({ token: getToken() }),
      transports: ['websocket', 'polling'],
    })
  }
  return _socket
}

export function ensureConnected(): Socket {
  const s = useProgressSocket()
  if (!s.connected) s.connect()
  return s
}

// 登录/登出后调用：丢掉旧 socket，下次 getSocket() 用新 token 重建。
// 返回 Promise：等 underlying transport 真正发出 disconnect 包后再 resolve，
// 否则调用方立刻跳转会让旧 transport 的 in-flight 帧带着旧 token 抵达 server。
// 1s 超时兜底，避免 socket 永远不触发 disconnect 事件时卡住登出流程。
export async function resetSocket(): Promise<void> {
  const s = _socket
  _socket = null
  if (!s) return
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, 1000)
    try {
      s.once('disconnect', () => {
        clearTimeout(timer)
        resolve()
      })
      s.disconnect()
    } catch {
      clearTimeout(timer)
      resolve()
    }
  })
}
