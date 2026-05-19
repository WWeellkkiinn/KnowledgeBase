<script setup lang="ts"></script>

<template>
  <div class="empty-wrap">
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="3 3">
      <circle cx="20" cy="20" r="16" />
    </svg>
    <div class="title">暂时没有新内容</div>
    <div class="subtitle">正在后台为你准备，请稍后</div>
  </div>
</template>

<style scoped>
.empty-wrap {
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #64748b;
  text-align: center;
  font-family: Inter, 'Noto Sans SC', sans-serif;
}

.title {
  font-size: 14px;
  font-weight: 500;
  color: #334155;
  margin-top: 14px;
}

.subtitle {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 6px;
}
</style>
