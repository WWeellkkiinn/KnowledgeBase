import { defineStore } from 'pinia'
import { closeAll, closeTask, subscribeTask } from '@/api/socket'
import type { ProgressEvent } from '@/types/api'

const MAX_EVENTS = 200

interface State {
  // Client intent: tasks the user wants to follow.
  desired: Set<string>
  // Tasks with an open EventSource right now.
  active: Set<string>
  events: ProgressEvent[]
}

export const useProgressStore = defineStore('progress', {
  state: (): State => ({
    desired: new Set(),
    active: new Set(),
    events: [],
  }),
  getters: {
    // Connected = at least one stream live. Kept for component compatibility.
    connected: (state) => state.active.size > 0,
    eventsByTask: (state) => (taskId: string) =>
      state.events.filter((e) => e.task_id === taskId),
    recent: (state) => state.events.slice(-20).reverse(),
  },
  actions: {
    _record(ev: ProgressEvent) {
      this.events.push(ev)
      if (this.events.length > MAX_EVENTS) {
        this.events = this.events.slice(-MAX_EVENTS)
      }
    },
    subscribe(taskId: string) {
      if (this.active.has(taskId)) {
        this.desired.add(taskId)
        return
      }
      this.desired.add(taskId)
      subscribeTask(taskId, (ev) => this._record(ev))
      this.active.add(taskId)
    },
    unsubscribe(taskId: string) {
      this.desired.delete(taskId)
      if (!this.active.has(taskId)) return
      closeTask(taskId)
      this.active.delete(taskId)
    },
    closeAll() {
      closeAll()
      this.active.clear()
      this.desired.clear()
    },
  },
})
