<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import StatCard from '@/components/StatCard.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import Button from '@/components/ui/Button.vue'
import { papersApi } from '@/api/endpoints'

const stats = ref<{ total: number; analyzed: number; new_this_week: number; core_count: number } | null>(null)
const refreshing = ref(false)

const todayLabel = computed(() => '今天 ' + new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }))

async function refresh() {
  refreshing.value = true
  try {
    const r = await papersApi.stats()
    stats.value = r as any
  } catch { /* ignore */ } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  refresh()
})
</script>

<template>
  <section class="space-y-6">
    <PageHeader title="概览" :subtitle="todayLabel">
      <template #actions>
        <Button
          variant="ghost"
          size="sm"
          :loading="refreshing"
          @click="refresh"
        >
          {{ refreshing ? '刷新中…' : '刷新' }}
        </Button>
      </template>
    </PageHeader>

    <section class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <StatCard label="论文总数" :value="stats?.total ?? '—'" hint="全库" to="/papers" />
      <StatCard label="本周新增" :value="stats?.new_this_week ?? '—'" hint="过去 7 天" />
      <StatCard label="已收藏" :value="stats?.core_count ?? '—'" hint="核心库" to="/papers" />
    </section>

    <section class="mt-10 mb-4 flex items-center gap-3">
      <span class="text-xs uppercase tracking-wide text-slate-500 font-medium">快速开始</span>
      <span class="flex-1 h-px bg-slate-200"></span>
    </section>

    <section class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <router-link to="/papers" class="action-card group">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <div class="action-title">上传论文</div>
        <div class="action-desc">PDF 自动提取元数据与引用</div>
      </router-link>
      <router-link to="/explore" class="action-card group">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
        </svg>
        <div class="action-title">去探索</div>
        <div class="action-desc">滑卡发现相关文献</div>
      </router-link>
      <router-link to="/review" class="action-card group">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <line x1="10" y1="9" x2="8" y2="9"/>
        </svg>
        <div class="action-title">生成综述</div>
        <div class="action-desc">AI 一键写文献综述</div>
      </router-link>
    </section>
  </section>
</template>

<style scoped>
.action-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 24px;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  text-decoration: none;
}
.action-card:hover {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.action-card svg {
  width: 28px;
  height: 28px;
  color: var(--color-accent);
  stroke-width: 1.5;
}
.action-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}
.action-desc {
  font-size: 13px;
  color: var(--color-text-muted);
  line-height: 1.5;
}
</style>
