<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, ref } from 'vue'
import { exploreApi, subscriptionsApi } from '@/api/endpoints'
import type { ExploreCard, Subscription } from '@/types/api'
import SubscriptionSheet from '@/components/SubscriptionSheet.vue'

const RAIL_EASING = 'ease-in-out'
const ENTER_EASING = 'cubic-bezier(0.34, 1.56, 0.64, 1)'
const SLIDE_DUR = 240
const UNDO_THRESHOLD = 80
const CARD_GAP = 16

const cards = ref<ExploreCard[]>([])
const prevCard = ref<ExploreCard | null>(null)
const animating = ref(false)
const settingsOpen = ref(false)
const loading = ref(true)
const busy = ref(false)
const refillStatus = ref('')
const sub = ref<Subscription | null>(null)

const cardRef = ref<HTMLDivElement>()
const cardPrevRef = ref<HTMLDivElement>()
const cardNextRef = ref<HTMLDivElement>()
const cardContentRef = ref<HTMLDivElement>()

let sx = 0, sy = 0, swipeDir: 'h' | 'v' | null = null, cachedW = 0
let cardEl: HTMLElement | null = null
let isLoadingMore = false

function getCardW() {
  return (cardRef.value?.offsetWidth ?? 320) + CARD_GAP
}

function resetCardPositions() {
  ;[cardRef, cardPrevRef, cardNextRef].forEach(r =>
    r.value?.getAnimations().forEach(a => a.cancel())
  )
  if (cardRef.value) cardRef.value.style.transform = ''
  const W = getCardW()
  if (cardPrevRef.value) cardPrevRef.value.style.transform = `translateX(${-W}px) translateY(-50%)`
  if (cardNextRef.value) cardNextRef.value.style.transform = `translateX(${W}px) translateY(-50%)`
}

const EMPTY_HTML = `<div style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#64748b;text-align:center"><div>今天已刷完</div><div style="font-size:13px;color:#94a3b8;margin-top:6px">点击右上角「补充」拉取新论文</div></div>`

function stageCards() {
  if (cardContentRef.value)
    cardContentRef.value.innerHTML = cards.value[0]?.card_html ?? EMPTY_HTML
  if (cardNextRef.value) cardNextRef.value.innerHTML = cards.value[1]?.card_html ?? ''
  if (cardPrevRef.value) cardPrevRef.value.innerHTML = prevCard.value?.card_html ?? ''
  resetCardPositions()
}

function snapAllBack() {
  const m = cardRef.value?.style.transform?.match(/translateX\((-?[\d.]+)px\)/)
  const curDx = m ? parseFloat(m[1]) : 0
  const opts = { duration: 220, easing: ENTER_EASING }
  cardRef.value?.animate([{ transform: `translateX(${curDx}px)` }, { transform: 'none' }], opts)
  if (prevCard.value && cardPrevRef.value) {
    const W = cachedW || getCardW()
    cardPrevRef.value.animate(
      [
        { transform: `translateX(${-W + curDx}px) translateY(-50%)` },
        { transform: `translateX(${-W}px) translateY(-50%)` },
      ],
      opts
    )
  }
}

async function doAction(action: 'saved' | 'skipped' | 'passed') {
  if (animating.value || !cards.value[0] || !cardRef.value || !cardNextRef.value) return
  animating.value = true
  const card = cards.value[0]
  const W = getCardW()
  await Promise.all([
    cardRef.value.animate(
      [{ transform: 'translateX(0)' }, { transform: `translateX(${-W}px)` }],
      { duration: SLIDE_DUR, easing: RAIL_EASING, fill: 'forwards' }
    ).finished,
    cardNextRef.value.animate(
      [
        { transform: `translateX(${W}px) translateY(-50%)` },
        { transform: 'translateX(0) translateY(-50%)' },
      ],
      { duration: SLIDE_DUR, easing: RAIL_EASING, fill: 'forwards' }
    ).finished,
  ])
  prevCard.value = card
  cards.value = cards.value.slice(1)
  stageCards()
  animating.value = false
  exploreApi.recordAction(card.id, action).catch(() => {})
  if (cards.value.length < 3) loadMoreCards()
}

async function doUndo() {
  if (animating.value || !prevCard.value || !cardRef.value || !cardPrevRef.value) return
  animating.value = true
  const undoCard = prevCard.value
  const W = getCardW()
  const m = cardRef.value.style.transform?.match(/translateX\((-?[\d.]+)px\)/)
  const curDx = m ? parseFloat(m[1]) : 0
  await Promise.all([
    cardRef.value.animate(
      [{ transform: `translateX(${curDx}px)` }, { transform: `translateX(${W * 1.5}px)` }],
      { duration: SLIDE_DUR, easing: RAIL_EASING, fill: 'forwards' }
    ).finished,
    cardPrevRef.value.animate(
      [
        { transform: `translateX(${-W + curDx}px) translateY(-50%)` },
        { transform: 'translateX(0) translateY(-50%)' },
      ],
      { duration: SLIDE_DUR, easing: RAIL_EASING, fill: 'forwards' }
    ).finished,
  ])
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
    const res = await exploreApi.getCards(sub.value.id, 10)
    const newCards = (res.data.items as ExploreCard[]).filter(
      c => !cards.value.some(existing => existing.id === c.id)
    )
    if (newCards.length > 0) {
      cards.value = [...cards.value, ...newCards]
      if (!cardNextRef.value?.innerHTML && cards.value[1]) {
        cardNextRef.value!.innerHTML = cards.value[1].card_html
      }
    }
  } finally {
    isLoadingMore = false
  }
}

