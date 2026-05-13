<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { papersApi } from '@/api/endpoints'
import type { Paper } from '@/types/api'

const items = ref<Paper[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const hasMore = ref(false)

const status = ref<string>('')
const source = ref<string>('')
const offset = ref(0)
const pageSize = 50

async function fetchPage() {
  loading.value = true
  error.value = null
  try {
    // 多请求 1 条用作探查："+1" 策略判断是否还有下一页，
    // 避免恰好满页时 canNext=true 但下一页空的 UX bug（C1+X2 审查）
    const resp = await papersApi.list({
      status: status.value || undefined,
      source: source.value || undefined,
      limit: pageSize + 1,
      offset: offset.value,
    })
    hasMore.value = resp.items.length > pageSize
    items.value = resp.items.slice(0, pageSize)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchPage)
watch([status, source], () => {
  offset.value = 0
  fetchPage()
})

const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => hasMore.value)

function nextPage() {
  offset.value += pageSize
  fetchPage()
}
function prevPage() {
  offset.value = Math.max(0, offset.value - pageSize)
  fetchPage()
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Papers</h1>
      <div class="flex gap-2 text-sm">
        <select v-model="status" class="rounded border border-slate-300 px-2 py-1">
          <option value="">所有状态</option>
          <option value="analyzed">已分析</option>
          <option value="downloaded">已下载</option>
          <option value="pending">待处理</option>
          <option value="failed">失败</option>
        </select>
        <select v-model="source" class="rounded border border-slate-300 px-2 py-1">
          <option value="">所有来源</option>
          <option value="root">root</option>
          <option value="ref">ref</option>
        </select>
      </div>
    </div>

    <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
      {{ error }}
    </p>

    <div v-if="loading" class="text-sm text-slate-500">加载中…</div>
    <p v-else-if="items.length === 0" class="text-sm text-slate-500">无匹配论文。</p>

    <div v-else class="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-left text-xs uppercase text-slate-500">
          <tr>
            <th class="px-3 py-2">#</th>
            <th class="px-3 py-2">标题</th>
            <th class="px-3 py-2">年份</th>
            <th class="px-3 py-2">来源</th>
            <th class="px-3 py-2">状态</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="p in items" :key="p.id" class="hover:bg-slate-50">
            <td class="px-3 py-2 text-slate-400">{{ p.id }}</td>
            <td class="px-3 py-2">
              <RouterLink
                :to="`/papers/${p.id}`"
                class="text-blue-600 hover:underline"
              >
                {{ p.title || p.stem }}
              </RouterLink>
              <div v-if="p.doi" class="text-xs text-slate-400">{{ p.doi }}</div>
            </td>
            <td class="px-3 py-2 text-slate-600">{{ p.year ?? '—' }}</td>
            <td class="px-3 py-2 text-slate-600">{{ p.source }}</td>
            <td class="px-3 py-2">
              <span
                class="rounded px-1.5 py-0.5 text-xs font-medium"
                :class="{
                  'bg-emerald-100 text-emerald-700': p.status === 'analyzed',
                  'bg-slate-100 text-slate-600': p.status !== 'analyzed',
                }"
              >
                {{ p.status }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex items-center justify-between text-sm">
      <span class="text-slate-500">偏移 {{ offset }} · 本页 {{ items.length }}</span>
      <div class="flex gap-2">
        <button
          class="rounded border border-slate-300 px-3 py-1 disabled:opacity-50"
          :disabled="!canPrev || loading"
          @click="prevPage"
        >
          上一页
        </button>
        <button
          class="rounded border border-slate-300 px-3 py-1 disabled:opacity-50"
          :disabled="!canNext || loading"
          @click="nextPage"
        >
          下一页
        </button>
      </div>
    </div>
  </section>
</template>
