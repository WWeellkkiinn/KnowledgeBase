<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { failuresApi } from '@/api/endpoints'
import type { FailureItem, FailuresResponse } from '@/types/api'

const data = ref<FailuresResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const filterCategory = ref('')
const filterStem = ref('')

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    data.value = await failuresApi.list()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})

const CATEGORY_LABEL: Record<string, string> = {
  paywalled: '付费墙 (403/401)',
  http_error: 'HTTP 错误',
  not_a_pdf: '非 PDF',
  browser_timeout: '浏览器超时',
  no_pdf_found: '未找到 PDF',
  other: '其他',
}

const CATEGORY_CLASS: Record<string, string> = {
  paywalled: 'bg-rose-100 text-rose-700',
  http_error: 'bg-orange-100 text-orange-700',
  not_a_pdf: 'bg-amber-100 text-amber-700',
  browser_timeout: 'bg-purple-100 text-purple-700',
  no_pdf_found: 'bg-slate-100 text-slate-600',
  other: 'bg-gray-100 text-gray-600',
}

const stems = computed<string[]>(() => {
  if (!data.value) return []
  return [...new Set(data.value.items.map((i) => i.stem))].sort()
})

const filtered = computed<FailureItem[]>(() => {
  if (!data.value) return []
  return data.value.items.filter((it) => {
    if (filterCategory.value && it.category !== filterCategory.value) return false
    if (filterStem.value && it.stem !== filterStem.value) return false
    return true
  })
})
</script>

<template>
  <section class="space-y-5">
    <h1 class="text-2xl font-bold">Failure Diagnostics</h1>

    <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">{{ error }}</p>
    <p v-if="loading" class="text-sm text-slate-500">加载中…</p>

    <template v-if="data">
      <!-- Stats cards -->
      <div class="flex flex-wrap gap-3">
        <div class="rounded-lg border border-slate-200 bg-white px-4 py-3 text-center min-w-[110px]">
          <div class="text-2xl font-bold text-slate-800">{{ data.total }}</div>
          <div class="text-xs text-slate-500 mt-1">总失败条目</div>
        </div>
        <div
          v-for="(count, cat) in data.by_category"
          :key="cat"
          class="rounded-lg border border-slate-200 bg-white px-4 py-3 text-center min-w-[110px]"
        >
          <div class="text-2xl font-bold text-slate-800">{{ count }}</div>
          <div class="mt-1">
            <span
              class="rounded px-1.5 py-0.5 text-xs font-medium"
              :class="CATEGORY_CLASS[cat] ?? 'bg-slate-100 text-slate-600'"
            >
              {{ CATEGORY_LABEL[cat] ?? cat }}
            </span>
          </div>
        </div>
      </div>

      <!-- Filters -->
      <div class="flex gap-3 text-sm">
        <select
          v-model="filterCategory"
          class="rounded border border-slate-300 px-2 py-1"
        >
          <option value="">所有类别</option>
          <option v-for="cat in Object.keys(data.by_category)" :key="cat" :value="cat">
            {{ CATEGORY_LABEL[cat] ?? cat }}
          </option>
        </select>
        <select
          v-model="filterStem"
          class="rounded border border-slate-300 px-2 py-1 max-w-[240px]"
        >
          <option value="">所有论文</option>
          <option v-for="s in stems" :key="s" :value="s">{{ s }}</option>
        </select>
        <span class="text-slate-400 self-center">{{ filtered.length }} 条</span>
      </div>

      <!-- Table -->
      <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th class="px-3 py-2">论文</th>
              <th class="px-3 py-2">#</th>
              <th class="px-3 py-2">引文</th>
              <th class="px-3 py-2">失败原因</th>
              <th class="px-3 py-2">类别</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-if="filtered.length === 0">
              <td colspan="5" class="px-3 py-6 text-center text-slate-400">无失败记录。</td>
            </tr>
            <tr v-for="(it, idx) in filtered" :key="idx" class="hover:bg-slate-50">
              <td class="px-3 py-2 text-xs text-slate-500 whitespace-nowrap">
                <RouterLink
                  v-if="it.paper_id"
                  :to="`/papers/${it.paper_id}`"
                  class="text-blue-600 hover:underline"
                >
                  {{ it.stem }}
                </RouterLink>
                <span v-else>{{ it.stem }}</span>
              </td>
              <td class="px-3 py-2 text-slate-400">{{ it.ref_index }}</td>
              <td class="px-3 py-2 max-w-xs">
                <div class="truncate text-slate-700" :title="it.header">{{ it.header }}</div>
                <div v-if="it.doi" class="text-xs text-slate-400">{{ it.doi }}</div>
              </td>
              <td class="px-3 py-2 text-xs text-slate-500 max-w-xs">
                <span class="break-all">{{ it.reason }}</span>
              </td>
              <td class="px-3 py-2">
                <span
                  class="rounded px-1.5 py-0.5 text-xs font-medium"
                  :class="CATEGORY_CLASS[it.category] ?? 'bg-slate-100 text-slate-600'"
                >
                  {{ CATEGORY_LABEL[it.category] ?? it.category }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
