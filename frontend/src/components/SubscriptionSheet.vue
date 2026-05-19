<script setup lang="ts">
import { onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { subscriptionsApi } from '@/api/endpoints'
import { useSubscriptionsStore } from '@/stores/subscriptions'

const emit = defineEmits<{ close: [] }>()

const store = useSubscriptionsStore()
const error = ref<string | null>(null)
const submitting = ref(false)
const modalOpen = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({ description: '', active: true })

let pollTimer: ReturnType<typeof setInterval> | null = null

function isPending(s: typeof store.items[number]): boolean {
  return Boolean(s.description) && (!s.generated_queries || s.generated_queries.length === 0)
}

function startPollingIfNeeded() {
  const hasPending = store.items.some(isPending)
  if (hasPending && !pollTimer) {
    pollTimer = setInterval(async () => {
      await store.fetchAll(true)
      if (!store.items.some(isPending)) stopPolling()
    }, 10_000)
  } else if (!hasPending && pollTimer) {
    stopPolling()
  }
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

watch(() => store.items, startPollingIfNeeded, { deep: true })

onMounted(() => { store.fetchAll().then(startPollingIfNeeded); window.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { stopPolling(); window.removeEventListener('keydown', onKey) })

function onKey(e: KeyboardEvent) { if (e.key === 'Escape' && modalOpen.value) close() }

function openCreate() {
  editingId.value = null
  Object.assign(form, { description: '', active: true })
  error.value = null
  modalOpen.value = true
}

function openEdit(s: typeof store.items[number]) {
  editingId.value = s.id
  form.description = s.description ?? ''
  form.active = s.active
  error.value = null
  modalOpen.value = true
}

function close() { modalOpen.value = false }

async function submit() {
  if (!form.description.trim()) { error.value = '请填写研究兴趣描述'; return }
  submitting.value = true
  error.value = null
  try {
    if (editingId.value === null) {
      await subscriptionsApi.create({ description: form.description.trim() })
    } else {
      await subscriptionsApi.update(editingId.value, { active: form.active, description: form.description.trim() })
    }
    close()
    await store.fetchAll(true)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}

async function confirmDelete() {
  if (!confirm('确定删除该领域？')) return
  try {
    await subscriptionsApi.delete(editingId.value!)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
    return
  }
  close()
  await store.fetchAll(true)
}
</script>

<template>
  <div class="sheet-content">
    <div class="sheet-header">
      <h2>感兴趣的领域</h2>
      <button class="close-btn" @click="emit('close')">✕</button>
    </div>

    <div class="sheet-body">
      <div class="flex items-center justify-between" style="margin-bottom:12px">
        <div></div>
        <button class="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700" @click="openCreate">
          添加领域
        </button>
      </div>

      <p v-if="error" class="rounded bg-rose-50 p-3 text-sm text-rose-700" style="margin-bottom:8px">{{ error }}</p>

      <div class="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th class="px-3 py-2">#</th>
              <th class="px-3 py-2">描述/检索式</th>
              <th class="px-3 py-2">状态</th>
              <th class="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-if="store.items.length === 0">
              <td colspan="4" class="px-3 py-6 text-center text-slate-400">暂无领域</td>
            </tr>
            <tr v-for="s in store.items" :key="s.id" class="hover:bg-slate-50">
              <td class="px-3 py-2 text-slate-400">{{ s.id }}</td>
              <td class="px-3 py-2 text-slate-600 text-xs max-w-md">
                <div class="line-clamp-2">{{ s.description || '(无描述)' }}</div>
                <div v-if="isPending(s)" class="mt-1 inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">
                  <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500"></span>
                  LLM 正在生成检索式…
                </div>
                <details v-else-if="s.generated_queries?.length" class="mt-1">
                  <summary class="cursor-pointer text-slate-400">LLM 生成 {{ s.generated_queries.length }} 条检索式</summary>
                  <ul class="ml-4 list-disc text-slate-500">
                    <li v-for="q in s.generated_queries" :key="q">{{ q }}</li>
                  </ul>
                </details>
              </td>
              <td class="px-3 py-2">
                <span
                  class="rounded px-1.5 py-0.5 text-xs font-medium"
                  :class="s.active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'"
                >
                  {{ s.active ? '运行中' : '已暂停' }}
                </span>
              </td>
              <td class="px-3 py-2 text-right">
                <button class="text-xs text-slate-600 hover:underline" @click="openEdit(s)">编辑</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="modalOpen" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="close"></div>
      <div class="relative z-10 w-full max-w-2xl rounded-lg bg-white shadow-xl mx-4">
        <header class="flex items-center justify-between border-b px-4 py-3">
          <h2 class="text-lg font-semibold">
            {{ editingId === null ? '新建领域' : `编辑领域 #${editingId}` }}
          </h2>
          <button class="text-slate-400 hover:text-slate-700" @click="close">✕</button>
        </header>

        <form @submit.prevent="submit" class="space-y-3 p-4 text-sm">
          <p v-if="error" class="rounded bg-rose-50 p-2 text-xs text-rose-700">{{ error }}</p>

          <div>
            <label class="mb-1 block text-xs font-semibold text-slate-600">
              你关注哪个研究方向？
              <span class="ml-1 font-normal text-slate-400">LLM 用这个描述生成检索式 + 给候选打分</span>
            </label>
            <textarea
              v-model="form.description"
              rows="3"
              maxlength="1000"
              placeholder="例如：ABM 应用于宏观经济动态、金融市场、企业行为。"
              class="w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </div>

          <div v-if="editingId !== null">
            <label class="mb-1 block text-xs font-semibold text-slate-600">状态</label>
            <label class="flex cursor-pointer items-center gap-2">
              <input type="checkbox" v-model="form.active" class="h-4 w-4 rounded border-slate-300" />
              <span class="text-xs">{{ form.active ? '运行中' : '已暂停' }}</span>
            </label>
          </div>
        </form>

        <footer class="flex justify-end gap-2 border-t px-4 py-3">
          <button type="button" @click="close" class="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50">取消</button>
          <button
            v-if="editingId !== null"
            type="button"
            @click="confirmDelete"
            class="rounded border border-rose-300 px-3 py-1 text-sm text-rose-600 hover:bg-rose-50"
          >
            删除
          </button>
          <button
            @click="submit"
            :disabled="submitting"
            class="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {{ submitting ? (editingId === null ? '创建中…' : '保存中…') : (editingId === null ? '创建' : '保存') }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.sheet-content {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.sheet-header h2 {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.close-btn {
  background: none;
  border: none;
  font-size: 18px;
  color: #64748b;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}

.close-btn:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.sheet-body {
  overflow-y: auto;
}
</style>
