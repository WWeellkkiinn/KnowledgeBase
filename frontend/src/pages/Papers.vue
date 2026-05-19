<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { papersApi } from '@/api/endpoints'
import { useProgressStore } from '@/stores/progress'
import type { Paper } from '@/types/api'
import PageHeader from '@/components/ui/PageHeader.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LoadingSkeleton from '@/components/ui/LoadingSkeleton.vue'
import ErrorState from '@/components/ui/ErrorState.vue'

const progress = useProgressStore()

const route = useRoute()
const router = useRouter()

const items = ref<Paper[]>([])
const loading = ref(true)
const showSkeleton = ref(false)
let skeletonTimer: ReturnType<typeof setTimeout> | null = null
const error = ref<string | null>(null)

function startLoading() {
  if (skeletonTimer) clearTimeout(skeletonTimer)
  skeletonTimer = setTimeout(() => {
    if (loading.value) showSkeleton.value = true
  }, 200)
}

function stopLoading() {
  if (skeletonTimer) { clearTimeout(skeletonTimer); skeletonTimer = null }
  showSkeleton.value = false
}
const hasMore = ref(false)
const total = ref(0)

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
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const jumpInput = ref('')

// 固定宽度页码条：永远 9 个槽位（不足时 total < 9 直接列全部），
// 翻页过程中条宽不变，避免点一次扩一次的视觉跳动。
// 布局：[首页] [省略号 or 邻页] [5 个中段] [省略号 or 邻页] [末页]
type PageItem = number | 'ellipsis-l' | 'ellipsis-r'
const SLOTS = 9
const pageItems = computed<PageItem[]>(() => {
  const total = totalPages.value
  const cur = currentPage.value
  if (total <= SLOTS) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  // EDGE_RUN = 7 个连续数字 + 末页（或首页）+ 省略号 = 9 槽
  const EDGE_RUN = SLOTS - 2  // 7
  // 靠近开头：1..7 + … + total
  if (cur <= 4) {
    const items: PageItem[] = []
    for (let i = 1; i <= EDGE_RUN; i++) items.push(i)
    items.push('ellipsis-r')
    items.push(total)
    return items
  }
  // 靠近结尾：1 + … + (total-6)..total
  if (cur >= total - 3) {
    const items: PageItem[] = [1, 'ellipsis-l']
    for (let i = total - EDGE_RUN + 1; i <= total; i++) items.push(i)
    return items
  }
  // 中间：1 + … + cur-2..cur+2 + … + total
  const items: PageItem[] = [1, 'ellipsis-l']
  for (let i = cur - 2; i <= cur + 2; i++) items.push(i)
  items.push('ellipsis-r')
  items.push(total)
  return items
})

function gotoPage(n: number) {
  const clamped = Math.min(totalPages.value, Math.max(1, Math.floor(n)))
  const newOffset = (clamped - 1) * pageSize
  if (newOffset === offset.value) return
  offset.value = newOffset
  clearSelection()
}

async function fetchPage() {
  const requestedTier = tier.value
  const requestedOffset = offset.value
  loading.value = true
  startLoading()
  error.value = null
  try {
    const resp = await papersApi.list({
      limit: pageSize,
      offset: requestedOffset,
      tier: requestedTier,
    })
    if (tier.value !== requestedTier || offset.value !== requestedOffset) return
    items.value = resp.items
    total.value = resp.total ?? 0
    hasMore.value = (requestedOffset + items.value.length) < total.value
  } catch (e: unknown) {
    if (tier.value === requestedTier && offset.value === requestedOffset)
      error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (tier.value === requestedTier && offset.value === requestedOffset) {
      loading.value = false
      stopLoading()
    }
  }
}

onMounted(fetchPage)
onBeforeUnmount(() => { if (skeletonTimer) clearTimeout(skeletonTimer) })

let _syncingFromRoute = false
watch(tier, () => {
  if (_syncingFromRoute) return  // 浏览器前进/后退时由 route.query watch 接管，不重置 offset
  offset.value = 0
  clearSelection()
})

