<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { papersApi } from '@/api/endpoints'
import { useProgressStore } from '@/stores/progress'
import type {
  BackwardTrackResult,
  ForwardTrackResult,
  PaperDetail,
  ProgressEvent,
} from '@/types/api'
import { isTrackAccepted } from '@/types/api'
import Button from '@/components/ui/Button.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LoadingSkeleton from '@/components/ui/LoadingSkeleton.vue'
import ErrorState from '@/components/ui/ErrorState.vue'

const progress = useProgressStore()
const PAGE_LIMIT = 100

const route = useRoute()
const router = useRouter()
defineProps<{ id: string }>()
const paperId = computed(() => Number(route.params.id))

// 上一页 URL：每次路由变化时刷新（含 RouterLink 进入新论文详情时）
const backHref = ref<string | null>(
  typeof window !== 'undefined' ? (window.history.state?.back ?? null) : null
)

function refreshBackHref() {
  if (typeof window !== 'undefined') {
    backHref.value = window.history.state?.back ?? null
  }
}

const backLabel = computed(() => {
  const b = backHref.value
  if (!b) return '← 返回论文库'
  if (b.startsWith('/papers/')) return '← 返回上一篇'
  if (b.startsWith('/papers')) return '← 返回论文库'
  if (b.startsWith('/network')) return '← 返回图谱'
  if (b === '/' || b.startsWith('/?')) return '← 返回主页'
  if (b.startsWith('/review')) return '← 返回审阅'
  if (b.startsWith('/subscriptions')) return '← 返回订阅'
  return '← 返回上一页'
})

function goBack() {
  if (backHref.value) router.back()
  else router.push('/papers')
}

const detail = ref<PaperDetail | null>(null)
const loading = ref(false)
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

const tab = ref<'refs' | 'cited'>('refs')

// ─ Cited by (forward-track) ─
const ftResult = ref<ForwardTrackResult | null>(null)
const ftLoading = ref(false)
const ftError = ref<string | null>(null)
const ftTaskId = ref<number | null>(null)     // 异步任务 ID（cache miss 时由 202 响应给出）
const ftLoadMoreLoading = ref(false)

// ─ References (backward-track) ─
const btResult = ref<BackwardTrackResult | null>(null)
const btLoading = ref(false)
const btError = ref<string | null>(null)
const btTaskId = ref<number | null>(null)
const btLoadMoreLoading = ref(false)

async function load() {
  const requestedId = paperId.value  // 捕获当前 id，防止主请求竞态
  loading.value = true
  startLoading()
  error.value = null
  detail.value = null
  btResult.value = null
  btError.value = null
  btLoading.value = false
  btTaskId.value = null
  btLoadMoreLoading.value = false
  ftResult.value = null
  ftError.value = null
  ftLoading.value = false
  ftTaskId.value = null
  ftLoadMoreLoading.value = false
  // 切换论文时把上一个论文的 pending track 订阅清掉
  for (const tid of _pendingHandlers.keys()) progress.unsubscribe(String(tid))
  _pendingHandlers.clear()
  // 重置事件游标到当前末尾：旧论文残留事件不再触发本论文 handler
  _lastProcessedEventIndex = progress.events.length
  try {
    const result = await papersApi.get(requestedId)
    if (paperId.value !== requestedId) return  // 已切换到其他论文，丢弃响应
    detail.value = result
    // 核心论文进入详情页即预取引用/被引用，让两个 tab 一打开就是富格式；
    // 否则不预取的论文会回退到 edges_in/out 的简版 #? 列表，与已加载论文形成"两种展示"的视觉不一致。
    // 注意：watch(tab,...) 仍保留惰性兜底，应对预取失败后用户点 tab 触发的重试。
    if (detail.value.paper.is_core && detail.value.paper.doi) {
      if (!btResult.value && !btLoading.value) runBackwardTrack(false)
      if (!ftResult.value && !ftLoading.value) runForwardTrack(false)
    }
  } catch (e: unknown) {
    if (paperId.value === requestedId)
      error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (paperId.value === requestedId) {
      loading.value = false
      stopLoading()
    }
  }
}

