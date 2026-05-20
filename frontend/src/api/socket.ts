// Progress event stream client.
//
// Replaces the old Socket.IO client with SSE (Server-Sent Events) — the SaaS
// backend (Django) exposes /api/progress/stream?task_id=<id>, which streams
// JSON-encoded events for one task.
//
// Public API kept compatible with the previous Pinia store consumers:
//   - subscribeTask(taskId, onEvent) → returns a disposer
//   - closeAll() — disconnect every active stream (used on logout)
//
// One EventSource per task_id. Browsers cap concurrent EventSources at ~6 per
// origin; since users normally watch 1–3 tasks at once this is fine.

import type { ProgressEvent } from '@/types/api'

type EventHandler = (ev: ProgressEvent) => void

interface Subscription {
  source: EventSource
  handler: EventHandler
}

const _active = new Map<string, Subscription>()

export function subscribeTask(taskId: string, onEvent: EventHandler): () => void {
  // If already open for this task, replace the handler (last writer wins).
  const existing = _active.get(taskId)
  if (existing) {
    existing.handler = onEvent
    return () => closeTask(taskId)
  }
  const url = `/api/progress/stream?task_id=${encodeURIComponent(taskId)}`
  const source = new EventSource(url, { withCredentials: true })
  const sub: Subscription = { source, handler: onEvent }
  _active.set(taskId, sub)

  source.onmessage = (msg: MessageEvent) => {
    try {
      const data = JSON.parse(msg.data) as ProgressEvent
      sub.handler(data)
    } catch {
      // Heartbeat (`:heartbeat`) and `event: open` frames arrive as empty data;
      // ignore JSON parse errors silently.
    }
  }
  source.onerror = () => {
    // EventSource auto-reconnects; if it gives up the readyState will be CLOSED.
    if (source.readyState === EventSource.CLOSED) {
      _active.delete(taskId)
    }
  }
  return () => closeTask(taskId)
}

export function closeTask(taskId: string): void {
  const sub = _active.get(taskId)
  if (!sub) return
  try { sub.source.close() } catch { /* ignore */ }
  _active.delete(taskId)
}

export function closeAll(): void {
  for (const taskId of [..._active.keys()]) closeTask(taskId)
}

// Legacy export kept so callers that import `resetSocket` from older code paths
// (e.g. logout flow in stores/auth.ts) continue to work after the swap.
export async function resetSocket(): Promise<void> {
  closeAll()
}
