<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, ref } from 'vue'
import { exploreApi, subscriptionsApi } from '@/api/endpoints'
import type { ExploreCard, Subscription } from '@/types/api'
import SubscriptionSheet from '@/components/SubscriptionSheet.vue'
import { useSubscriptionsStore } from '@/stores/subscriptions'

const subsStore = useSubscriptionsStore()

const ENTER_EASING = 'cubic-bezier(0.34, 1.56, 0.64, 1)'
const SLIDE_DUR = 240
const UNDO_THRESHOLD = 80

const cards = ref<ExploreCard[]>([])
const prevCard = ref<ExploreCard | null>(null)
const animating = ref(false)
const settingsOpen = ref(false)
const loading = ref(true)
const sub = ref<Subscription | null>(null)

const cardRef = ref<HTMLDivElement>()
const cardContentRef = ref<HTMLDivElement>()

let sx = 0, sy = 0, swipeDir: 'h' | 'v' | null = null
let cardEl: HTMLElement | null = null
let isLoadingMore = false
let retryTimer: ReturnType<typeof setTimeout> | null = null

const EMPTY_HTML = `<div style="padding:48px 24px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#64748b;text-align:center;font-family:Inter,'Noto Sans SC',sans-serif"><svg width="40" height="40" viewBox="0 0 40 40" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="3 3"><circle cx="20" cy="20" r="16"/></svg><div style="font-size:14px;font-weight:500;color:#334155;margin-top:14px">暂时没有新内容</div><div style="font-size:12px;color:#94a3b8;margin-top:6px">正在后台为你准备，请稍后</div></div>`
const LOADING_HTML = `<div style="padding:48px 24px;display:flex;flex-direction:column;gap:12px;align-items:stretch"><div style="height:14px;background:#e2e8f0;border-radius:6px;animation:kb-pulse 1.5s ease-in-out infinite"></div><div style="height:14px;width:80%;background:#e2e8f0;border-radius:6px;animation:kb-pulse 1.5s ease-in-out infinite"></div><div style="height:14px;width:60%;background:#e2e8f0;border-radius:6px;animation:kb-pulse 1.5s ease-in-out infinite"></div></div><style>@keyframes kb-pulse{0%,100%{opacity:1}50%{opacity:.5}}</style>`

function stageCards() {
  if (cardRef.value) cardRef.value.style.transform = ''
  if (cardContentRef.value)
    cardContentRef.value.innerHTML = loading.value ? LOADING_HTML : (cards.value[0]?.card_html ?? EMPTY_HTML)
}

function snapAllBack() {
  const m = cardRef.value?.style.transform?.match(/translateX\((-?[\d.]+)px\)/)
  const curDx = m ? parseFloat(m[1]) : 0
  const opts = { duration: 220, easing: ENTER_EASING }
  cardRef.value?.animate([{ transform: `translateX(${curDx}px)` }, { transform: 'none' }], opts)
}

async function doAction(action: 'saved' | 'skipped' | 'passed') {
  if (animating.value || !cards.value[0] || !cardRef.value) return
  animating.value = true
  const card = cards.value[0]
  const W = (cardRef.value.offsetWidth ?? 320) + 16
  await cardRef.value.animate(
    [{ transform: 'translateX(0)' }, { transform: `translateX(${-W}px)` }],
    { duration: SLIDE_DUR, easing: 'ease-in-out', fill: 'forwards' }
  ).finished
  prevCard.value = card
  cards.value = cards.value.slice(1)
  stageCards()
  animating.value = false
  exploreApi.recordAction(card.id, action).catch(() => {})
  if (cards.value.length <= 10) loadMoreCards()
}

async function doUndo() {
  if (animating.value || !prevCard.value || !cardRef.value) return
  animating.value = true
  const undoCard = prevCard.value
  const W = (cardRef.value.offsetWidth ?? 320) + 16
  const m = cardRef.value.style.transform?.match(/translateX\((-?[\d.]+)px\)/)
  const curDx = m ? parseFloat(m[1]) : 0
  await cardRef.value.animate(
    [{ transform: `translateX(${curDx}px)` }, { transform: `translateX(${W * 1.5}px)` }],
    { duration: SLIDE_DUR, easing: 'ease-in-out', fill: 'forwards' }
  ).finished
  cards.value = [undoCard, ...cards.value]
  prevCard.value = null
  stageCards()
  animating.value = false
  exploreApi.undo(undoCard.id).catch(() => {})
}

async function loadMoreCards() {
  if (!sub.value || isLoadingMore) return
  isLoadingMore = true
  try {
    const existingIds = cards.value.map(c => c.id)
    const res = await exploreApi.getCards(sub.value.id, 10, existingIds)
    const newCards = (res.data.items as ExploreCard[]).filter(
      c => !cards.value.some(existing => existing.id === c.id)
    )
    if (newCards.length > 0) {
      cards.value = [...cards.value, ...newCards]
    }
  } finally {
    isLoadingMore = false
  }
}

function scheduleRetry() {
  if (retryTimer) return
  retryTimer = setTimeout(async () => {
    retryTimer = null
    if (cards.value.length === 0 && !loading.value && sub.value) {
      await loadCards()
    }
  }, 8000)
}

async function loadCards() {
  if (!sub.value) { cards.value = []; loading.value = false; nextTick(() => stageCards()); return }
  loading.value = true
  nextTick(() => stageCards())
  const res = await exploreApi.getCards(sub.value.id, 20)
  cards.value = res.data.items
  loading.value = false
  nextTick(() => stageCards())
  if (cards.value.length === 0) scheduleRetry()
}

