<script setup lang="ts"></script>

<template>
  <div class="loading-wrap">
    <div class="bar bar-1"></div>
    <div class="bar bar-2"></div>
    <div class="bar bar-3"></div>
  </div>
</template>

<style scoped>
.loading-wrap {
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: stretch;
}

.bar {
  height: 14px;
  background: #e2e8f0;
  border-radius: 6px;
  animation: kb-pulse 1.5s ease-in-out infinite;
}

.bar-2 { width: 80%; }
.bar-3 { width: 60%; }

@keyframes kb-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: .5; }
}
</style>