// tier/offset 变化 → 同步到 URL + 拉取数据
// 注意：_syncingFromRoute 为 true 时跳过整段，由 route.query watch 自己负责 fetchPage，
// 避免 route.query → watch([tier,offset]) → router.replace → route.query watch 二次触发
watch([tier, offset], () => {
  if (_syncingFromRoute) return
  const desired = { tier: tier.value, page: String(currentPage.value) }
  const cur = route.query
  if (cur.tier !== desired.tier || String(cur.page ?? '') !== desired.page) {
    router.replace({ query: desired })
  }
  fetchPage()
}, { flush: 'post' })

// 浏览器前进/后退：route.query 变化时把 tier/offset 同步回 ref，并自己 fetchPage
watch(() => route.query, (q) => {
  const newTier = q.tier === 'stub' ? 'stub' : 'core'
  const newPage = Number(q.page) || 1
  const newOffset = newPage > 1 ? (newPage - 1) * pageSize : 0
  if (newTier === tier.value && newOffset === offset.value) return
  _syncingFromRoute = true
  try {
    tier.value = newTier
    offset.value = newOffset
    clearSelection()
  } finally {
    _syncingFromRoute = false
  }
  fetchPage()
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
  clearSelection()
  // fetchPage 由 route.query watch 统一负责（offset 变 → watch([tier, offset]) → router.replace → route.query watch → fetchPage）
}
function prevPage() {
  offset.value = Math.max(0, offset.value - pageSize)
  clearSelection()
}
const uploadInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadMsg = ref<string | null>(null)

function pickUpload() {
  uploadInput.value?.click()
}

async function onUploadChange(ev: Event) {
  const inputEl = ev.target as HTMLInputElement
  const f = inputEl.files?.[0]
  inputEl.value = ''  // 清空，允许重复选同一文件
  if (!f) return
  if (!f.name.toLowerCase().endsWith('.pdf')) {
    uploadMsg.value = '仅支持 PDF'
    return
  }
  if (f.size > 50 * 1024 * 1024) {
    uploadMsg.value = '文件超过 50MB'
    return
  }
  uploading.value = true
  uploadMsg.value = `正在上传 ${f.name}…`
  error.value = null
  try {
    const resp = await papersApi.upload(f)
    if (resp.deduped) {
      uploadMsg.value = `文件已存在（paper #${resp.paper_id}），未重复处理`
    } else {
      uploadMsg.value = `已入队（paper #${resp.paper_id}, task #${resp.task_id}），后台处理中…`
      if (resp.task_id != null) {
        // store 级订阅：用户上传后切到其它页仍需接收进度，故组件卸载时不退订
        progress.subscribe(String(resp.task_id))
      }
    }
    await fetchPage()
  } catch (e: unknown) {
    uploadMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    uploading.value = false
  }
}

function jumpToPage() {
  // 空字符串 Number('') === 0 且 isFinite(0)，会误跳第 1 页；这里显式拦截
  if (jumpInput.value === '' || jumpInput.value == null) return
  const n = Number(jumpInput.value)
  if (!Number.isFinite(n)) {
    jumpInput.value = ''
    return
  }
  const clamped = Math.min(totalPages.value, Math.max(1, Math.floor(n)))
  const newOffset = (clamped - 1) * pageSize
  jumpInput.value = ''
  if (newOffset === offset.value) return
  clearSelection()
  offset.value = newOffset
  // fetchPage 由 watch([tier, offset]) 触发
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

const TIER_COLOR: Record<number, string> = {
  1: 'bg-amber-100 text-amber-700',
  2: 'bg-slate-100 text-slate-600',
  3: 'bg-orange-100 text-orange-700',
}
function tierClass(tier: number | null | undefined) {
  if (tier == null) return 'bg-slate-100 text-slate-400'
  return TIER_COLOR[tier] ?? 'bg-slate-100 text-slate-500'
}
</script>

<template>
  <section class="space-y-4">
    <PageHeader title="论文库" :subtitle="`共 ${total} 篇论文`">
      <template #actions>
        <input
          ref="uploadInput"
          type="file"
          accept="application/pdf,.pdf"
          class="hidden"
          @change="onUploadChange"
        />
        <Button
          variant="primary"
          size="sm"
          :loading="uploading"
          @click="pickUpload"
        >
          {{ uploading ? '上传中…' : '上传 PDF' }}
        </Button>
      </template>
    </PageHeader>

    <p
      v-if="uploadMsg"
      class="rounded bg-blue-50 px-3 py-2 text-xs text-blue-700 flex items-center justify-between"
    >
      <span>{{ uploadMsg }}</span>
      <button class="text-blue-500 hover:text-blue-700" @click="uploadMsg = null">×</button>
    </p>

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

    <div class="flex h-10 items-center justify-between text-sm">
      <div class="flex items-center gap-2">
        <template v-if="selectedCount > 0">
          <span class="text-slate-600">已选 {{ selectedCount }} 篇</span>
          <Button
            v-if="tier === 'stub'"
            variant="secondary"
            size="sm"
            :disabled="batchLoading"
            @click="moveSelected(true)"
          >
            移至核心库
          </Button>
          <Button
            v-if="tier === 'core'"
            variant="secondary"
            size="sm"
            :disabled="batchLoading"
            @click="moveSelected(false)"
          >
            移至探索库
          </Button>
          <Button
            variant="danger"
            size="sm"
            :disabled="batchLoading"
            @click="deleteSelected"
          >
            删除
          </Button>
        </template>
        <span v-else class="text-slate-500">第 {{ currentPage }} / {{ totalPages }} 页（共 {{ total }} 条）</span>
      </div>
      <div class="flex items-center gap-1">
        <Button
          variant="secondary"
          size="sm"
          :disabled="!canPrev || loading"
          @click="prevPage"
        >上一页</Button>

        <template v-for="(p, i) in pageItems" :key="typeof p === 'number' ? `p${p}` : p">
          <span
            v-if="p === 'ellipsis-l' || p === 'ellipsis-r'"
            class="px-1 text-slate-400 select-none"
          >…</span>
          <button
            v-else
            class="min-w-9 rounded border px-2.5 py-1 text-sm"
            :class="p === currentPage
              ? 'border-blue-600 bg-blue-600 text-white font-semibold'
              : 'border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40'"
            :disabled="loading || p === currentPage"
            @click="gotoPage(p)"
          >{{ p }}</button>
        </template>

        <Button
          variant="secondary"
          size="sm"
          :disabled="!canNext || loading"
          @click="nextPage"
        >下一页</Button>

        <span class="ml-3 text-slate-400">跳至</span>
        <input
          v-model="jumpInput"
          type="number"
          min="1"
          :max="totalPages"
          :placeholder="String(currentPage)"
          class="w-16 rounded border border-slate-300 px-2 py-1 text-center text-sm"
          @keyup.enter="jumpToPage"
        />
        <Button
          variant="secondary"
          size="sm"
          :disabled="loading || !jumpInput"
          @click="jumpToPage"
        >GO</Button>
      </div>
    </div>

    <LoadingSkeleton v-if="showSkeleton" variant="row" :count="8" />
    <ErrorState v-else-if="error" :message="error" @retry="fetchPage" />
    <EmptyState
      v-else-if="!loading && items.length === 0"
      title="还没有论文"
      description="点击上方上传按钮添加你的第一篇 PDF"
    />
    <div v-else class="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table class="w-full text-sm">
        <thead class="sticky top-0 bg-white/95 backdrop-blur z-10 text-left text-xs uppercase text-slate-500">
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
            <th class="px-3 py-2 w-48">标签</th>
            <th class="px-3 py-2 w-48">作者</th>
            <th class="px-3 py-2 w-16">年份</th>
            <th class="px-3 py-2 w-56">期刊</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr
            v-for="p in items"
            :key="p.id"
            class="hover:bg-slate-50 transition-colors"
            :class="{ 'bg-blue-50': selectedIds.has(p.id) }"
          >
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
            <td class="px-3 py-2">
              <div v-if="p.tags?.length" class="flex flex-wrap gap-1">
                <span
                  v-for="tag in p.tags.slice(0, 3)"
                  :key="tag"
                  class="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-600"
                >{{ tag }}</span>
                <span v-if="p.tags.length > 3" class="text-xs text-slate-400">+{{ p.tags.length - 3 }}</span>
              </div>
              <span v-else class="text-slate-300">—</span>
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
