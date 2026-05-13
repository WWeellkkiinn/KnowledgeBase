import { defineStore } from 'pinia'
import { ensureConnected, useProgressSocket } from '@/api/socket'
import type { ProgressEvent } from '@/types/api'

const MAX_EVENTS = 200

interface State {
  connected: boolean
  // 客户端意图：用户希望关注的 task_ids。即使断线也保留，重连后自动续订。
  desired: Set<string>
  // 服务端确认的活跃订阅：emit('subscribe') 成功后加入；disconnect 时清空。
  active: Set<string>
  events: ProgressEvent[]
  inited: boolean
}

export const useProgressStore = defineStore('progress', {
  state: (): State => ({
    connected: false,
    desired: new Set(),
    active: new Set(),
    events: [],
    inited: false,
  }),
  getters: {
    eventsByTask: (state) => (taskId: string) =>
      state.events.filter((e) => e.task_id === taskId),
    recent: (state) => state.events.slice(-20).reverse(),
  },
  actions: {
    initOnce() {
      if (this.inited) return
      this.inited = true
      const s = useProgressSocket()
      s.on('connect', () => {
        this.connected = true
        // 断线重连：重新 emit 所有 desired 订阅（C1+C2 审查）
        for (const tid of this.desired) {
          s.emit('subscribe', { task_id: tid })
          this.active.add(tid)
        }
      })
      s.on('disconnect', () => {
        this.connected = false
        this.active = new Set()
      })
      s.on('event', (ev: ProgressEvent) => {
        this.events.push(ev)
        if (this.events.length > MAX_EVENTS) {
          this.events = this.events.slice(-MAX_EVENTS)
        }
      })
    },
    subscribe(taskId: string) {
      this.initOnce()
      this.desired.add(taskId)
      if (this.active.has(taskId)) return
      const s = ensureConnected()
      if (s.connected) {
        s.emit('subscribe', { task_id: taskId })
        this.active.add(taskId)
      }
      // 未连接时：'connect' handler 会按 desired 重发，避免重复 once 注册
    },
    unsubscribe(taskId: string) {
      const s = useProgressSocket()
      this.desired.delete(taskId)
      if (!this.active.has(taskId)) return
      s.emit('unsubscribe', { task_id: taskId })
      this.active.delete(taskId)
    },
  },
})
