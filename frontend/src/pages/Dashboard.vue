<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import StatCard from '@/components/StatCard.vue'
import { useTasksStore } from '@/stores/tasks'
import { usePapersStore } from '@/stores/papers'
import { useSubscriptionsStore } from '@/stores/subscriptions'
import { useProgressStore } from '@/stores/progress'
import { digestApi } from '@/api/endpoints'

const tasks = useTasksStore()
const papers = usePapersStore()
const subs = useSubscriptionsStore()
const progress = useProgressStore()
const refreshing = ref(false)
const watched = ref<Set<string>>(new Set())

async function refresh() {
  refreshing.value = true
  try {
    // Dashboard 仅展示计数，不再拉 papers 全表（C2/X2 审查）
    await Promise.all([tasks.fetch(), papers.fetchStats(), subs.fetchAll()])
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  progress.initOnce()
  refresh()
})

onBeforeUnmount(() => {
  // 切走 Dashboard 时清理订阅，避免长期泄漏（C1 审查）
  for (const tid of watched.value) progress.unsubscribe(tid)
  watched.value.clear()
})

function watchTask(taskId: number | string) {
  const tid = String(taskId)
  progress.subscribe(tid)
  watched.value.add(tid)
}

const digestSending = ref(false)
const digestMsg = ref('')

async function sendDigest() {
  digestSending.value = true
  digestMsg.value = ''
  try {
    const r = await digestApi.send()
    digestMsg.value = r.sent
      ? `已发送，共 ${r.paper_count} 篇`
      : `未发送：${r.reason ?? '无相关论文'}`
  } catch (e: unknown) {
    digestMsg.value = e instanceof Error ? e.message : '发送失败'
  } finally {
    digestSending.value = false
  }
}
</script>

<template>
  <section class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">概览</h1>
      <div class="flex items-center gap-2">
        <span v-if="digestMsg" class="text-xs text-slate-500">{{ digestMsg }}</span>
        <button
          class="rounded-md bg-blue-50 px-3 py-1 text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          :disabled="digestSending"
          @click="sendDigest"
        >
          {{ digestSending ? '发送中…' : '发送今日日报' }}
        </button>
        <button
          class="rounded-md bg-slate-100 px-3 py-1 text-sm hover:bg-slate-200 disabled:opacity-50"
          :disabled="refreshing"
          @click="refresh"
        >
          {{ refreshing ? '刷新中…' : '刷新' }}
        </button>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
      <StatCard
        label="论文总数"
        :value="papers.totalCount"
        :hint="`已分析 ${papers.analyzedCount}`"
      />
      <StatCard
        label="运行中任务"
        :value="tasks.counts.running ?? 0"
        :hint="`队列 ${tasks.counts.queued ?? 0} · 失败 ${tasks.counts.failed ?? 0}`"
        :tone="(tasks.counts.failed ?? 0) > 0 ? 'warn' : 'default'"
      />
      <StatCard
        label="活跃订阅"
        :value="subs.activeCount"
        :hint="`共 ${subs.items.length} 条`"
      />
      <StatCard
        label="未读 Inbox"
        :value="subs.unreadCount"
        :tone="subs.unreadCount > 0 ? 'good' : 'default'"
      />
    </div>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-semibold">最近任务</h2>
          <span class="text-xs text-slate-400">
            实时连接：{{ progress.connected ? '已连接' : '空闲' }}
          </span>
        </div>
        <p v-if="tasks.items.length === 0" class="text-sm text-slate-500">
          暂无任务。
        </p>
        <ul v-else class="divide-y divide-slate-100">
          <li
            v-for="t in tasks.recent"
            :key="t.id"
            class="flex items-center justify-between py-2 text-sm"
          >
            <div class="flex items-center gap-3">
              <span
                class="rounded px-1.5 py-0.5 text-xs font-medium"
                :class="{
                  'bg-amber-100 text-amber-700': t.status === 'queued',
                  'bg-blue-100 text-blue-700': t.status === 'running',
                  'bg-emerald-100 text-emerald-700': t.status === 'done',
                  'bg-rose-100 text-rose-700': t.status === 'failed',
                }"
              >
                {{ { queued: '排队中', running: '运行中', done: '完成', failed: '失败' }[t.status] ?? t.status }}
              </span>
              <span class="text-slate-600">#{{ t.id }} {{ t.type }}</span>
              <span v-if="t.paper_id" class="text-xs text-slate-400">
                论文 {{ t.paper_id }}
              </span>
            </div>
            <button
              v-if="t.status === 'running' || t.status === 'queued'"
              class="text-xs text-blue-600 hover:underline"
              @click="watchTask(t.id)"
            >
              订阅
            </button>
          </li>
        </ul>
      </div>

      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-semibold">订阅 Inbox</h2>
          <RouterLink
            to="/subscriptions"
            class="text-xs text-blue-600 hover:underline"
          >
            管理 →
          </RouterLink>
        </div>
        <p v-if="subs.inbox.length === 0" class="text-sm text-slate-500">
          暂无收件。
        </p>
        <ul v-else class="divide-y divide-slate-100">
          <li
            v-for="item in subs.inbox.slice(0, 8)"
            :key="item.id"
            class="flex items-center justify-between py-2 text-sm"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-slate-700">
                {{ (item.metadata?.title as string) || '(无标题)' }}
              </div>
              <div class="text-xs text-slate-400">
                sub #{{ item.subscription_id }}
              </div>
            </div>
            <button
              v-if="!item.notified"
              class="ml-2 text-xs text-blue-600 hover:underline"
              @click="subs.markRead(item.id)"
            >
              标记已读
            </button>
            <span v-else class="ml-2 text-xs text-slate-400">已读</span>
          </li>
        </ul>
      </div>
    </section>
  </section>
</template>