async function loadCards() {
  if (!sub.value) { cards.value = []; loading.value = false; nextTick(() => stageCards()); return }
  loading.value = true
  const res = await exploreApi.getCards(sub.value.id, 10)
  cards.value = res.data.items
  loading.value = false
  nextTick(() => stageCards())
}

async function loadSubscription() {
  const items = await subscriptionsApi.list({ active: true })
  sub.value = items.find((item: Subscription) => item.active && item.type === 'topic_search') ?? null
}

async function triggerRefill() {
  if (!sub.value || busy.value) return
  busy.value = true
  refillStatus.value = '正在从 OpenAlex 拉取论文…'
  try {
    await exploreApi.refill(sub.value.id)
    refillStatus.value = 'AI 分析中…'
    await loadCards()
    if (cards.value.length === 0) {
      for (let i = 0; i < 18; i++) {
        await new Promise(r => setTimeout(r, 10000))
        await loadCards()
        if (cards.value.length > 0) break
      }
    }
  } catch (e: any) {
    if (e?.response?.status !== 409) throw e
    await loadCards()
  } finally {
    busy.value = false
    refillStatus.value = ''
  }
}

function onTouchStart(e: TouchEvent) {
  if (animating.value) return
  sx = e.touches[0].clientX
  sy = e.touches[0].clientY
  swipeDir = null
  cachedW = getCardW()
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
  const W = cachedW
  if (dx > 0 && prevCard.value && cardPrevRef.value) {
    const travel = dx <= UNDO_THRESHOLD ? dx : UNDO_THRESHOLD + (dx - UNDO_THRESHOLD) * 0.25
    if (cardRef.value) cardRef.value.style.transform = `translateX(${travel}px)`
    cardPrevRef.value.style.transform = `translateX(${-W + travel}px) translateY(-50%)`
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
  await loadSubscription()
  await loadCards()
  cardEl = cardRef.value ?? null
  cardEl?.addEventListener('touchmove', onTouchMove, { passive: false })
})

onBeforeUnmount(() => {
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
        <button
          class="refill-btn"
          :class="{ 'refill-busy': busy }"
          :disabled="busy || !sub"
          @click="triggerRefill"
        >
          {{ busy ? '补充中…' : '+ 补充' }}
        </button>
        <button class="settings-btn" @click="settingsOpen = true">⚙</button>
      </div>
    </div>

    <div v-if="refillStatus" class="refill-status">{{ refillStatus }}</div>

    <div
      class="card-stage"
      @touchstart.passive="onTouchStart"
      @touchend.passive="onTouchEnd"
      @touchcancel.passive="onTouchCancel"
    >
      <div ref="cardPrevRef" class="card-offstage card-prev"></div>
      <div ref="cardNextRef" class="card-offstage card-next"></div>
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
  max-width: 480px;
  height: calc(100dvh - 56px);
  margin: 0 auto;
  gap: 12px;
  overflow: hidden;
}

.explore-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}

.sub-label { font-size: 18px; font-weight: 700; color: #0f172a; }
.pool-count { margin-top: 2px; font-size: 13px; color: #64748b; }

.refill-btn,
.settings-btn {
  border: 0;
  border-radius: 999px;
  font-weight: 700;
  cursor: pointer;
  padding: 8px 14px;
  white-space: nowrap;
}

.refill-btn {
  color: #0f172a;
  background: #e2e8f0;
  transition: background 0.2s, color 0.2s;
}

.refill-btn.refill-busy {
  background: #dbeafe;
  color: #2563eb;
  cursor: not-allowed;
  animation: pulse 1.5s ease-in-out infinite;
}

.settings-btn {
  background: #f1f5f9;
  color: #475569;
  font-size: 16px;
}

.refill-status {
  text-align: center;
  font-size: 13px;
  color: #2563eb;
  padding: 4px 0;
  animation: pulse 1.5s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.card-stage {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-x: clip;
}

.card-current,
.card-prev,
.card-next {
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
}

.card-current {
  position: absolute;
  inset: 0;
  z-index: 3;
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
  border-top: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 0 0 20px 20px;
}

.card-action-bar .btn-skip { background: #dc2626; color: #fff; border: 0; border-radius: 999px; min-height: 44px; font-weight: 700; cursor: pointer; font-size: 14px; }
.card-action-bar .btn-pass { background: #64748b; color: #fff; border: 0; border-radius: 999px; min-height: 44px; font-weight: 700; cursor: pointer; font-size: 14px; }
.card-action-bar .btn-save { background: #16a34a; color: #fff; border: 0; border-radius: 999px; min-height: 44px; font-weight: 700; cursor: pointer; font-size: 14px; }
.card-action-bar button:disabled { opacity: 0.55; cursor: not-allowed; }

.card-offstage {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  z-index: 1;
  pointer-events: none;
  padding: 22px;
  will-change: transform;
}

.card-prev { z-index: 1; }
.card-next { z-index: 2; }

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

