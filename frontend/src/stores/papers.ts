import { defineStore } from 'pinia'
import { papersApi } from '@/api/endpoints'
import type { Paper } from '@/types/api'

interface State {
  items: Paper[]
  total: number
  analyzed: number
  loading: boolean
  error: string | null
}

export const usePapersStore = defineStore('papers', {
  state: (): State => ({
    items: [],
    total: 0,
    analyzed: 0,
    loading: false,
    error: null,
  }),
  getters: {
    analyzedCount(state): number {
      return state.analyzed
    },
    totalCount(state): number {
      return state.total
    },
  },
  actions: {
    async fetchStats() {
      try {
        const s = await papersApi.stats()
        this.total = s.total
        this.analyzed = s.analyzed
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async fetch() {
      this.loading = true
      this.error = null
      try {
        const resp = await papersApi.list({ limit: 500 })
        this.items = resp.items
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },
  },
})
