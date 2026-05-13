<script setup lang="ts">
import { onMounted, ref, shallowRef, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { papersApi } from '@/api/endpoints'
import type { Paper } from '@/types/api'

const papers = ref<Paper[]>([])
const selected = ref<Set<number>>(new Set())
const focus = ref('研究方法')
const output = ref('')
const rendered = shallowRef('')
const running = ref(false)
const error = ref<string | null>(null)
let abortCtrl: AbortController | null = null
// 防止 abort 后旧 reader 仍写入新一次运行的 output（C1 审查）
let runToken = 0
// 节流标记：每个 chunk 进来不立刻 marked+sanitize 整文，使用 trailing-edge
// 100ms 间隔 + 结束兜底（C1+C2+X2 审查）
let renderTimer: number | null = null
const RENDER_THROTTLE_MS = 100

onMounted(async () => {
  const resp = await papersApi.list({ status: 'analyzed', limit: 500 })
  papers.value = resp.items
})

function toggle(id: number) {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
  // Vue 反应性：Set 修改需要触发 trigger，重新赋值
  selected.value = new Set(selected.value)
}

function selectAll() {
  selected.value = new Set(papers.value.map((p) => p.id))
}
function clearAll() {
  selected.value = new Set()
}

async function run() {
  if (selected.value.size === 0) {
    error.value = '请至少选择 1 篇论文'
    return
  }
  // 取消上一次（如有）
  abortCtrl?.abort()
  runToken += 1
  const myToken = runToken
  running.value = true
  error.value = null
  output.value = ''
  rendered.value = ''
  abortCtrl = new AbortController()

  try {
    const resp = await fetch('/api/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper_ids: Array.from(selected.value),
        focus: focus.value,
      }),
      signal: abortCtrl.signal,
    })
    if (myToken !== runToken) return
    if (!resp.ok || !resp.body) {
      const txt = await resp.text().catch(() => '')
      throw new Error(`HTTP ${resp.status}: ${txt || resp.statusText}`)
    }
    await readSse(resp.body, myToken)
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') return
    if (myToken !== runToken) return
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (myToken === runToken) {
      running.value = false
      scheduleRender(true)  // 结束兜底渲染
    }
  }
}

async function readSse(body: ReadableStream<Uint8Array>, myToken: number) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      if (myToken !== runToken) break  // 被新 run 抢占
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // 同时兼容 \n\n 与 \r\n\r\n（SSE spec 允许）
      let idx: number
      while (
        (idx = buf.search(/\r?\n\r?\n/)) >= 0
      ) {
        const m = buf.slice(idx).match(/^\r?\n\r?\n/)
        const sep = m ? m[0].length : 2
        const raw = buf.slice(0, idx)
        buf = buf.slice(idx + sep)
        handleEvent(raw, myToken)
      }
    }
  } finally {
    try { reader.releaseLock() } catch { /* already released */ }
  }
}

function handleEvent(raw: string, myToken: number) {
  if (myToken !== runToken) return
  let event = 'message'
  let data = ''
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) {
      // SSE spec: data 多行应以 \n join；后端 emit 单行 data，所以拼接即可
      data += (data ? '\n' : '') + line.slice(5).replace(/^ /, '')
    }
  }
  if (event === 'chunk') {
    try {
      output.value += JSON.parse(data) as string
      scheduleRender()
    } catch {
      output.value += data
      scheduleRender()
    }
  } else if (event === 'error') {
    try {
      const obj = JSON.parse(data) as { error?: string }
      error.value = obj.error ?? data
    } catch {
      error.value = data
    }
  }
  // done 事件：自然结束
}

function scheduleRender(immediate = false) {
  if (immediate) {
    if (renderTimer !== null) {
      window.clearTimeout(renderTimer)
      renderTimer = null
    }
    rendered.value = DOMPurify.sanitize(
      marked.parse(output.value || '', { async: false }) as string,
    )
    return
  }
  if (renderTimer !== null) return
  renderTimer = window.setTimeout(() => {
    renderTimer = null
    rendered.value = DOMPurify.sanitize(
      marked.parse(output.value || '', { async: false }) as string,
    )
  }, RENDER_THROTTLE_MS)
}

function cancel() {
  abortCtrl?.abort()
  runToken += 1  // 抢占当前 token，让旧 readSse / handleEvent 丢弃
  running.value = false
}

watch(output, (v) => {
  if (!v) rendered.value = ''
})
</script>

<template>
  <section class="space-y-4">
    <h1 class="text-2xl font-bold">Review</h1>

    <div class="grid gap-4 lg:grid-cols-[300px_1fr]">
      <aside class="space-y-3">
        <div>
          <label class="mb-1 block text-xs font-semibold text-slate-600">
            关注维度
          </label>
          <input
            v-model="focus"
            class="w-full rounded border border-slate-300 px-2 py-1 text-sm"
            placeholder="如：研究方法 / 数据来源 / 政策含义"
          />
        </div>
        <div class="flex items-center justify-between text-xs">
          <span class="text-slate-500">
            已选 {{ selected.size }} / {{ papers.length }}
          </span>
          <div class="flex gap-2">
            <button class="text-blue-600 hover:underline" @click="selectAll">
              全选
            </button>
            <button class="text-slate-500 hover:underline" @click="clearAll">
              清空
            </button>
          </div>
        </div>
        <div
          class="max-h-96 overflow-y-auto rounded border border-slate-200 bg-white"
        >
          <ul class="divide-y divide-slate-100 text-sm">
            <li
              v-for="p in papers"
              :key="p.id"
              class="flex items-start gap-2 px-3 py-2"
            >
              <input
                type="checkbox"
                :checked="selected.has(p.id)"
                class="mt-1"
                @change="toggle(p.id)"
              />
              <span class="flex-1 cursor-pointer" @click="toggle(p.id)">
                <span class="text-slate-700">{{ p.title || p.stem }}</span>
                <span v-if="p.year" class="ml-1 text-xs text-slate-400">
                  ({{ p.year }})
                </span>
              </span>
            </li>
          </ul>
        </div>
        <div class="flex gap-2">
          <button
            class="flex-1 rounded bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            :disabled="running || selected.size === 0"
            @click="run"
          >
            {{ running ? '生成中…' : '生成综述' }}
          </button>
          <button
            v-if="running"
            class="rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
            @click="cancel"
          >
            取消
          </button>
        </div>
      </aside>

      <article class="rounded-lg border border-slate-200 bg-white p-4">
        <p v-if="error" class="mb-3 rounded bg-rose-50 p-3 text-sm text-rose-700">
          {{ error }}
        </p>
        <p v-if="!output && !running" class="text-sm text-slate-500">
          选择论文后点击「生成综述」开始流式输出。
        </p>
        <div
          v-else
          class="prose max-w-none text-sm leading-relaxed"
          v-html="rendered"
        ></div>
      </article>
    </div>
  </section>
</template>

<style>
.prose h1 { font-size: 1.5rem; font-weight: 700; margin-top: 1rem; }
.prose h2 { font-size: 1.2rem; font-weight: 600; margin-top: 1rem; }
.prose p { margin: 0.5rem 0; }
.prose table { width: 100%; border-collapse: collapse; margin: 0.5rem 0; }
.prose th, .prose td { border: 1px solid #e2e8f0; padding: 4px 8px; font-size: 0.85rem; }
.prose th { background: #f1f5f9; }
.prose code { background: #f1f5f9; padding: 0 4px; border-radius: 3px; }
</style>
