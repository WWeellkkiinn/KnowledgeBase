import { defineStore } from 'pinia'
import { tasksApi } from '@/api/endpoints'
import type { Task } from '@/types/api'

interface State {
  items: Task[]
  loading: boolean
  error: string | null
}

export const useTasksStore = defineStore('tasks', {
  state: (): State => ({ items: [], loading: false, error: null }),
  getters: {
    counts(state): Record<string, number> {
      const out: Record<string, number> = { queued: 0, running: 0, done: 0, failed: 0 }
      for (const t of state.items) out[t.status] = (out[t.status] ?? 0) + 1
      return out
    },
    recent(state): Task[] {
      return state.items.slice(0, 10)
    },
  },
  actions: {
    async fetch(limit = 100) {
      this.loading = true
      this.error = null
      try {
        this.items = await tasksApi.list({ limit })
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },
  },
})