onMounted(() => {
  refreshBackHref()
  load()
})
onBeforeUnmount(() => { if (skeletonTimer) clearTimeout(skeletonTimer) })
watch(() => route.params.id, () => {
  refreshBackHref()
  load()
})

watch(tab, (newTab) => {
  if (!detail.value?.paper.is_core || !detail.value?.paper.doi) return
  // 短路 ftTaskId/btTaskId：任务已在队列里时不要重复发请求
  if (newTab === 'refs' && !btResult.value && !btLoading.value && !btTaskId.value) {
    runBackwardTrack(false)
  }
  if (newTab === 'cited' && !ftResult.value && !ftLoading.value && !ftTaskId.value) {
    runForwardTrack(false)
  }
})

// Track 端点现在返回 200(cache 命中) 或 202(已入队后台 worker)。
// 收到 202 后订阅 task_id，worker 完成时 emit done → 自动重发请求拿 cache。
//
// 之前的实现 watch(progress.events.length) 只取最新一条事件，同一 tick 内多个
// done/failed 事件会被丢（Vue watch flush 合并）→ 对应 task 永远 loading。
// 改为 watch 整个 events 数组，记录上次处理过的位置，遍历新增部分。

const _pendingHandlers = new Map<number, (ev: ProgressEvent) => void>()
let _lastProcessedEventIndex = 0  // 仅看 events 数组中 index >= 此值的新事件

function _onTrackDone(taskId: number, requestedId: number, direction: 'forward' | 'backward') {
  const handler = (ev: ProgressEvent) => {
    if (ev.type !== 'progress') return
    const step = (ev.payload?.step as string) || ''
    if (step !== 'done' && step !== 'failed') return
    progress.unsubscribe(String(taskId))
    _pendingHandlers.delete(taskId)
    if (paperId.value !== requestedId) return
    if (direction === 'forward') {
      ftTaskId.value = null
      if (step === 'failed') {
        ftError.value = (ev.payload?.message as string) || '后台查询失败'
        ftLoading.value = false
        return
      }
      runForwardTrack(false)
    } else {
      btTaskId.value = null
      if (step === 'failed') {
        btError.value = (ev.payload?.message as string) || '后台查询失败'
        btLoading.value = false
        return
      }
      runBackwardTrack(false)
    }
  }
  _pendingHandlers.set(taskId, handler)
  progress.subscribe(String(taskId))
}

// 路由 progress store 的所有新增事件 → 对应 handler；不再用 length 单点 watch。
// 注意：progress store 的 events 数组上限 200，超过后头部裁切，索引会"漂移"。
// 因此每次取 lastProcessedIndex 与当前 length 的 min，确保索引不越界。
watch(
  () => progress.events.length,
  (newLen) => {
    if (_pendingHandlers.size === 0) {
      _lastProcessedEventIndex = newLen
      return
    }
    // store 内部可能 slice 裁切（MAX_EVENTS=200），保守起见从 max(0, lastIdx) 开始
    const start = Math.max(0, Math.min(_lastProcessedEventIndex, newLen))
    for (let i = start; i < newLen; i++) {
      const ev = progress.events[i]
      if (!ev) continue
      const tid = Number(ev.task_id)
      const h = _pendingHandlers.get(tid)
      if (h) h(ev)
    }
    _lastProcessedEventIndex = newLen
  },
)

async function runForwardTrack(refresh = false) {
  const requestedId = paperId.value
  ftLoading.value = true
  ftError.value = null
  try {
    const resp = await papersApi.forwardTrack(requestedId, {
      refresh, page_limit: PAGE_LIMIT, offset: 0,
    })
    if (paperId.value !== requestedId) return
    if (isTrackAccepted(resp)) {
      // 202：任务已入队，订阅 done 事件后自动重发
      ftTaskId.value = resp.task_id
      _onTrackDone(resp.task_id, requestedId, 'forward')
      // 保持 ftLoading=true（"查询中…"）直到 worker 完成
      return
    }
    ftResult.value = resp
    ftTaskId.value = null
    ftLoading.value = false
  } catch (e: unknown) {
    if (paperId.value === requestedId) {
      ftError.value = e instanceof Error ? e.message : String(e)
      ftLoading.value = false
    }
  }
}

