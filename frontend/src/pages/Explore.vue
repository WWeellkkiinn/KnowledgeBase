<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, reactive } from 'vue'
import { exploreApi, subscriptionsApi } from '@/api/endpoints'
import type { ExploreCard as ExploreCardItem, Subscription } from '@/types/api'
import SubscriptionSheet from '@/components/SubscriptionSheet.vue'
import ExploreSidePanel from '@/components/explore/ExploreSidePanel.vue'
import ExploreCard from '@/components/explore/ExploreCard.vue'
import ExploreLoading from '@/components/explore/ExploreLoading.vue'
import ExploreEmpty from '@/components/explore/ExploreEmpty.vue'
import { useSubscriptionsStore } from '@/stores/subscriptions'

const subsStore = useSubscriptionsStore()

const ENTER_EASING = 'cubic-bezier(0.34, 1.56, 0.64, 1)'
const SLIDE_DUR = 240
const UNDO_THRESHOLD = 80

const cards = ref<ExploreCardItem[]>([])
const prevCard = ref<ExploreCardItem | null>(null)
const prevAction = ref<'saved' | 'skipped' | 'passed' | null>(null)
const sessionStats = reactive({ saved: 0, skipped: 0, passed: 0 })
const animating = ref(false)
const settingsOpen = ref(false)
const loading = ref(true)
const sub = ref<Subscription | null>(null)
const poolCount = ref(0)
const isFilling = ref(false)

const cardRef = ref<HTMLDivElement>()

let sx = 0, sy = 0, swipeDir: 'h' | 'v' | null = null
let isLoadingMore = false
let retryTimer: ReturnType<typeof setTimeout> | null = null
let snapAnim: Animation | null = null
let actionQueue: Promise<unknown> = Promise.resolve()
function queueRecord(fn: () => Promise<unknown>) {
  actionQueue = actionQueue.then(fn).catch(() => {})
}

function snapAllBack() {
  if (snapAnim) { snapAnim.cancel(); snapAnim = null }
  const m = cardRef.value?.style.transform?.match(/translateX\((-?[\d.]+)px\)/)
  const curDx = m ? parseFloat(m[1]) : 0
  const opts = { duration: 220, easing: ENTER_EASING }
  const animation = cardRef.value?.animate([{ transform: `translateX(${curDx}px)` }, { transform: 'none' }], opts)
  if (animation) {
    snapAnim = animation
    animation.onfinish = () => {
      if (cardRef.value) cardRef.value.style.transform = ''
      snapAnim = null
    }
  }
}

async function doAction(action: 'saved' | 'skipped' | 'passed') {
  if (animating.value || !cards.value[0] || !cardRef.value) return
  animating.value = true
  const card = cards.value[0]
  try {
    const W = (cardRef.value.offsetWidth ?? 320) + 16
    const anim = cardRef.value.animate(
      [{ transform: 'translateX(0)' }, { transform: `translateX(${-W}px)` }],
      { duration: SLIDE_DUR, easing: 'ease-in-out', fill: 'forwards' }
    )
    await anim.finished.catch(() => {})
    anim.cancel()
    prevCard.value = card
    prevAction.value = action
    sessionStats[action]++
    cards.value = cards.value.slice(1)
    queueRecord(() => exploreApi.recordAction(card.id, action))
    if (cards.value.length <= 10) loadMoreCards()
  } finally {
    animating.value = false
  }
}

async function doUndo() {
  if (animating.value || !prevCard.value || !cardRef.value) return
  animating.value = true
  const undoCard = prevCard.value
  try {
    const W = (cardRef.value.offsetWidth ?? 320) + 16
    const m = cardRef.value.style.transform?.match(/translateX\((-?[\d.]+)px\)/)
    const curDx = m ? parseFloat(m[1]) : 0
    const anim = cardRef.value.animate(
      [{ transform: `translateX(${curDx}px)` }, { transform: `translateX(${W * 1.5}px)` }],
      { duration: SLIDE_DUR, easing: 'ease-in-out', fill: 'forwards' }
    )
    await anim.finished.catch(() => {})
    anim.cancel()
    cards.value = [undoCard, ...cards.value]
    if (prevAction.value) {
      sessionStats[prevAction.value] = Math.max(0, sessionStats[prevAction.value] - 1)
    }
    prevCard.value = null
    prevAction.value = null
    queueRecord(() => exploreApi.undo(undoCard.id))
  } finally {
    animating.value = false
  }
}