async function loadSubscription() {
  const items = await subscriptionsApi.list({ active: true })
  sub.value = items.find((item: Subscription) => item.active) ?? null
}

function onTouchStart(e: TouchEvent) {
  if (animating.value) return
  sx = e.touches[0].clientX
  sy = e.touches[0].clientY
  swipeDir = null
}

function onTouchMove(e: TouchEvent) {
  if (animating.value || !cards.value[0]) return
  const dx = e.touches[0].clientX - sx
  const dy = e.touches[0].clientY - sy
  const adx = Math.abs(dx), ady = Math.abs(dy)
  if (swipeDir === null && (adx > 6 || ady > 6)) {
    swipeDir = adx > ady ? 'h' : 'v'
  }
  if (swipeDir !== 'h') return
  e.preventDefault()
  if (dx > 0 && prevCard.value) {
    const travel = dx <= UNDO_THRESHOLD ? dx : UNDO_THRESHOLD + (dx - UNDO_THRESHOLD) * 0.25
    if (cardRef.value) cardRef.value.style.transform = `translateX(${travel}px)`
  } else if (dx > 0) {
    const travel = Math.min(dx * 0.12, 18)
    if (cardRef.value) cardRef.value.style.transform = `translateX(${travel}px)`
  } else {
    const travel = dx * 0.85
    if (cardRef.value) cardRef.value.style.transform = `translateX(${travel}px)`
  }
}

function onTouchEnd(e: TouchEvent) {
  if (swipeDir !== 'h') { swipeDir = null; return }
  const dx = e.changedTouches[0].clientX - sx
  swipeDir = null
  if (dx > UNDO_THRESHOLD && prevCard.value) {
    doUndo()
  } else if (dx < -UNDO_THRESHOLD) {
    doAction('skipped')
  } else {
    snapAllBack()
  }
}

function onTouchCancel() {
  swipeDir = null
  if (!animating.value) snapAllBack()
}

onMounted(async () => {
  subsStore.fetchAll()
  await loadSubscription()
  await loadCards()
  cardEl = cardRef.value ?? null
  cardEl?.addEventListener('touchmove', onTouchMove, { passive: false })
})

onBeforeUnmount(() => {
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
  cardEl?.removeEventListener('touchmove', onTouchMove)
  cardEl = null
})
</script>

<template>
  <div class="explore-root">
    <div class="explore-header">
      <div>
        <div class="sub-label">{{ sub?.description || '探索' }}</div>
        <div class="pool-count">{{ cards.length }} 张卡片</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="settings-btn" @click="settingsOpen = true">⚙</button>
      </div>
    </div>

    <div
      class="card-stage"
      @touchstart.passive="onTouchStart"
      @touchend.passive="onTouchEnd"
      @touchcancel.passive="onTouchCancel"
    >
      <div ref="cardRef" class="card-current">
        <div ref="cardContentRef" class="card-content-area"></div>
        <div class="card-action-bar" v-if="!loading && cards.length > 0">
          <button class="btn-skip" :disabled="animating" @click="doAction('skipped')">不感兴趣</button>
          <button class="btn-pass" :disabled="animating" @click="doAction('passed')">已读</button>
          <button class="btn-save" :disabled="animating" @click="doAction('saved')">收藏</button>
        </div>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="settingsOpen" class="sheet-overlay" @click.self="settingsOpen = false">
      <div class="sheet-panel">
        <SubscriptionSheet @close="settingsOpen = false" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.explore-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  flex: 1;
  min-height: 0;
  gap: 12px;
  padding: 16px;
}

.explore-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  max-width: 640px;
  width: 100%;
  margin: 0 auto;
}

.sub-label { font-size: 18px; font-weight: 700; color: #0f172a; }
.pool-count { margin-top: 2px; font-size: 13px; color: #64748b; }

.settings-btn {
  border: 0;
  border-radius: 999px;
  font-weight: 700;
  cursor: pointer;
  padding: 8px 14px;
  white-space: nowrap;
  background: #f1f5f9;
  color: #475569;
  font-size: 16px;
}

.card-stage {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: 640px;
  width: 100%;
  margin: 0 auto;
}

.card-current {
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
  position: relative;
  width: 100%;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  will-change: transform;
  cursor: grab;
}

.card-content-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
  padding: 22px;
}

.card-action-bar {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  padding: 12px 16px;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
  border-top: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 0 0 20px 20px;
}

.card-action-bar .btn-skip { background: #dc2626; color: #fff; border: 0; border-radius: 999px; min-height: 44px; font-weight: 700; cursor: pointer; font-size: 14px; }
.card-action-bar .btn-pass { background: #64748b; color: #fff; border: 0; border-radius: 999px; min-height: 44px; font-weight: 700; cursor: pointer; font-size: 14px; }
.card-action-bar .btn-save { background: #16a34a; color: #fff; border: 0; border-radius: 999px; min-height: 44px; font-weight: 700; cursor: pointer; font-size: 14px; }
.card-action-bar button:disabled { opacity: 0.55; cursor: not-allowed; }

.sheet-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 50;
  display: flex;
  align-items: flex-end;
}

.sheet-panel {
  width: 100%;
  max-height: 90dvh;
  overflow-y: auto;
  background: #fff;
  border-radius: 16px 16px 0 0;
  padding: 16px;
}
</style>
