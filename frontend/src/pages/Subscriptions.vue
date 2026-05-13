<script setup lang="ts">
import axios from 'axios'
import { onMounted, reactive, ref } from 'vue'
import { subscriptionsApi } from '@/api/endpoints'
import { useSubscriptionsStore } from '@/stores/subscriptions'

const store = useSubscriptionsStore()
const showForm = ref(false)
const error = ref<string | null>(null)
const submitting = ref(false)

const form = reactive({
  type: 'paper_citations' as 'paper_citations' | 'author_works' | 'topic_search',
  doi: '',
  author_id: '',
  query: '',
  cron_expr: 'every 7d',
})

onMounted(() => store.fetchAll())

function targetFor(): Record<string, unknown> {
  if (form.type === 'paper_citations') return { doi: form.doi.trim() }
  if (form.type === 'author_works') return { author_id: form.author_id.trim() }
  return { query: form.query.trim() }
}

async function submit() {
  error.value = null
  submitting.value = true
  try {
    await subscriptionsApi.create({
      type: form.type,
      target: targetFor(),
      cron_expr: form.cron_expr,
    })
    showForm.value = false
    await store.fetchAll()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}

async function toggleActive(id: number, current: boolean) {
  try {
    await subscriptionsApi.update(id, { active: !current })
    await store.fetchAll()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function remove(id: number) {
  try {
    await subscriptionsApi.delete(id)
    await store.fetchAll()
  } catch (e: unknown) {
    // 用 axios 的 status code 判断，不依赖错误 message 字符串
    if (axios.isAxiosError(e) && e.response?.status === 409) {
      if (confirm('该订阅有未读 Inbox，确认强制删除？')) {
        await subscriptionsApi.delete(id, true)
        await store.fetchAll()
      }
      return
    }
    error.value = e instanceof Error ? e.message : String(e)
  }
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Subscriptions</h1>
      <button
        class="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
        @click="showForm = !showForm"
      >
        {{ showForm ? '取消' : '新建订阅' }}
      </button>
    </div>

    <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700">
      {{ error }}
    </p>

    <form
      v-if="showForm"
      class="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm"
      @submit.prevent="submit"
    >
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-semibold text-slate-600">类型</label>
          <select v-model="form.type" class="w-full rounded border border-slate-300 px-2 py-1">
            <option value="paper_citations">论文被引（paper_citations）</option>
            <option value="author_works">作者新作（author_works）</option>
            <option value="topic_search">话题搜索（topic_search）</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-slate-600">触发周期</label>
          <input
            v-model="form.cron_expr"
            class="w-full rounded border border-slate-300 px-2 py-1"
            placeholder="every 7d / 0 3 * * 1"
          />
        </div>
      </div>
      <div v-if="form.type === 'paper_citations'">
        <label class="mb-1 block text-xs font-semibold text-slate-600">DOI</label>
        <input
          v-model="form.doi"
          class="w-full rounded border border-slate-300 px-2 py-1"
          placeholder="10.1234/abc"
        />
      </div>
      <div v-if="form.type === 'author_works'">
        <label class="mb-1 block text-xs font-semibold text-slate-600">作者 ID</label>
        <input
          v-model="form.author_id"
          class="w-full rounded border border-slate-300 px-2 py-1"
          placeholder="OpenAlex / SS author id"
        />
      </div>
      <div v-if="form.type === 'topic_search'">
        <label class="mb-1 block text-xs font-semibold text-slate-600">查询词</label>
        <input
          v-model="form.query"
          class="w-full rounded border border-slate-300 px-2 py-1"
          placeholder="agent-based model AND inequality"
        />
      </div>
      <button
        type="submit"
        class="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        :disabled="submitting"
      >
        {{ submitting ? '提交中…' : '创建' }}
      </button>
    </form>

    <div class="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-left text-xs uppercase text-slate-500">
          <tr>
            <th class="px-3 py-2">#</th>
            <th class="px-3 py-2">类型</th>
            <th class="px-3 py-2">Target</th>
            <th class="px-3 py-2">周期</th>
            <th class="px-3 py-2">下次</th>
            <th class="px-3 py-2">状态</th>
            <th class="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="store.items.length === 0">
            <td colspan="7" class="px-3 py-6 text-center text-slate-400">
              暂无订阅
            </td>
          </tr>
          <tr v-for="s in store.items" :key="s.id" class="hover:bg-slate-50">
            <td class="px-3 py-2 text-slate-400">{{ s.id }}</td>
            <td class="px-3 py-2">{{ s.type }}</td>
            <td class="px-3 py-2 text-slate-600 text-xs">
              <code>{{ JSON.stringify(s.target) }}</code>
            </td>
            <td class="px-3 py-2 text-slate-600">{{ s.cron_expr }}</td>
            <td class="px-3 py-2 text-xs text-slate-500">{{ s.next_run_at || '—' }}</td>
            <td class="px-3 py-2">
              <button
                class="rounded px-1.5 py-0.5 text-xs font-medium"
                :class="
                  s.active
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-slate-100 text-slate-600'
                "
                @click="toggleActive(s.id, s.active)"
              >
                {{ s.active ? 'active' : 'paused' }}
              </button>
            </td>
            <td class="px-3 py-2 text-right">
              <button
                class="text-xs text-rose-600 hover:underline"
                @click="remove(s.id)"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
