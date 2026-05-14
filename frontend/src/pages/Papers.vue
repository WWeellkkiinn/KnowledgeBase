<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { papersApi } from '@/api/endpoints'
import type { Paper } from '@/types/api'

const route = useRoute()
const router = useRouter()

const items = ref<Paper[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const hasMore = ref(false)

const pageSize = 50
const routeTier = route.query.tier === 'stub' ? 'stub' : 'core'
const routePage = Number(route.query.page)
const tier = ref<'core' | 'stub'>(routeTier)
const offset = ref(routePage > 1 ? (routePage - 1) * pageSize : 0)
const selectedIds = ref<Set<number>>(new Set())
const batchLoading = ref(false)
const selectedCount = computed(() => selectedIds.value.size)
const pageIds = computed(() => items.value.map((p) => p.id))
const allPageSelected = computed(() => pageIds.value.length > 0 && pageIds.value.every((id) => selectedIds.value.has(id)))
const somePageSelected = computed(() => pageIds.value.some((id) => selectedIds.value.has(id)))
const headerCheckboxRef = ref<HTMLInputElement | null>(null)
const currentPage = computed(() => Math.floor(offset.value / pageSize) + 1)

async function fetchPage() {
  const requestedTier = tier.value
  const requestedOffset = offset.value
  loading.value = true
  error.value = null
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
    if (tier.value === requestedTier && offset.value === requestedOffset)
      error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (tier.value === requestedTier && offset.value === requestedOffset)
      loading.value = false
  }
}

onMounted(fetchPage)

watch(tier, () => {
  offset.value = 0
  clearSelection()
  fetchPage()
})

let _routeWatchReady = false
watch([tier, offset], () => {
  if (!_routeWatchReady) { _routeWatchReady = true; return }
  router.replace({ query: { tier: tier.value, page: currentPage.value } })
}, { flush: 'post' })

watch(items, () => {
  const pageSet = new Set(pageIds.value)
  selectedIds.value = new Set([...selectedIds.value].filter((id) => pageSet.has(id)))
})

watch([allPageSelected, somePageSelected], () => {
  if (headerCheckboxRef.value) {
    headerCheckboxRef.value.indeterminate = somePageSelected.value && !allPageSelected.value
  }
}, { immediate: true })

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

function toggleOne(id: number) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function togglePage() {
  selectedIds.value = allPageSelected.value ? new Set() : new Set(pageIds.value)
}

function clearSelection() {
  selectedIds.value = new Set()
}

async function moveSelected(isCore: boolean) {
  if (selectedIds.value.size === 0) return
  batchLoading.value = true
  error.value = null
  try {
    await papersApi.moveBatch(Array.from(selectedIds.value), isCore)
    clearSelection()
    await fetchPage()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    batchLoading.value = false
  }
}

async function deleteSelected() {
  if (selectedIds.value.size === 0) return
  if (!confirm(`确认删除选中的 ${selectedIds.value.size} 篇论文？此操作不可撤销，关联的引用记录也会一并删除。`)) return
  batchLoading.value = true
  error.value = null
  try {
    await papersApi.deleteBatch(Array.from(selectedIds.value))
    clearSelection()
    await fetchPage()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    batchLoading.value = false
  }
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

    <div class="flex h-10 items-center justify-between text-sm">
      <div class="flex items-center gap-2">
        <template v-if="selectedCount > 0">
          <span class="text-slate-600">已选 {{ selectedCount }} 篇</span>
          <button
            v-if="tier === 'stub'"
            class="rounded border border-slate-300 px-3 py-1 disabled:opacity-50"
            :disabled="batchLoading"
            @click="moveSelected(true)"
          >
            移至核心库
          </button>
          <button
            v-if="tier === 'core'"
            class="rounded border border-slate-300 px-3 py-1 disabled:opacity-50"
            :disabled="batchLoading"
            @click="moveSelected(false)"
          >
            移至探索库
          </button>
          <button
            class="rounded border border-rose-300 px-3 py-1 text-rose-600 disabled:opacity-50"
            :disabled="batchLoading"
            @click="deleteSelected"
          >
            删除
          </button>
        </template>
        <span v-else class="text-slate-500">第 {{ currentPage }} 页</span>
      </div>
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

    <div v-if="loading && items.length === 0" class="text-sm text-slate-500">加载中…</div>
    <p v-else-if="items.length === 0" class="text-sm text-slate-500">暂无论文。</p>

    <div v-else class="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-left text-xs uppercase text-slate-500">
          <tr>
            <th class="px-3 py-2 w-10">
              <input
                ref="headerCheckboxRef"
                type="checkbox"
                :checked="allPageSelected"
                @change="togglePage"
              />
            </th>
            <th class="px-3 py-2">标题</th>
            <th class="px-3 py-2 w-48">作者</th>
            <th class="px-3 py-2 w-16">年份</th>
            <th class="px-3 py-2 w-56">期刊</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="p in items" :key="p.id" class="hover:bg-slate-50">
            <td class="px-3 py-2">
              <input
                type="checkbox"
                :checked="selectedIds.has(p.id)"
                @change="toggleOne(p.id)"
              />
            </td>
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
  </section>
</template>
