<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { papersApi } from '@/api/endpoints'
import type { ForwardTrackResult, PaperDetail } from '@/types/api'

const route = useRoute()
// props.id 来自路由 props: true；watch route.params 是为了 PaperDetail 互跳。
// 用 route.params 作为单一真值源，避免 props/route 不同帧的竞态（C1 审查）。
defineProps<{ id: string }>()
const paperId = computed(() => Number(route.params.id))

const detail = ref<PaperDetail | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const tab = ref<'overview' | 'refs' | 'cited'>('overview')

async function load() {
  loading.value = true
  error.value = null
  detail.value = null
  try {
    detail.value = await papersApi.get(paperId.value)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.params.id, load)

// ─ Cited by (forward-track) ─
const ftResult = ref<ForwardTrackResult | null>(null)
const ftLoading = ref(false)
const ftError = ref<string | null>(null)

async function runForwardTrack(refresh = false) {
  ftLoading.value = true
  ftError.value = null
  try {
    ftResult.value = await papersApi.forwardTrack(paperId.value, { refresh })
  } catch (e: unknown) {
    ftError.value = e instanceof Error ? e.message : String(e)
  } finally {
    ftLoading.value = false
  }
}

const tierLabel = computed(() => {
  const t = detail.value?.paper.journal?.quality_tier
  return t ? `Tier ${t}` : '—'
})
</script>

<template>
  <section class="space-y-5">
    <RouterLink to="/papers" class="text-sm text-blue-600 hover:underline">
      ← 返回 Papers
    </RouterLink>

    <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
      {{ error }}
    </p>
    <p v-if="loading" class="text-sm text-slate-500">加载中…</p>

    <article v-if="detail" class="space-y-4">
      <header>
        <h1 class="text-2xl font-bold">
          {{ detail.paper.title || detail.paper.stem }}
        </h1>
        <div class="mt-1 text-sm text-slate-500">
          <span>{{ detail.paper.year ?? '年份未知' }}</span>
          <span v-if="detail.paper.doi" class="ml-3">DOI: {{ detail.paper.doi }}</span>
          <span class="ml-3">来源: {{ detail.paper.source }}</span>
          <span class="ml-3">状态: {{ detail.paper.status }}</span>
        </div>
        <div v-if="detail.paper.journal" class="mt-2 text-sm">
          <span class="font-medium text-slate-700">
            {{ detail.paper.journal.name }}
          </span>
          <span class="ml-2 rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700">
            {{ tierLabel }}
          </span>
          <span
            v-if="detail.paper.journal.is_predatory"
            class="ml-2 rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-700"
          >
            predatory
          </span>
        </div>
        <div class="mt-3 flex gap-2 text-sm">
          <a
            v-if="detail.paper.doi"
            :href="papersApi.citationBibUrl(detail.paper.id)"
            class="rounded border border-slate-300 px-3 py-1 hover:bg-slate-50"
          >
            下载 BibTeX
          </a>
        </div>
      </header>

      <nav class="border-b border-slate-200">
        <ul class="flex gap-4 text-sm">
          <li>
            <button
              class="border-b-2 px-1 pb-2"
              :class="
                tab === 'overview'
                  ? 'border-blue-600 text-blue-600 font-semibold'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              "
              @click="tab = 'overview'"
            >
              概览
            </button>
          </li>
          <li>
            <button
              class="border-b-2 px-1 pb-2"
              :class="
                tab === 'refs'
                  ? 'border-blue-600 text-blue-600 font-semibold'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              "
              @click="tab = 'refs'"
            >
              References ({{ detail.edges_out.length }})
            </button>
          </li>
          <li>
            <button
              class="border-b-2 px-1 pb-2"
              :class="
                tab === 'cited'
                  ? 'border-blue-600 text-blue-600 font-semibold'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              "
              @click="tab = 'cited'"
            >
              Cited by
            </button>
          </li>
        </ul>
      </nav>

      <div v-if="tab === 'overview'" class="space-y-2 text-sm">
        <div v-if="detail.paper.pdf_path">
          <span class="text-slate-500">PDF:</span>
          <code class="ml-2">{{ detail.paper.pdf_path }}</code>
        </div>
        <div v-if="detail.paper.insight_path">
          <span class="text-slate-500">Insight:</span>
          <code class="ml-2">{{ detail.paper.insight_path }}</code>
        </div>
        <div v-if="detail.paper.refs_path">
          <span class="text-slate-500">Refs:</span>
          <code class="ml-2">{{ detail.paper.refs_path }}</code>
        </div>
      </div>

      <div v-else-if="tab === 'refs'">
        <p v-if="detail.edges_out.length === 0" class="text-sm text-slate-500">
          无引用边。
        </p>
        <ul v-else class="divide-y divide-slate-100">
          <li v-for="e in detail.edges_out" :key="e.id" class="py-2 text-sm">
            <span class="text-slate-400">#{{ e.ref_index ?? '?' }}</span>
            <span class="ml-2">{{ e.ref_title || '(无标题)' }}</span>
            <RouterLink
              v-if="e.to_paper_id"
              :to="`/papers/${e.to_paper_id}`"
              class="ml-2 text-xs text-blue-600 hover:underline"
            >
              已入库 →
            </RouterLink>
          </li>
        </ul>
      </div>

      <div v-else-if="tab === 'cited'" class="space-y-3">
        <div class="flex items-center gap-2 text-sm">
          <button
            class="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700 disabled:opacity-50"
            :disabled="ftLoading || !detail.paper.doi"
            @click="runForwardTrack(false)"
          >
            {{ ftLoading ? '查询中…' : '触发前向追踪' }}
          </button>
          <button
            v-if="ftResult"
            class="rounded border border-slate-300 px-3 py-1 hover:bg-slate-50"
            :disabled="ftLoading"
            @click="runForwardTrack(true)"
          >
            强制刷新
          </button>
          <span v-if="!detail.paper.doi" class="text-xs text-amber-600">
            缺 DOI，无法前向追踪
          </span>
        </div>

        <p v-if="ftError" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
          {{ ftError }}
        </p>

        <div v-if="ftResult">
          <div class="text-sm text-slate-500">
            {{ ftResult.citing_count }} 篇引用
            <span v-if="ftResult.cached" class="ml-2 text-xs">(来自缓存)</span>
          </div>
          <ul class="mt-2 divide-y divide-slate-100">
            <li
              v-for="(c, i) in ftResult.citing_papers"
              :key="i"
              class="py-2 text-sm"
            >
              <div class="font-medium text-slate-700">{{ c.title || '(无标题)' }}</div>
              <div class="text-xs text-slate-500">
                {{ c.authors }} · {{ c.year ?? '?' }}
                <span class="ml-2 rounded bg-slate-100 px-1 text-slate-500">
                  {{ c.source }}
                </span>
                <span v-if="c.doi" class="ml-2">{{ c.doi }}</span>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </article>
  </section>
</template>
