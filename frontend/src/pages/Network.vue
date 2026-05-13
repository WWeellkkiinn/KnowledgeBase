<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import cytoscape, { type Core } from 'cytoscape'
import { networkApi } from '@/api/endpoints'
import type { NetworkGraph } from '@/types/api'

const router = useRouter()
const container = ref<HTMLDivElement | null>(null)
const cy = shallowRef<Core | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const stats = ref<{ nodes: number; edges: number; total: number; truncated: boolean }>({
  nodes: 0,
  edges: 0,
  total: 0,
  truncated: false,
})
let disposed = false

// Tier → 颜色（PLAN §M3.4 要求按 Tier 着色）
const TIER_COLOR: Record<string, string> = {
  '1': '#fbbf24', // 金
  '2': '#a3a3a3', // 银
  '3': '#b45309', // 铜
  unknown: '#94a3b8',
}

function colorFor(tier: number | null): string {
  if (tier === null || tier === undefined) return TIER_COLOR.unknown
  return TIER_COLOR[String(tier)] ?? TIER_COLOR.unknown
}

async function render() {
  loading.value = true
  error.value = null
  try {
    const data: NetworkGraph & { total?: number; truncated?: boolean } =
      await networkApi.get(1000)
    if (disposed) return  // 组件已卸载，丢弃响应
    stats.value = {
      nodes: data.nodes.length,
      edges: data.edges.length,
      total: data.total ?? data.nodes.length,
      truncated: data.truncated ?? false,
    }
    if (!container.value) return

    cy.value?.destroy()
    cy.value = null
    // 节点数大时改用更稳的 grid layout，避免 cose 在 200+ 节点冻结主线程
    // （C2+X2 审查）。100 是经验阈值。
    const layoutName = data.nodes.length > 100 ? 'grid' : 'cose'
    cy.value = cytoscape({
      container: container.value,
      elements: [
        ...data.nodes.map((n) => ({
          data: {
            id: String(n.id),
            label: n.title ? n.title.slice(0, 40) : n.stem,
            tier: n.quality_tier,
            color: colorFor(n.quality_tier),
            source: n.source,
          },
        })),
        ...data.edges.map((e) => ({
          data: {
            id: `e${e.id}`,
            source: String(e.from),
            target: String(e.to),
          },
        })),
      ],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': 'data(color)',
            label: 'data(label)',
            'font-size': '10px',
            color: '#1e293b',
            'text-wrap': 'wrap',
            'text-max-width': '120px',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            width: 24,
            height: 24,
            'border-width': 1,
            'border-color': '#475569',
          },
        },
        {
          selector: 'node[source = "root"]',
          style: {
            width: 36,
            height: 36,
            'border-width': 2,
            'border-color': '#0f172a',
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1,
            'line-color': '#cbd5e1',
            'target-arrow-color': '#94a3b8',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
          },
        },
      ],
      layout: { name: layoutName, animate: false, fit: true, padding: 30 },
      wheelSensitivity: 0.2,
    })

    cy.value.on('tap', 'node', (evt) => {
      const id = evt.target.id()
      router.push(`/papers/${id}`)
    })
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(render)
onBeforeUnmount(() => {
  disposed = true
  cy.value?.destroy()
  cy.value = null
})
</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Network</h1>
      <div class="flex items-center gap-3 text-sm text-slate-500">
        <span>
          {{ stats.nodes }} 节点 · {{ stats.edges }} 边
          <span v-if="stats.truncated" class="ml-1 text-amber-600">
            (共 {{ stats.total }}，已截断)
          </span>
        </span>
        <button
          class="rounded border border-slate-300 px-3 py-1 hover:bg-slate-50 disabled:opacity-50"
          :disabled="loading"
          @click="render"
        >
          {{ loading ? '加载中…' : '重绘' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
      {{ error }}
    </p>

    <div class="flex items-center gap-4 text-xs text-slate-500">
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#fbbf24"></span>
        Tier 1
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#a3a3a3"></span>
        Tier 2
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#b45309"></span>
        Tier 3
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#94a3b8"></span>
        未知 / 无期刊
      </span>
      <span class="ml-4">大节点 = root，箭头 = 引用方向</span>
    </div>

    <div
      ref="container"
      class="h-[640px] w-full rounded-lg border border-slate-200 bg-white"
    ></div>
  </section>
</template>
