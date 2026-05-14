<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { papersApi } from '@/api/endpoints'
import type { BackwardTrackResult, ForwardTrackResult, PaperDetail } from '@/types/api'

const route = useRoute()
const router = useRouter()
defineProps<{ id: string }>()
const paperId = computed(() => Number(route.params.id))

function goBack() {
  if (window.history.state?.back) router.back()
  else router.push('/papers')
}

const detail = ref<PaperDetail | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const tab = ref<'refs' | 'cited'>('refs')

const insightContent = ref<string | null>(null)
const insightLoading = ref(false)
const insightError = ref<string | null>(null)

// ─ Cited by (forward-track) ─
const ftResult = ref<ForwardTrackResult | null>(null)
const ftLoading = ref(false)
const ftError = ref<string | null>(null)

// ─ References (backward-track) ─
const btResult = ref<BackwardTrackResult | null>(null)
const btLoading = ref(false)
const btError = ref<string | null>(null)

async function load() {
  const requestedId = paperId.value  // 捕获当前 id，防止主请求竞态
  loading.value = true
  error.value = null
  detail.value = null
  insightContent.value = null
  insightError.value = null
  insightLoading.value = false
  btResult.value = null
  btError.value = null
  btLoading.value = false  // 重置：防止旧请求 finally 竞态导致新论文无法触发追踪
  ftResult.value = null
  ftError.value = null
  ftLoading.value = false
  try {
    const result = await papersApi.get(requestedId)
    if (paperId.value !== requestedId) return  // 已切换到其他论文，丢弃响应
    detail.value = result
    // 核心论文自动触发追踪，stub 论文等待用户手动操作
    if (detail.value.paper.is_core && detail.value.paper.doi) {
      if (!btLoading.value) runBackwardTrack(false)
      if (!ftLoading.value) runForwardTrack(false)
    }
    // 有 insight 则异步加载；requestedId 防止写入错误论文
    if (detail.value.paper.insight_path) {
      insightLoading.value = true
      papersApi.getInsight(requestedId)
        .then(r => {
          if (paperId.value === requestedId) insightContent.value = r.content
        })
        .catch((e: unknown) => {
          if (paperId.value === requestedId)
            insightError.value = e instanceof Error ? e.message : String(e)
        })
        .finally(() => {
          if (paperId.value === requestedId) insightLoading.value = false
        })
    }
  } catch (e: unknown) {
    if (paperId.value === requestedId)
      error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (paperId.value === requestedId) loading.value = false
  }
}

onMounted(load)
watch(() => route.params.id, load)

watch(tab, (newTab) => {
  if (!detail.value?.paper.is_core || !detail.value?.paper.doi) return
  if (newTab === 'refs' && !btResult.value && !btLoading.value) {
    runBackwardTrack(false)
  }
  if (newTab === 'cited' && !ftResult.value && !ftLoading.value) {
    runForwardTrack(false)
  }
})

async function runForwardTrack(refresh = false) {
  const requestedId = paperId.value
  ftLoading.value = true
  ftError.value = null
  try {
    const result = await papersApi.forwardTrack(requestedId, { refresh })
    if (paperId.value === requestedId) ftResult.value = result
  } catch (e: unknown) {
    if (paperId.value === requestedId)
      ftError.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (paperId.value === requestedId) ftLoading.value = false
  }
}