async function runBackwardTrack(refresh = false) {
  const requestedId = paperId.value
  btLoading.value = true
  btError.value = null
  try {
    const resp = await papersApi.backwardTrack(requestedId, {
      refresh, page_limit: PAGE_LIMIT, offset: 0,
    })
    if (paperId.value !== requestedId) return
    if (isTrackAccepted(resp)) {
      btTaskId.value = resp.task_id
      _onTrackDone(resp.task_id, requestedId, 'backward')
      return
    }
    btResult.value = resp
    btTaskId.value = null
    btLoading.value = false
  } catch (e: unknown) {
    if (paperId.value === requestedId) {
      btError.value = e instanceof Error ? e.message : String(e)
      btLoading.value = false
    }
  }
}

async function loadMoreBackward() {
  if (!btResult.value || btLoadMoreLoading.value) return
  const requestedId = paperId.value
  const nextOffset = (btResult.value.referenced_papers?.length || 0)
  btLoadMoreLoading.value = true
  try {
    const resp = await papersApi.backwardTrack(requestedId, {
      page_limit: PAGE_LIMIT, offset: nextOffset,
    })
    if (paperId.value !== requestedId) return
    if (isTrackAccepted(resp)) {
      // 不应发生：cache 已写入才会有 has_more=true；如真触发，明确提示而非静默
      btError.value = 'cache 已失效，正在后台重新查询，请稍候再试'
      return
    }
    // push 原地 append，避免 spread 重建 O(n) 数组
    if (btResult.value) {
      btResult.value.referenced_papers.push(...resp.referenced_papers)
      btResult.value.has_more = resp.has_more
      btResult.value.offset = resp.offset
      btResult.value.limit = resp.limit
    }
  } finally {
    btLoadMoreLoading.value = false
  }
}

async function loadMoreForward() {
  if (!ftResult.value || ftLoadMoreLoading.value) return
  const requestedId = paperId.value
  const nextOffset = (ftResult.value.citing_papers?.length || 0)
  ftLoadMoreLoading.value = true
  try {
    const resp = await papersApi.forwardTrack(requestedId, {
      page_limit: PAGE_LIMIT, offset: nextOffset,
    })
    if (paperId.value !== requestedId) return
    if (isTrackAccepted(resp)) {
      ftError.value = 'cache 已失效，正在后台重新查询，请稍候再试'
      return
    }
    if (ftResult.value) {
      ftResult.value.citing_papers.push(...resp.citing_papers)
      ftResult.value.has_more = resp.has_more
      ftResult.value.offset = resp.offset
      ftResult.value.limit = resp.limit
    }
  } finally {
    ftLoadMoreLoading.value = false
  }
}


const tierLabel = computed(() => {
  const t = detail.value?.paper.journal?.quality_tier
  return t ? `Tier ${t}` : null
})

const authorList = computed(() => {
  const raw = detail.value?.paper.authors_json
  if (!Array.isArray(raw) || raw.length === 0) return null
  const names = (raw as string[]).slice(0, 5)
  return raw.length > 5 ? names.join(', ') + ' 等' : names.join(', ')
})

// 数字徽章：API 加载完才显示真实数；否则为 null → 模板渲染成 '…'
// 注意：edges_in/edges_out（DB 里的子集）和 references_count/citing_count（API 全量）
// 是不同量级的两个量，不能拼成 ?? 兜底链，否则会出现"90→30"跳变错觉。
const refCount = computed<number | null>(() =>
  btResult.value?.references_count ?? null
)
const citedCount = computed<number | null>(() =>
  ftResult.value?.citing_count ?? null
)

const aiSectionOpen = ref(true)
const aiAnalyzing = ref(false)
const aiAnalyzeError = ref<string | null>(null)

async function runAiAnalyze() {
  if (!detail.value) return
  const requestedId = detail.value.paper.id
  aiAnalyzing.value = true
  aiAnalyzeError.value = null
  try {
    const updated = await papersApi.aiAnalyze(requestedId)
    // 用户已切到其他论文 → 丢弃结果，避免污染新 detail
    if (!detail.value || detail.value.paper.id !== requestedId) return
    detail.value.paper.tags = updated.tags
    detail.value.paper.ai_summary = updated.ai_summary
    detail.value.paper.ai_analyzed_at = updated.ai_analyzed_at
    aiSectionOpen.value = true
  } catch (e: unknown) {
    if (detail.value && detail.value.paper.id === requestedId) {
      aiAnalyzeError.value = e instanceof Error ? e.message : String(e)
    }
  } finally {
    if (detail.value && detail.value.paper.id === requestedId) {
      aiAnalyzing.value = false
    }
  }
}
</script>

