<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { exploreApi, subscriptionsApi } from '@/api/endpoints'
import type { ExploreCard, Subscription } from '@/types/api'

const cards = ref<ExploreCard[]>([])
const sub = ref<Subscription | null>(null)
const cardRef = ref<HTMLDivElement | null>(null)
const loading = ref(true)
const busy = ref(false)
const refillStatus = ref('')
const exiting = ref<'left' | 'right' | 'down' | null>(null)
const touchStartX = ref(0)
const touchStartY = ref(0)

const currentCard = computed(() => cards.value[0] ?? null)
const prevCard = computed(() => cards.value[1] ?? null)
const nextCard = computed(() => cards.value[2] ?? null)
const poolCount = computed(() => cards.value.length)
const subLabel = computed(() => sub.value?.description || '探索')

function renderCard() {
  nextTick(() => {
    if (cardRef.value) {
      cardRef.value.innerHTML = currentCard.value?.card_html ?? ''
    }
  })
}

async function loadCards() {
  if (!sub.value) {
    cards.value = []
    loading.value = false
    renderCard()
    return
  }
  loading.value = true
  const res = await exploreApi.getCards(sub.value.id)
  cards.value = res.data.items
  loading.value = false
  renderCard()
}

async function loadSubscription() {
  const items = await subscriptionsApi.list({ active: true })
  sub.value = items.find((item) => item.active && item.type === 'topic_search') ?? null
}

async function doAction(action: 'saved' | 'skipped' | 'passed') {
  const card = currentCard.value
  if (!card || busy.value) return
  busy.value = true
  exiting.value = action === 'saved' ? 'right' : action === 'skipped' ? 'left' : 'down'
  await exploreApi.recordAction(card.id, action)
  window.setTimeout(() => {
    cards.value = cards.value.slice(1)
    exiting.value = null
    busy.value = false
    renderCard()
  }, 220)
}

async function triggerRefill() {
  if (!sub.value || busy.value) return
  busy.value = true
  refillStatus.value = '正在从 OpenAlex 拉取论文…'
  try {
    await exploreApi.refill(sub.value.id)
    refillStatus.value = 'AI 分析中，稍后自动刷新…'
    // 后台处理中，轮询直到有卡片可用（最多等 3 分钟）
    for (let i = 0; i < 18; i++) {
      await new Promise(r => setTimeout(r, 10000))
      await loadCards()
      if (cards.value.length > 0) break
    }
  } catch (e: any) {
    if (e?.response?.status !== 409) throw e
    await loadCards()
  } finally {
    busy.value = false
    refillStatus.value = ''
  }
}

function onTouchStart(event: TouchEvent) {
  const touch = event.touches[0]
  touchStartX.value = touch.clientX
  touchStartY.value = touch.clientY
}

function onTouchEnd(event: TouchEvent) {
  const touch = event.changedTouches[0]
  const dx = touch.clientX - touchStartX.value
  const dy = touch.clientY - touchStartY.value
  if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy)) {
    doAction(dx > 0 ? 'saved' : 'skipped')
  } else if (dy > 80) {
    doAction('passed')
  }
}

watch(currentCard, renderCard)

onMounted(async () => {
  await loadSubscription()
  await loadCards()
})
</script>

<template>
  <div class="explore-root">
    <div class="explore-header">
      <div>
        <div class="sub-label">{{ subLabel }}</div>
        <div class="pool-count">{{ poolCount }} 张卡片</div>
      </div>
      <button class="refill-btn" :disabled="busy || !sub" @click="triggerRefill">补充</button>
    </div>

    <div v-if="refillStatus" class="refill-status">{{ refillStatus }}</div>
    <div v-if="loading" class="empty-state">加载中...</div>
    <div v-else-if="!currentCard && !refillStatus" class="empty-state">
      <div>今天已刷完</div>
      <div style="font-size:13px;color:#94a3b8;margin-top:6px">点击右上角「补充」拉取新论文</div>
    </div>
    <template v-else>
      <div class="card-stage" @touchstart.passive="onTouchStart" @touchend.passive="onTouchEnd">
        <div v-if="prevCard" id="card-prev" class="card-prev" inert v-html="prevCard.card_html"></div>
        <div v-if="nextCard" id="card-next" class="card-next" inert v-html="nextCard.card_html"></div>
        <div id="card" ref="cardRef" :class="['card', exiting ? 'exit-' + exiting : '']"></div>
      </div>

      <div class="action-row">
        <button class="btn-skip" :disabled="busy" @click="doAction('skipped')">跳过</button>
        <button class="btn-pass" :disabled="busy" @click="doAction('passed')">稍后</button>
        <button class="btn-save" :disabled="busy" @click="doAction('saved')">保存</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.explore-root {
  display: flex;
  flex-direction: column;
  max-width: 480px;
  height: calc(100dvh - 56px);
  margin: 0 auto;
  gap: 16px;
}

.explore-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.refill-status {
  text-align: center;
  font-size: 13px;
  color: #2563eb;
  padding: 8px 0 0;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.sub-label {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.pool-count {
  margin-top: 2px;
  font-size: 13px;
  color: #64748b;
}

.refill-btn,
.action-row button {
  border: 0;
  border-radius: 999px;
  font-weight: 700;
  cursor: pointer;
}

.refill-btn {
  padding: 8px 14px;
  color: #0f172a;
  background: #e2e8f0;
}

.card-stage {
  position: relative;
  flex: 1;
  min-height: 0;
}

#card,
#card-prev,
#card-next {
  position: absolute;
  inset: 0;
  overflow: auto;
  padding: 22px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
}

#card {
  z-index: 3;
  transition: transform 0.22s ease, opacity 0.22s ease;
}

#card-prev {
  z-index: 1;
  transform: translateY(18px) scale(0.94);
  opacity: 0.45;
}

#card-next {
  z-index: 2;
  transform: translateY(10px) scale(0.97);
  opacity: 0.7;
}

.exit-left {
  transform: translateX(-120%) rotate(-8deg);
  opacity: 0;
}

.exit-right {
  transform: translateX(120%) rotate(8deg);
  opacity: 0;
}

.exit-down {
  transform: translateY(120%);
  opacity: 0;
}

.action-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.action-row button {
  min-height: 44px;
  color: #fff;
}

.btn-skip {
  background: #dc2626;
}

.btn-pass {
  background: #64748b;
}

.btn-save {
  background: #16a34a;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.empty-state {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  color: #64748b;
}
</style>
