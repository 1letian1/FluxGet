<script setup lang="ts">
import { onMounted, ref } from 'vue'

type HealthResponse = {
  status: string
}

const backendStatus = ref('正在检查后端…')
const backendAvailable = ref(false)

onMounted(async () => {
  try {
    const response = await fetch('/api/v1/health')
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const health = (await response.json()) as HealthResponse
    backendAvailable.value = health.status === 'ok'
    backendStatus.value = backendAvailable.value ? '后端连接正常' : '后端状态异常'
  } catch {
    backendAvailable.value = false
    backendStatus.value = '后端未启动（请先运行 python main.py）'
  }
})
</script>

<template>
  <main class="page-shell">
    <section class="starter-card" aria-labelledby="page-title">
      <div class="app-mark" aria-hidden="true">↓</div>
      <p class="eyebrow">UNIVERSAL DOWNLOADER</p>
      <h1 id="page-title">通用下载器</h1>
      <p class="description">项目骨架已就绪，后续功能将按阶段逐步接入。</p>
      <div class="health-row" role="status" aria-live="polite">
        <span class="health-dot" :class="{ connected: backendAvailable }"></span>
        <span>{{ backendStatus }}</span>
      </div>
    </section>
  </main>
</template>