<template>
  <section class="space-y-5">
    <PageHeader :title="detail?.paper.title || detail?.paper.stem || '论文详情'" subtitle="">
      <template #actions>
        <Button variant="ghost" size="sm" @click="goBack">{{ backLabel }}</Button>
      </template>
    </PageHeader>

    <ErrorState v-if="error" :message="error" />
    <LoadingSkeleton v-if="showSkeleton" variant="text" :count="6" />

    <article v-if="detail" class="space-y-6">
      <!-- ── 头部：结构化元数据 ── -->
      <header class="space-y-4">
        <h1 class="text-2xl font-bold leading-snug">
          {{ detail.paper.title || detail.paper.stem }}
        </h1>

        <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <template v-if="authorList">
            <dt class="text-slate-400 self-start">作者</dt>
            <dd class="text-slate-700">{{ authorList }}</dd>
          </template>
          <dt class="text-slate-400 self-center">年份</dt>
          <dd class="text-slate-700">{{ detail.paper.year ?? '—' }}</dd>
          <dt class="text-slate-400 self-center">DOI</dt>
          <dd class="text-slate-700 text-sm flex min-w-0 items-center gap-2">
            <span class="font-mono truncate">{{ detail.paper.doi || '—' }}</span>
            <a
              v-if="detail.paper.doi"
              :href="papersApi.citationBibUrl(detail.paper.id)"
              class="shrink-0 rounded border border-slate-300 px-2 py-0.5 hover:bg-slate-50"
            >
              下载 BibTeX
            </a>
          </dd>
          <dt class="text-slate-400 self-center">期刊</dt>
          <dd class="text-slate-700 flex min-w-0 items-center gap-2">
            <span class="truncate">{{ detail.paper.journal?.name || '—' }}</span>
            <span
              v-if="tierLabel"
              class="rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700"
            >
              {{ tierLabel }}
            </span>
            <span
              v-if="detail.paper.journal?.is_predatory"
              class="rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-700"
            >
              掠夺性期刊
            </span>
          </dd>
        </dl>

        <!-- 摘要 -->
        <div v-if="detail.paper.abstract" class="space-y-1">
          <p class="text-xs font-medium uppercase tracking-wide text-slate-400">摘要</p>
          <p class="text-sm text-slate-600 leading-relaxed">{{ detail.paper.abstract }}</p>
        </div>

        <!-- Tags（header 区快速预览） -->
        <div v-if="detail.paper.tags?.length" class="flex flex-wrap gap-1.5">
          <span
            v-for="tag in detail.paper.tags"
            :key="tag"
            class="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs text-blue-700"
          >{{ tag }}</span>
        </div>

      </header>

      <!-- ── 内容精炼（原 AI 精炼） ── -->
      <div class="rounded-lg border border-slate-200 bg-slate-50">
        <div class="border-b border-slate-200 px-4 py-2 flex items-center justify-between">
          <button
            class="flex items-center gap-1 text-sm font-semibold text-slate-700"
            @click="aiSectionOpen = !aiSectionOpen"
          >
            内容精炼
            <span class="text-xs font-normal text-slate-400">{{ aiSectionOpen ? '▲' : '▼' }}</span>
          </button>
          <Button
            v-if="detail.paper.abstract && !detail.paper.ai_analyzed_at"
            variant="secondary" size="sm"
            :loading="aiAnalyzing"
            :disabled="aiAnalyzing"
            @click="runAiAnalyze"
          >立即分析</Button>
          <Button
            v-else-if="detail.paper.abstract && detail.paper.ai_analyzed_at"
            variant="secondary" size="sm"
            :loading="aiAnalyzing"
            :disabled="aiAnalyzing"
            @click="runAiAnalyze"
          >重新分析</Button>
        </div>
        <div v-if="aiSectionOpen" class="px-4 py-3 space-y-3 text-sm">
          <p v-if="aiAnalyzeError" class="text-xs text-rose-500">{{ aiAnalyzeError }}</p>
          <template v-if="detail.paper.ai_summary || detail.paper.tags?.length">
            <!-- Tags -->
            <div v-if="detail.paper.tags?.length" class="flex flex-wrap gap-1.5">
              <span
                v-for="tag in detail.paper.tags"
                :key="tag"
                class="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs text-blue-700"
              >{{ tag }}</span>
            </div>
            <template v-if="detail.paper.ai_summary">
              <div v-if="detail.paper.ai_summary.research_question" class="space-y-1">
                <p class="text-sm font-semibold text-slate-900">研究问题</p>
                <p class="text-slate-700 leading-relaxed">{{ detail.paper.ai_summary.research_question }}</p>
              </div>
              <div v-if="detail.paper.ai_summary.methodology" class="space-y-1">
                <p class="text-sm font-semibold text-slate-900">方法</p>
                <p class="text-slate-700 leading-relaxed">{{ detail.paper.ai_summary.methodology }}</p>
              </div>
              <div v-if="detail.paper.ai_summary.key_findings?.length" class="space-y-1">
                <p class="text-sm font-semibold text-slate-900">关键发现</p>
                <ul class="list-disc list-inside text-slate-700 leading-relaxed space-y-0.5">
                  <li v-for="(f, i) in detail.paper.ai_summary.key_findings" :key="i">{{ f }}</li>
                </ul>
              </div>
            </template>
          </template>
          <p v-else class="text-xs text-slate-400">
            {{ detail.paper.abstract ? '点击"立即分析"生成 AI 精炼摘要。' : '无摘要，无法进行 AI 分析。' }}
          </p>
        </div>
      </div>

      <!-- ── Tab 导航 ── -->
      <nav class="border-b border-slate-200">
        <ul class="flex gap-4 text-sm">
          <li>
            <button
              class="border-b-2 px-1 pb-2"
              :class="tab === 'refs' ? 'border-blue-600 text-blue-600 font-semibold' : 'border-transparent text-slate-600 hover:text-slate-900'"
              @click="tab = 'refs'"
            >
              引用 ({{ refCount ?? '…' }})
            </button>
          </li>
          <li>
            <button
              class="border-b-2 px-1 pb-2"
              :class="tab === 'cited' ? 'border-blue-600 text-blue-600 font-semibold' : 'border-transparent text-slate-600 hover:text-slate-900'"
              @click="tab = 'cited'"
            >
              被引用 ({{ citedCount ?? '…' }})
            </button>
          </li>
        </ul>
      </nav>

      <!-- ── 引用 Tab ── -->
      <div v-if="tab === 'refs'" class="space-y-4">
        <p v-if="!detail.paper.doi" class="text-xs text-amber-600">缺少 DOI，无法查询 API，仅显示已入库引用</p>
        <p v-else-if="btTaskId" class="rounded bg-blue-50 px-3 py-2 text-xs text-blue-700">
          后台处理中（task #{{ btTaskId }}），首次查询需调外部 API，可关闭页面，完成后下次访问即用缓存秒回。
        </p>
        <p v-else-if="btLoading" class="text-xs text-slate-400">查询中…</p>
        <p v-if="btError" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
          {{ btError }}
        </p>

        <div v-if="btResult">
          <div class="mb-2 text-sm text-slate-500">
            {{ btResult.references_count }} 篇引用
            <span v-if="btResult.cached" class="ml-2 text-xs">(来自缓存)</span>
          </div>
          <ul class="divide-y divide-slate-100">
            <li
              v-for="(r, i) in btResult.referenced_papers"
              :key="r.doi || i"
              class="py-3 space-y-0.5"
            >
              <div class="text-sm font-medium text-slate-700 leading-snug">{{ r.title || '(无标题)' }}</div>
              <div class="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                <span>{{ r.year ?? '?' }}</span>
                <span>·</span>
                <span class="truncate">{{ r.authors }}</span>
                <span class="rounded bg-slate-100 px-1 text-slate-500">{{ r.source }}</span>
              </div>
              <div v-if="r.venue_name || r.doi" class="text-xs text-slate-400">
                <span v-if="r.venue_name">{{ r.venue_name }}</span>
                <span v-if="r.venue_name && r.doi"> · </span>
                <span v-if="r.doi" class="font-mono">{{ r.doi }}</span>
              </div>
              <details v-if="r.abstract" class="mt-1">
                <summary class="cursor-pointer text-xs text-blue-600 hover:underline">摘要</summary>
                <p class="mt-1 text-xs text-slate-600 leading-relaxed">{{ r.abstract }}</p>
              </details>
            </li>
          </ul>
          <div v-if="btResult.has_more" class="mt-3 text-center">
            <Button variant="secondary" size="sm" :loading="btLoadMoreLoading" :disabled="btLoadMoreLoading" @click="loadMoreBackward">
              {{ btLoadMoreLoading ? '加载中…' : `加载更多（已显示 ${btResult.referenced_papers.length} / ${btResult.references_count}）` }}
            </Button>
          </div>
        </div>

        <EmptyState v-else-if="!btLoading && !btTaskId && detail.paper.doi" title="暂无引用数据" description="" />
      </div>

      <!-- ── 被引用 Tab ── -->
      <div v-else-if="tab === 'cited'" class="space-y-3">
        <p v-if="!detail.paper.doi" class="text-xs text-amber-600">缺少 DOI，无法查询</p>
        <p v-else-if="ftTaskId" class="rounded bg-blue-50 px-3 py-2 text-xs text-blue-700">
          后台处理中（task #{{ ftTaskId }}），首次查询需调外部 API，可关闭页面，完成后下次访问即用缓存秒回。
        </p>
        <p v-else-if="ftLoading" class="text-xs text-slate-400">查询中…</p>
        <ErrorState v-if="ftError" :message="ftError" @retry="runForwardTrack(false)" />

        <div v-if="ftResult">
          <div class="mb-2 flex items-center gap-3 text-sm text-slate-500">
            <span>{{ ftResult.citing_count }} 篇被引用</span>
            <span v-if="ftResult.cached" class="text-xs">(来自缓存)</span>
            <Button v-if="detail.paper.doi" variant="ghost" size="sm" class="ml-auto" :disabled="ftLoading" @click="runForwardTrack(true)">↻ 刷新</Button>
          </div>
          <ul class="divide-y divide-slate-100">
            <li
              v-for="(c, i) in ftResult.citing_papers"
              :key="c.doi || i"
              class="py-3 space-y-0.5"
            >
              <div class="text-sm font-medium text-slate-700 leading-snug">{{ c.title || '(无标题)' }}</div>
              <div class="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                <span>{{ c.year ?? '?' }}</span>
                <span>·</span>
                <span class="truncate">{{ c.authors }}</span>
                <span class="rounded bg-slate-100 px-1 text-slate-500">{{ c.source }}</span>
              </div>
              <div v-if="c.venue_name || c.doi" class="text-xs text-slate-400">
                <span v-if="c.venue_name">{{ c.venue_name }}</span>
                <span v-if="c.venue_name && c.doi"> · </span>
                <span v-if="c.doi" class="font-mono">{{ c.doi }}</span>
              </div>
              <details v-if="c.abstract" class="mt-1">
                <summary class="cursor-pointer text-xs text-blue-600 hover:underline">摘要</summary>
                <p class="mt-1 text-xs text-slate-600 leading-relaxed">{{ c.abstract }}</p>
              </details>
            </li>
          </ul>
          <div v-if="ftResult.has_more" class="mt-3 text-center">
            <Button variant="secondary" size="sm" :loading="ftLoadMoreLoading" :disabled="ftLoadMoreLoading" @click="loadMoreForward">
              {{ ftLoadMoreLoading ? '加载中…' : `加载更多（已显示 ${ftResult.citing_papers.length} / ${ftResult.citing_count}）` }}
            </Button>
          </div>
        </div>
        <p v-if="!ftResult && !ftLoading && !ftTaskId && !detail.paper.is_core" class="text-xs text-slate-400">
          探索库论文不统计被引量。如需查看，请先加入核心库。
        </p>
      </div>
    </article>
  </section>
</template>
