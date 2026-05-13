// /progress namespace 的 Socket.IO 客户端单例。
// 后端定义见 app/sockets/progress.py：subscribe/unsubscribe by task_id，回放缓冲。
// dev：vite proxy 转发 ws；prod：同源部署。
import { io, type Socket } from 'socket.io-client'

let _socket: Socket | null = null

export function useProgressSocket(): Socket {
  if (_socket === null) {
    _socket = io('/progress', {
      autoConnect: false,
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
