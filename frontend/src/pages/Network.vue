<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useRouter } from 'vue-router'
import cytoscape, { type Core } from 'cytoscape'
import { networkApi } from '@/api/endpoints'
import type { NetworkGraph } from '@/types/api'
import Button from '@/components/ui/Button.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import LoadingSkeleton from '@/components/ui/LoadingSkeleton.vue'
import ErrorState from '@/components/ui/ErrorState.vue'

const router = useRouter()
const container = ref<HTMLDivElement | null>(null)
const cy = shallowRef<Core | null>(null)
const loading = ref(true)
const showSkeleton = ref(false)
let skeletonTimer: ReturnType<typeof setTimeout> | null = null
const loaded = ref(false)
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
const stats = ref<{ nodes: number; edges: number; total: number; truncated: boolean }>({
  nodes: 0,
  edges: 0,
  total: 0,
  truncated: false,
})
let disposed = false

// Tier → 颜色（学术蓝色阶，PLAN §M3.4 要求按 Tier 着色）
const TIER_COLOR: Record<string, string> = {
  '1': '#1E40AF', // 深蓝
  '2': '#3B82F6', // 中蓝
  '3': '#93C5FD', // 浅蓝
  unknown: '#CBD5E1', // 中性灰
}
const HIGH_IMPACT_BORDER = '#D97706' // 琥珀，描边高亮高被引节点
const HIGH_IMPACT_RATIO = 0.6 // citation_count / max >= 此值视为高被引
const HIGH_IMPACT_MIN_MAX = 10 // max 太小（样本贫瘠）时不做"高被引"标注，避免误报

function colorFor(tier: number | null): string {
  if (tier === null || tier === undefined) return TIER_COLOR.unknown
  return TIER_COLOR[String(tier)] ?? TIER_COLOR.unknown
}

async function render() {
  loading.value = true
  loaded.value = false
  startLoading()
  error.value = null
  try {
    const data = await networkApi.get(1000) as Omit<NetworkGraph, 'nodes'> & {
      total?: number
      truncated?: boolean
      nodes: Array<NetworkGraph['nodes'][number] & {
        authors_json?: string[] | null
        citation_count?: number
      }>
    }
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
    const maxCnt = Math.max(
      data.nodes.reduce((m, n) => Math.max(m, n.citation_count ?? 0), 0),
      1,
    )
    const allowHighImpact = maxCnt >= HIGH_IMPACT_MIN_MAX
    const nodeSize = (c: number) => Math.round(16 + (c / maxCnt) * 48)
    cy.value = cytoscape({
      container: container.value,
      elements: [
        ...data.nodes.map((n) => {
          const cnt = n.citation_count ?? 0
          const highImpact = allowHighImpact && cnt / maxCnt >= HIGH_IMPACT_RATIO
          return {
            data: {
              id: String(n.id),
              label: n.authors_json?.length
                ? `${n.authors_json[0].trim().split(/\s+/).at(-1)}${n.authors_json.length > 1 ? ' et al.' : ''} · ${n.year ?? '?'}`
                : `· ${n.year ?? '?'}`,
              tier: n.quality_tier,
              color: colorFor(n.quality_tier),
              source: n.source,
              size: nodeSize(cnt),
              borderColor: highImpact ? HIGH_IMPACT_BORDER : '#1E3A8A',
              borderWidth: highImpact ? 2.5 : 1,
            },
          }
        }),
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
            width: 'data(size)',
            height: 'data(size)',
            'border-width': 'data(borderWidth)',
            'border-color': 'data(borderColor)',
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1,
            'line-color': '#DBEAFE',
            'target-arrow-color': '#93C5FD',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.8,
            'curve-style': 'bezier',
          },
        },
      ],
      layout: { name: layoutName, animate: false, fit: true, padding: 30 },
      wheelSensitivity: 0.95,
    })

    cy.value.on('tap', 'node', (evt) => {
      const id = evt.target.id()
      router.push(`/papers/${id}`)
    })
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
    loaded.value = true
    stopLoading()
  }
}

onMounted(render)
onBeforeUnmount(() => {
  disposed = true
  if (skeletonTimer) clearTimeout(skeletonTimer)
  cy.value?.destroy()
  cy.value = null
})
</script>

<template>
  <section class="space-y-4">
    <PageHeader title="引用图谱" :subtitle="`${stats.nodes} 节点 · ${stats.edges} 边${stats.truncated ? ` (共 ${stats.total}，已截断)` : ''}`">
      <template #actions>
        <Button variant="ghost" size="sm" :loading="loading" :disabled="loading" @click="render">重绘</Button>
      </template>
    </PageHeader>

    <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#1E40AF"></span>
        一级期刊
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#3B82F6"></span>
        二级期刊
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#93C5FD"></span>
        三级期刊
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full" style="background:#CBD5E1"></span>
        未知 / 无期刊
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-3 w-3 rounded-full border-[2.5px]" style="background:#fff;border-color:#D97706"></span>
        高被引
      </span>
    </div>

    <div class="graph-wrap h-[calc(100dvh-14rem)] md:h-[calc(100dvh-12rem)] min-h-[480px]">
      <LoadingSkeleton v-if="showSkeleton" variant="card" :count="1" />
      <ErrorState v-else-if="error" :message="error" @retry="render" />
      <EmptyState v-else-if="loaded && stats.nodes === 0" title="还没有引用网络" description="先在论文库里启动引用追踪" />
      <div
        v-else
        ref="container"
        class="h-full w-full rounded-lg border border-slate-200 bg-[#F8FAFC]"
      ></div>
    </div>
  </section>
</template>
