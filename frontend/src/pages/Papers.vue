<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { papersApi } from '@/api/endpoints'
import type { Paper } from '@/types/api'

const items = ref<Paper[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const hasMore = ref(false)

const tier = ref<'core' | 'stub'>('core')
const offset = ref(0)
const pageSize = 50

async function fetchPage() {
  const requestedTier = tier.value
  const requestedOffset = offset.value
  loading.value = true
  error.value = null
  items.value = []
  try {
    const resp = await papersApi.list({
      limit: pageSize + 1,
      offset: requestedOffset,
      tier: requestedTier,
    })
    if (tier.value !== requestedTier || offset.value !== requestedOffset) return
    hasMore.value = resp.items.length > pageSize
    items.value = resp.items.slice(0, pageSize)
  } catch (e: unknown) {
    if (tier.value === requestedTier) error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (tier.value === requestedTier) loading.value = false
  }
}

onMounted(fetchPage)

watch(tier, () => {
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

const TIER_COLOR: Record<string, string> = {
  '1': 'bg-amber-100 text-amber-700',
  '2': 'bg-slate-100 text-slate-600',
  '3': 'bg-orange-100 text-orange-700',
}
function tierClass(tier: number | null | undefined) {
  return tier ? (TIER_COLOR[String(tier)] ?? 'bg-slate-100 text-slate-500') : 'bg-slate-100 text-slate-400'
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">论文库</h1>
    </div>

    <nav class="border-b border-slate-200">
      <ul class="flex gap-4 text-sm">
        <li>
          <button
            class="border-b-2 px-1 pb-2"
            :class="tier === 'core' ? 'border-blue-600 text-blue-600 font-semibold' : 'border-transparent text-slate-600 hover:text-slate-900'"
            @click="tier = 'core'"
          >核心库</button>
        </li>
        <li>
          <button
            class="border-b-2 px-1 pb-2"
            :class="tier === 'stub' ? 'border-blue-600 text-blue-600 font-semibold' : 'border-transparent text-slate-600 hover:text-slate-900'"
            @click="tier = 'stub'"
          >探索库</button>
        </li>
      </ul>
    </nav>

    <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
      {{ error }}
    </p>

    <div v-if="loading" class="text-sm text-slate-500">加载中…</div>
    <p v-else-if="items.length === 0" class="text-sm text-slate-500">暂无论文。</p>

    <div v-else class="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-left text-xs uppercase text-slate-500">
          <tr>
            <th class="px-3 py-2">标题</th>
            <th class="px-3 py-2 w-48">作者</th>
            <th class="px-3 py-2 w-16">年份</th>
            <th class="px-3 py-2 w-56">期刊</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="p in items" :key="p.id" class="hover:bg-slate-50">
            <td class="px-3 py-2 max-w-xs">
              <RouterLink
                :to="`/papers/${p.id}`"
                class="text-blue-600 hover:underline line-clamp-2"
              >
                {{ p.title || p.stem }}
              </RouterLink>
            </td>
            <td class="px-3 py-2 text-xs text-slate-500">
              <span v-if="Array.isArray(p.authors_json) && p.authors_json.length">
                {{ (p.authors_json as string[]).slice(0, 3).join(', ') }}{{ p.authors_json.length > 3 ? ' 等' : '' }}
              </span>
              <span v-else class="text-slate-300">—</span>
            </td>
            <td class="px-3 py-2 text-slate-600">{{ p.year ?? '—' }}</td>
            <td class="px-3 py-2">
              <template v-if="p.journal">
                <span class="text-slate-700 text-xs">{{ p.journal.name }}</span>
                <span
                  v-if="p.journal.quality_tier != null"
                  class="ml-1.5 rounded px-1 py-0.5 text-xs font-medium"
                  :class="tierClass(p.journal.quality_tier)"
                >
                  T{{ p.journal.quality_tier }}
                </span>
              </template>
              <span v-else class="text-slate-400">—</span>
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