async function runBackwardTrack(refresh = false) {
  const requestedId = paperId.value
  btLoading.value = true
  btError.value = null
  try {
    const result = await papersApi.backwardTrack(requestedId, { refresh })
    if (paperId.value === requestedId) btResult.value = result
  } catch (e: unknown) {
    if (paperId.value === requestedId)
      btError.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (paperId.value === requestedId) btLoading.value = false
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

const refCount = computed(() => btResult.value?.references_count ?? detail.value?.edges_out.length ?? 0)
const citedCount = computed(() => {
  if (ftResult.value) return ftResult.value.citing_count
  if (!detail.value?.paper.is_core) return 0
  return detail.value?.edges_in.length ?? 0
})
</script>

<template>
  <section class="space-y-5">
    <button @click="goBack" class="text-sm text-blue-600 hover:underline">
      ← 返回论文库
    </button>

    <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
      {{ error }}
    </p>
    <p v-if="loading" class="text-sm text-slate-500">加载中…</p>

    <article v-if="detail" class="space-y-6">
      <!-- ── 头部：结构化元数据 ── -->
      <header class="space-y-4">
        <h1 class="text-2xl font-bold leading-snug">
          {{ detail.paper.title || detail.paper.stem }}
        </h1>

        <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm items-start">
          <template v-if="authorList">
            <dt class="text-slate-400 whitespace-nowrap">作者</dt>
            <dd class="text-slate-700">{{ authorList }}</dd>
          </template>
          <dt class="text-slate-400">年份</dt>
          <dd class="text-slate-700">{{ detail.paper.year ?? '—' }}</dd>
          <dt class="text-slate-400">DOI</dt>
          <dd class="text-slate-700 text-sm flex items-baseline gap-2">
            <span class="font-mono">{{ detail.paper.doi || '—' }}</span>
            <a
              v-if="detail.paper.doi"
              :href="papersApi.citationBibUrl(detail.paper.id)"
              class="rounded border border-slate-300 px-2 py-0.5 hover:bg-slate-50"
            >
              下载 BibTeX
            </a>
          </dd>
          <dt class="text-slate-400">期刊</dt>
          <dd class="text-slate-700 flex items-center gap-2">
            <span>{{ detail.paper.journal?.name || '—' }}</span>
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

      </header>

      <!-- ── 内容分析 ── -->
      <div v-if="detail.paper.insight_path" class="rounded-lg border border-slate-200 bg-slate-50">
        <div class="border-b border-slate-200 px-4 py-2">
          <h2 class="text-sm font-semibold text-slate-700">内容分析</h2>
        </div>
        <div class="px-4 py-3">
          <p v-if="insightLoading" class="text-xs text-slate-400">加载中…</p>
          <p v-else-if="insightError" class="text-xs text-rose-500">{{ insightError }}</p>
          <pre
            v-else-if="insightContent"
            class="whitespace-pre-wrap text-xs text-slate-600 leading-relaxed font-sans"
          >{{ insightContent }}</pre>
          <p v-else class="text-xs text-slate-400">文件不存在或无内容。</p>
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
              引用 ({{ refCount }})
            </button>
          </li>
          <li>
            <button
              class="border-b-2 px-1 pb-2"
              :class="tab === 'cited' ? 'border-blue-600 text-blue-600 font-semibold' : 'border-transparent text-slate-600 hover:text-slate-900'"
              @click="tab = 'cited'"
            >
              被引用 ({{ citedCount }})
            </button>
          </li>
        </ul>
      </nav>

      <!-- ── 引用 Tab ── -->
      <div v-if="tab === 'refs'" class="space-y-4">
        <p v-if="!detail.paper.doi" class="text-xs text-amber-600">缺少 DOI，无法查询 API，仅显示已入库引用</p>
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
        </div>

        <div v-else-if="detail.edges_out.length > 0">
          <p class="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">已入库的引用</p>
          <ul class="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
            <li v-for="e in detail.edges_out" :key="e.id" class="px-3 py-2 text-sm flex items-center gap-2">
              <span class="text-slate-400 text-xs w-6 shrink-0">#{{ e.ref_index ?? '?' }}</span>
              <span class="text-slate-700 flex-1">{{ e.ref_title || '(无标题)' }}</span>
              <RouterLink
                v-if="e.to_paper_id"
                :to="`/papers/${e.to_paper_id}`"
                class="text-xs text-blue-600 hover:underline shrink-0"
              >
                已入库 →
              </RouterLink>
            </li>
          </ul>
        </div>
      </div>

      <!-- ── 被引用 Tab ── -->
      <div v-else-if="tab === 'cited'" class="space-y-3">
        <p v-if="!detail.paper.doi" class="text-xs text-amber-600">缺少 DOI，无法查询</p>
        <p v-else-if="ftLoading" class="text-xs text-slate-400">查询中…</p>
        <div v-if="ftError" class="rounded bg-rose-50 p-3 text-sm text-rose-700 flex items-center justify-between">
          <span>{{ ftError }}</span>
          <button
            v-if="detail.paper.doi"
            class="ml-3 text-xs text-rose-600 hover:text-rose-800 underline shrink-0"
            :disabled="ftLoading"
            @click="runForwardTrack(false)"
          >重试</button>
        </div>

        <div v-if="ftResult">
          <div class="mb-2 flex items-center gap-3 text-sm text-slate-500">
            <span>{{ ftResult.citing_count }} 篇被引用</span>
            <span v-if="ftResult.cached" class="text-xs">(来自缓存)</span>
            <button
              v-if="detail.paper.doi"
              class="ml-auto text-xs text-slate-400 hover:text-slate-600 disabled:opacity-40"
              :disabled="ftLoading"
              @click="runForwardTrack(true)"
            >↻ 刷新</button>
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
        </div>
        <p v-if="!ftResult && !ftLoading && !detail.paper.is_core" class="text-xs text-slate-400">
          探索库论文不统计被引量。如需查看，请先加入核心库。
        </p>
      </div>
    </article>
  </section>
</template>
