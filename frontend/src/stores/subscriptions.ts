import { defineStore } from 'pinia'
import { inboxApi, subscriptionsApi } from '@/api/endpoints'
import type { InboxItem, Subscription } from '@/types/api'

interface State {
  items: Subscription[]
  inbox: InboxItem[]
  loading: boolean
  error: string | null
}

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
      this.loading = true
      this.error = null
      try {
        const [subs, inbox] = await Promise.all([
          subscriptionsApi.list(),
          inboxApi.list(),
        ])
        this.items = subs
        this.inbox = inbox
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },
    async markRead(id: number) {
      const updated = await inboxApi.markRead(id)
      const idx = this.inbox.findIndex((i) => i.id === id)
      if (idx >= 0) this.inbox[idx] = updated
    },
  },
})
