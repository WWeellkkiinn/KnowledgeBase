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

// 登录/登出后调用：丢掉旧 socket，下次 getSocket() 用新 token 重建
export function resetSocket(): void {
  if (_socket) {
    try {
      _socket.disconnect()
    } catch {
      // ignore
    }
    _socket = null
  }
}
