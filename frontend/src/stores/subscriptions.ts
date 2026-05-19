import { defineStore } from 'pinia'
import { subscriptionsApi } from '@/api/endpoints'
import type { Subscription } from '@/types/api'

interface State {
  items: Subscription[]
  loading: boolean
  error: string | null
}

let _fetchPromise: Promise<void> | null = null

export const useSubscriptionsStore = defineStore('subscriptions', {
  state: (): State => ({ items: [], loading: false, error: null }),
  getters: {
    activeCount(state): number {
      return state.items.filter((s) => s.active).length
    },
  },
  actions: {
    async fetchAll(force = false) {
      if (!force && this.items.length > 0) return
      if (_fetchPromise) return _fetchPromise
      this.loading = true
      this.error = null
      _fetchPromise = (async () => {
        try {
          this.items = await subscriptionsApi.list()
        } catch (e) {
          this.error = e instanceof Error ? e.message : String(e)
        } finally {
          this.loading = false
          _fetchPromise = null
        }
      })()
      return _fetchPromise
    },
  },
})
