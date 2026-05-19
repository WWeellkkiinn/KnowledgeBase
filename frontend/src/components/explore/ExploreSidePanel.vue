<script setup lang="ts">
import { computed } from 'vue'
import type { ExploreCard } from '@/types/api'

const props = defineProps<{
  prevCard: ExploreCard | null
  prevAction: 'saved' | 'skipped' | 'passed' | null
  remainingCount: number
  sessionStats: { saved: number; skipped: number; passed: number }
}>()

const emit = defineEmits<{
  undo: []
}>()

const actionLabel = computed(() => {
  if (!props.prevAction) return ''
  return { saved: '已收藏', passed: '已读', skipped: '不感兴趣' }[props.prevAction]
})

const actionBadgeClass = computed(() => {
  if (!props.prevAction) return ''
  return {
    saved: 'badge-saved',
    passed: 'badge-passed',
    skipped: 'badge-skipped',
  }[props.prevAction]
})
</script>

<template>
  <aside class="side-panel">
    <!-- Section 1: 上一张 -->
    <div class="panel-section">
      <div class="section-label">上一张</div>
      <div v-if="prevCard" class="prev-card">
        <div class="prev-action-badge" :class="actionBadgeClass">
          {{ actionLabel }}
        </div>
        <div class="prev-title">#{{ prevCard.id }}</div>
        <button class="undo-btn" @click="emit('undo')">↶ 撤销</button>
      </div>
      <div v-else class="empty-hint">暂无可撤销的卡片</div>
    </div>

    <!-- Section 2: 本次会话 -->
    <div class="panel-section">
      <div class="section-label">本次会话</div>
      <div class="stat-row">
        <span class="stat-num text-green">{{ sessionStats.saved }}</span>
        <span class="stat-label">收藏</span>
      </div>
      <div class="stat-row">
        <span class="stat-num text-slate">{{ sessionStats.passed }}</span>
        <span class="stat-label">已读</span>
      </div>
      <div class="stat-row">
        <span class="stat-num text-red">{{ sessionStats.skipped }}</span>
        <span class="stat-label">不感兴趣</span>
      </div>
    </div>

    <!-- Section 3: 队列 -->
    <div class="panel-section">
      <div class="section-label">队列</div>
      <div class="queue-count">剩余 {{ remainingCount }} 张</div>
    </div>
  </aside>
</template>

<style scoped>
.side-panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-self: flex-start;
  padding-top: 4px;
}

.panel-section {
  background: var(--color-bg, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 12px);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #94a3b8;
}

.prev-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prev-action-badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 999px;
  width: fit-content;
}

.badge-saved  { background: #f0fdf4; color: #15803d; }
.badge-passed { background: #f1f5f9; color: #475569; }
.badge-skipped { background: #fef2f2; color: #b91c1c; }

.prev-title {
  font-size: 14px;
  font-weight: 500;
  color: #334155;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.undo-btn {
  width: 100%;
  background: #f1f5f9;
  border: 0;
  border-radius: 999px;
  padding: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #334155;
  cursor: pointer;
  transition: background 0.15s;
}
.undo-btn:hover { background: #e2e8f0; }

.empty-hint {
  font-size: 13px;
  color: #94a3b8;
}

.stat-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-num {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.text-green  { color: #16a34a; }
.text-slate  { color: #475569; }
.text-red    { color: #dc2626; }

.stat-label {
  font-size: 12px;
  color: #64748b;
}

.queue-count {
  font-size: 14px;
  color: #334155;
}
</style>
