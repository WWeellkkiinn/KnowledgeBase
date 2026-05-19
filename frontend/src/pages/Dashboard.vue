<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import StatCard from '@/components/StatCard.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import Button from '@/components/ui/Button.vue'
import { useTasksStore } from '@/stores/tasks'
import { usePapersStore } from '@/stores/papers'
import { digestApi, subscriptionsApi } from '@/api/endpoints'

const tasks = useTasksStore()
const papers = usePapersStore()
const refreshing = ref(false)
const activeTopicCount = ref(0)
const totalTopicCount = ref(0)

const todayLabel = computed(() => '今天 ' + new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }))

async function refresh() {
  refreshing.value = true
  try {
    const [, , allSubs] = await Promise.all([
      tasks.fetch(),
      papers.fetchStats(),
      subscriptionsApi.list(),
    ])
    activeTopicCount.value = allSubs.filter((s: { active: boolean }) => s.active).length
    totalTopicCount.value = allSubs.length
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  refresh()
})

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
    <PageHeader title="概览" :subtitle="todayLabel">
      <template #actions>
        <span v-if="digestMsg" class="text-xs text-slate-500">{{ digestMsg }}</span>
        <Button
          variant="secondary"
          size="sm"
          :loading="digestSending"
          @click="sendDigest"
        >
          {{ digestSending ? '发送中…' : '发送今日日报' }}
        </Button>
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

    <div class="grid grid-cols-2 gap-4 md:grid-cols-3">
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
        label="关注话题"
        :value="activeTopicCount"
        :hint="`共 ${totalTopicCount} 条`"
      />
    </div>
  </section>
</template>
