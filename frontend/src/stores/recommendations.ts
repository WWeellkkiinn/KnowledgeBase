import { defineStore } from 'pinia'
import { recommendationsApi, profileApi, type Recommendation } from '@/api/endpoints'

export type { Recommendation }

let lastFetchId = 0

interface State {
  items: Recommendation[]
  loading: boolean
  error: string
  lastFetchedAt: string | null
  regenerating: boolean
}

export const useRecommendationsStore = defineStore('recommendations', {
  state: (): State => ({
    items: [],
    loading: false,
    error: '',
    lastFetchedAt: null,
    regenerating: false,
  }),
  getters: {
    unreadCount(state): number {
      return state.items.filter((i) => !i.dismissed && !i.saved_to_library).length
    },
    visible(state): Recommendation[] {
      return state.items.filter((i) => !i.dismissed && !i.saved_to_library)
    },
    topPicks(state): Recommendation[] {
      return [...state.items]
        .filter((i) => !i.dismissed && !i.saved_to_library)
        .sort((a, b) => b.relevance_score - a.relevance_score)
        .slice(0, 5)
    },
  },
  actions: {
    async fetch(limit = 50) {
      const fetchId = ++lastFetchId
      this.loading = true
      this.error = ''
      try {
        const data = await recommendationsApi.list(limit)
        if (fetchId !== lastFetchId) return
        this.items = data.items ?? []
        this.lastFetchedAt = new Date().toISOString()
      } catch (e: unknown) {
        if (fetchId !== lastFetchId) return
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        if (fetchId === lastFetchId) this.loading = false
      }
    },
    async dismiss(id: number) {
      const idx = this.items.findIndex((i) => i.id === id)
      const previous = idx >= 0 ? { ...this.items[idx] } : null
      if (idx >= 0) this.items[idx] = { ...this.items[idx], dismissed: true }
      try {
        await recommendationsApi.dismiss(id)
      } catch (e: unknown) {
        if (idx >= 0 && previous) this.items[idx] = previous
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async saveToLibrary(id: number) {
      const idx = this.items.findIndex((i) => i.id === id)
      const previous = idx >= 0 ? { ...this.items[idx] } : null
      if (idx >= 0) this.items[idx] = { ...this.items[idx], saved_to_library: true }
      try {
        await recommendationsApi.saveToLibrary(id)
      } catch (e: unknown) {
        if (idx >= 0 && previous) this.items[idx] = previous
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    clearDismissed() {
      this.items = this.items.filter((i) => !i.dismissed)
    },
    async regenerateProfile() {
      this.regenerating = true
      this.error = ''
      try {
        await profileApi.regenerate()
        await this.fetch()
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.regenerating = false
      }
    },
  },
})
