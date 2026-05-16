<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRecommendationsStore, type Recommendation } from '@/stores/recommendations'

const store = useRecommendationsStore()
let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  if (store.items.length === 0) store.fetch()
  refreshTimer = setInterval(() => store.fetch(), 5 * 60 * 1000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

const lastFetchedText = computed(() => {
  if (!store.lastFetchedAt) return '尚未刷新'
  try {
    const d = new Date(store.lastFetchedAt)
    return `上次刷新：${d.toLocaleString()}`
  } catch {
    return '上次刷新：—'
  }
})

const SOURCE_LABEL: Record<string, string> = {
  openalex: 'OpenAlex',
  arxiv: 'arXiv',
  semanticscholar: 'Semantic Scholar',
  crossref: 'Crossref',
}

function shortAbstract(r: Recommendation): string {
  const abstract = stripControls(r.abstract)
  return abstract.length > 300 ? `${abstract.slice(0, 300)}…` : abstract
}

function authorsText(r: Recommendation): string {
  if (!r.authors_json || r.authors_json.length === 0) return '佚名'
  const authors = r.authors_json.map((a) => stripControls(a))
  if (authors.length <= 3) return authors.join(', ')
  return `${authors.slice(0, 3).join(', ')} 等`
}

function scoreText(score: number): string {
  return score.toFixed(2)
}

function stripControls(value: string | null | undefined): string {
  return (value ?? '').replace(/[\u0000-\u001F\u007F-\u009F\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, '')
}

function matchedThemeText(r: Recommendation): string {
  const theme = stripControls(r.matched_theme) || '相关主题'
  return theme.length > 40 ? `${theme.slice(0, 40)}…` : theme
}

function sourceText(r: Recommendation): string {
  return SOURCE_LABEL[r.source] ?? stripControls(r.source)
}

function safeUrl(r: Recommendation): string {
  const url = stripControls(r.url)
  if (!url) return '#'
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? url : '#'
  } catch {
    return '#'
  }
}

async function onRegenerate() {
  await store.regenerateProfile()
}
</script>

<template>
  <section class="space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">今日推荐</h1>
        <p class="mt-1 text-xs text-slate-500">{{ lastFetchedText }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="rounded-md bg-slate-100 px-3 py-1 text-sm hover:bg-slate-200 disabled:opacity-50"
          :disabled="store.loading"
          @click="store.fetch()"
        >
          {{ store.loading ? '加载中…' : '刷新' }}
        </button>
        <button
          class="rounded-md bg-blue-50 px-3 py-1 text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          :disabled="store.regenerating"
          @click="onRegenerate"
        >
          {{ store.regenerating ? '生成中…' : '重新生成画像' }}
        </button>
      </div>
    </div>

    <p v-if="store.error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
      {{ store.error }}
    </p>

    <!-- Loading skeleton -->
    <div v-if="store.loading && store.items.length === 0" class="space-y-3">
      <div
        v-for="n in 3"
        :key="n"
        class="animate-pulse rounded-lg border border-slate-200 bg-white p-4"
      >
        <div class="h-3 w-1/3 rounded bg-slate-200" />
        <div class="mt-3 h-5 w-3/4 rounded bg-slate-200" />
        <div class="mt-2 h-3 w-1/2 rounded bg-slate-100" />
        <div class="mt-3 h-3 w-full rounded bg-slate-100" />
        <div class="mt-1 h-3 w-5/6 rounded bg-slate-100" />
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!store.loading && store.visible.length === 0"
      class="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center"
    >
      <p class="text-sm text-slate-600">
        暂无推荐。请确保已入库 ≥5 篇论文，然后生成画像。
      </p>
      <button
        class="mt-4 rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        :disabled="store.regenerating"
        @click="onRegenerate"
      >
        {{ store.regenerating ? '生成中…' : '生成画像' }}
      </button>
    </div>

    <!-- Recommendation cards -->
    <ul v-else class="space-y-3">
      <li
        v-for="rec in store.visible"
        :key="rec.id"
        class="rounded-lg border border-slate-200 bg-white p-4 hover:border-slate-300"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1 space-y-1.5">
            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span class="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">
                📌 因为你关注
                <span class="font-medium" :title="stripControls(rec.matched_theme)">
                  {{ matchedThemeText(rec) }}
                </span>
                推荐
              </span>
              <span class="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                score: {{ scoreText(rec.relevance_score) }}
              </span>
            </div>

            <h2 class="text-base font-semibold text-slate-800">
              <a
                v-if="rec.url"
                :href="safeUrl(rec)"
                target="_blank"
                rel="noopener noreferrer"
                class="text-blue-700 hover:underline"
              >
                {{ stripControls(rec.title) }}
              </a>
              <span v-else>{{ stripControls(rec.title) }}</span>
            </h2>

            <div class="text-xs text-slate-500">
              {{ authorsText(rec) }}
              <span v-if="rec.year"> · {{ rec.year }}</span>
              <span> · {{ sourceText(rec) }}</span>
            </div>

            <p v-if="rec.abstract" class="text-sm leading-relaxed text-slate-700">
              {{ shortAbstract(rec) }}
            </p>

            <p
              v-if="rec.reason"
              class="rounded bg-blue-50 px-2 py-1.5 text-xs text-blue-800"
            >
              💡 {{ stripControls(rec.reason) }}
            </p>
          </div>

          <div class="flex flex-col gap-2">
            <button
              class="whitespace-nowrap rounded-md bg-emerald-50 px-3 py-1 text-xs text-emerald-700 hover:bg-emerald-100"
              @click="store.saveToLibrary(rec.id)"
            >
              保存到库
            </button>
            <button
              class="whitespace-nowrap rounded-md bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200"
              @click="store.dismiss(rec.id)"
            >
              不感兴趣
            </button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>