async function loadMoreCards() {
  if (!sub.value || isLoadingMore) return
  isLoadingMore = true
  try {
    const existingIds = cards.value.map(c => c.id)
    const res = await exploreApi.getCards(sub.value.id, 10, existingIds)
    poolCount.value = res.data.pool_count
    isFilling.value = res.data.is_filling
    const newCards = (res.data.items as ExploreCardItem[]).filter(
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
  if (!sub.value) { cards.value = []; loading.value = false; return }
  loading.value = true
  try {
    const res = await exploreApi.getCards(sub.value.id, 20)
    poolCount.value = res.data.pool_count
    isFilling.value = res.data.is_filling
    if (cards.value.length === 0) {
      cards.value = res.data.items
      if (cards.value.length === 0) scheduleRetry()
    }
  } catch {
    cards.value = []
    scheduleRetry()
  } finally {
    loading.value = false
  }
}

async function loadSubscription() {
  const items = await subscriptionsApi.list({ active: true })
  sub.value = items.find((item: Subscription) => item.active) ?? null
}

function onTouchStart(e: TouchEvent) {
  if (animating.value) return
  if (snapAnim) { snapAnim.cancel(); snapAnim = null }
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
    const travel = -Math.min(Math.abs(dx) * 0.12, 18)
    if (cardRef.value) cardRef.value.style.transform = `translateX(${travel}px)`
  }
}

function onTouchEnd(e: TouchEvent) {
  if (swipeDir !== 'h') { swipeDir = null; return }
  const dx = e.changedTouches[0].clientX - sx
  swipeDir = null
  if (dx > UNDO_THRESHOLD && prevCard.value) {
    doUndo()
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
})

onBeforeUnmount(() => {
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
})
</script>

<template>
  <div class="explore-root">
    <div class="explore-header">
      <div>
        <div class="sub-label">{{ sub?.description || '探索' }}</div>
        <div class="pool-count">
          池中候选 {{ poolCount }} 张
          <span v-if="isFilling" class="filling-tag">自动补给中…</span>
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="settings-btn" @click="settingsOpen = true">⚙</button>
      </div>
    </div>

    <div class="explore-body">
      <div
        class="card-stage"
        @touchstart.passive="onTouchStart"
        @touchend.passive="onTouchEnd"
        @touchcancel.passive="onTouchCancel"
      >
        <div ref="cardRef" :key="cards[0]?.id ?? 'empty'" class="card-current" @touchmove="onTouchMove">
          <div class="card-content-area">
            <ExploreLoading v-if="loading" />
            <ExploreEmpty v-else-if="!cards[0]" />
            <ExploreCard v-else :card="cards[0].card" />
          </div>
          <div class="card-action-bar" v-if="!loading && cards.length > 0">
            <button class="btn-skip" :disabled="animating" @click="doAction('skipped')"><span class="btn-icon">✕</span><span class="btn-label">不感兴趣</span></button>
            <button class="btn-pass" :disabled="animating" @click="doAction('passed')"><span class="btn-icon">✓</span><span class="btn-label">已读</span></button>
            <button class="btn-save" :disabled="animating" @click="doAction('saved')"><span class="btn-icon">★</span><span class="btn-label">收藏</span></button>
          </div>
        </div>
      </div>
      <ExploreSidePanel
        class="hidden-mobile"
        :prev-card="prevCard"
        :prev-action="prevAction"
        :remaining-count="cards.length"
        :session-stats="sessionStats"
        @undo="doUndo"
      />
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
  padding: 24px 16px 16px;
}

@media (min-width: 640px) {
  .explore-root { padding-left: 24px; padding-right: 24px; }
}

@media (min-width: 1024px) {
  .explore-root { padding-left: 32px; padding-right: 32px; }
}

.explore-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  width: 100%;
  max-width: 1024px;
  margin: 0 auto;
}

.sub-label { font-size: 18px; font-weight: 700; color: #0f172a; }
.pool-count { margin-top: 2px; font-size: 13px; color: #64748b; }
.filling-tag {
  margin-left: 8px;
  font-size: 11px;
  color: #4338ca;
  background: #e0e7ff;
  padding: 1px 8px;
  border-radius: 9999px;
  animation: filling-pulse 1.6s ease-in-out infinite;
}
@keyframes filling-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

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

.explore-body {
  flex: 1;
  min-height: 0;
  display: flex;
  justify-content: flex-start;
  gap: 24px;
  width: 100%;
  max-width: 1024px;
  margin: 0 auto;
}

.hidden-mobile {
  display: none;
}

@media (min-width: 1024px) {
  .hidden-mobile {
    display: flex;
  }
}

.card-stage {
  flex: 1;
  min-height: 0;
  max-width: 640px;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
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
  flex: 0 1 auto;
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

.card-action-bar button {
  height: 44px;
  font-size: 14px;
  font-weight: 600;
  border-radius: 999px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: background-color 0.15s, border-color 0.15s, color 0.15s, transform 0.1s;
}
.card-action-bar button:active:not(:disabled) { transform: scale(0.97); }
.card-action-bar .btn-icon { font-size: 14px; line-height: 1; }

.card-action-bar .btn-skip {
  background: #ffedd5;
  color: #c2410c;
  border: 1px solid #fed7aa;
}
.card-action-bar .btn-skip:hover:not(:disabled) {
  background: #fed7aa;
  border-color: #fdba74;
}

.card-action-bar .btn-pass {
  background: #e0e7ff;
  color: #4338ca;
  border: 1px solid #c7d2fe;
}
.card-action-bar .btn-pass:hover:not(:disabled) {
  background: #c7d2fe;
  border-color: #a5b4fc;
}

.card-action-bar .btn-save {
  background: #0f766e;
  color: #fff;
  border: 0;
  box-shadow: 0 1px 2px rgba(15, 118, 110, 0.18);
}
.card-action-bar .btn-save:hover:not(:disabled) {
  background: #115e59;
}
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
