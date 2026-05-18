import { defineStore } from 'pinia'
import { inboxApi, subscriptionsApi } from '@/api/endpoints'
import type { InboxItem, Subscription } from '@/types/api'

interface State {
  items: Subscription[]
  inbox: InboxItem[]
  loading: boolean
  error: string | null
}

let _fetchPromise: Promise<void> | null = null

export const useSubscriptionsStore = defineStore('subscriptions', {
  state: (): State => ({ items: [], inbox: [], loading: false, error: null }),
  getters: {
    activeCount(state): number {
      return state.items.filter((s) => s.active).length
    },
    unreadCount(state): number {
      return state.inbox.filter((i) => !i.notified).length
    },
  },
  actions: {
    async fetchAll() {
      if (_fetchPromise) return _fetchPromise
      this.loading = true
      this.error = null
      _fetchPromise = (async () => {
        try {
          const [subsResult, inboxResult] = await Promise.allSettled([
            subscriptionsApi.list(),
            inboxApi.list(),
          ])
          if (subsResult.status === 'fulfilled') this.items = subsResult.value
          else this.error = subsResult.reason instanceof Error ? subsResult.reason.message : String(subsResult.reason)
          if (inboxResult.status === 'fulfilled') this.inbox = inboxResult.value
        } finally {
          this.loading = false
          _fetchPromise = null
        }
      })()
      return _fetchPromise
    },
    async markRead(id: number) {
      const updated = await inboxApi.markRead(id)
      const idx = this.inbox.findIndex((i) => i.id === id)
      if (idx >= 0) this.inbox[idx] = updated
    },
  },
})
