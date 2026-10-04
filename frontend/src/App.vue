<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { connectTaskEvents, type ApiTask, type TaskEvent } from './api/taskEvents'
import { getRuntimeConfig, type NativeBridgeApi } from './api/runtime'

type PageId = 'workspace' | 'history' | 'rules' | 'settings'
type Mode = 'direct' | 'rule'
type TaskStatus = 'downloading' | 'waiting' | 'completed' | 'failed' | 'cancelled' | 'skipped'
type DownloadTask = {
  id: number | string
  filename: string
  source: string
  status: TaskStatus
  progress: number
  size: string
}
type LogEntry = { timestamp: string; level: string; logger: string; message: string; filename?: string; status?: string }

const currentPage = ref<PageId>('workspace')
const mode = ref<Mode>('rule')
const outputDir = ref('D:\\Downloads\\jenkins-plugins')
const concurrency = ref(4)
const conflictPolicy = ref('overwrite')
const selectedRule = ref('Jenkins HPI')
const baseUrl = ref('https://updates.jenkins.io/download/plugins')
const ruleInput = ref('gson-api    2.10.1-15.v0d99f670e0a_7\nvariant     60.v7290fc0eb_b_cd\nworkflow-api    1316.v33be_726c50b_a_')
const directInput = ref('https://github.com/example/tool/releases/download/v1.0/tool.zip')
const template = ref('{base_url}/{name}/{version}/{name}.hpi')
const notice = ref('')
const showPreview = ref(false)
const eventConnected = ref(false)
const showLogs = ref(false)
const logsLoading = ref(false)
const logItems = ref<LogEntry[]>([])
let nextId = 4
let disconnectTaskEvents: (() => void) | undefined
let taskEventsDisposed = false

const tasks = ref<DownloadTask[]>([
  { id: 1, filename: 'gson-api.hpi', source: '规则 · Jenkins HPI · 2.10.1-15.v0d99f670e0a_7', status: 'downloading', progress: 72, size: '1.8 MB' },
  { id: 2, filename: 'variant.hpi', source: '规则 · Jenkins HPI · 60.v7290fc0eb_b_cd', status: 'waiting', progress: 0, size: '—' },
  { id: 3, filename: 'tool.zip', source: '直接 URL · github.com/example/tool/releases/…', status: 'completed', progress: 100, size: '8.4 MB' },
])

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** unit).toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function mapTask(task: ApiTask): DownloadTask {
  const status: TaskStatus = task.status === 'downloading' ? 'downloading'
    : task.status === 'completed' ? 'completed'
      : task.status === 'failed' ? 'failed'
        : task.status === 'cancelled' ? 'cancelled'
          : task.status === 'skipped' ? 'skipped' : 'waiting'
  let source = '直接 URL'
  try {
    source = task.source_type === 'rule' ? `规则 · ${task.rule_id ?? ''}` : `直接 URL · ${new URL(task.url).host}`
  } catch { /* Keep a generic source label for malformed historical data. */ }
  return { id: task.id, filename: task.filename, source, status,
    progress: task.progress ?? 0, size: task.bytes_total === null ? formatBytes(task.bytes_downloaded) : formatBytes(task.bytes_total) }
}

function applyTaskEvent(event: TaskEvent) {
  if (!event.data || typeof event.data !== 'object' || !('id' in event.data)) return
  const task = mapTask(event.data as ApiTask)
  const index = tasks.value.findIndex((item) => item.id === task.id)
  if (index < 0) tasks.value.unshift(task)
  else tasks.value[index] = task
}

onMounted(() => {
  void connectTaskEvents({
    onSnapshot: (snapshot) => { tasks.value = snapshot.map(mapTask) },
    onEvent: applyTaskEvent,
    onConnectionChange: (connected) => { eventConnected.value = connected },
  }).then((disconnect) => {
    if (taskEventsDisposed) disconnect()
    else disconnectTaskEvents = disconnect
  }).catch(() => { eventConnected.value = false })
})

onBeforeUnmount(() => { taskEventsDisposed = true; disconnectTaskEvents?.() })

const navigation: { id: PageId; label: string; icon: string }[] = [
  { id: 'workspace', label: '任务工作台', icon: '▦' },
  { id: 'history', label: '下载历史', icon: '◴' },
  { id: 'rules', label: 'URL 规则', icon: '⌘' },
  { id: 'settings', label: '偏好设置', icon: '⚙' },
]

const pageTitle = computed(() => ({ workspace: '新建下载任务', history: '下载历史', rules: 'URL 规则', settings: '偏好设置' })[currentPage.value])
const pageDescription = computed(() => ({
  workspace: '粘贴链接，或用规则从数据生成下载地址',
  history: '已完成和已停止的下载都可以在这里查找',
  rules: '用模板快速生成批量下载地址',
  settings: '配置下载目录、并发和文件处理方式',
})[currentPage.value])
const counts = computed(() => ({
  waiting: tasks.value.filter((task) => task.status === 'waiting').length,
  completed: tasks.value.filter((task) => task.status === 'completed').length,
  failed: tasks.value.filter((task) => task.status === 'failed').length,
}))
const directUrls = computed(() => directInput.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean))
const validDirectUrls = computed(() => directUrls.value.filter((url) => /^https?:\/\//i.test(url)))
const ruleRows = computed(() => ruleInput.value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
  const [name = '', version = ''] = line.split(/\s+/)
  return { name, version, valid: Boolean(name && version) }
}))
const previewItems = computed(() => ruleRows.value.filter((row) => row.valid).slice(0, 3).map(({ name, version }) => ({
  name,
  version,
  url: template.value.replaceAll('{base_url}', baseUrl.value.trim().replace(/\/$/, '')).replaceAll('{name}', name).replaceAll('{version}', version).replaceAll('{filename}', `${name}.hpi`).replaceAll('{ext}', 'hpi'),
})))

function nativeApi(): NativeBridgeApi | undefined {
  return window.pywebview?.api
}

function setNotice(message: string) {
  notice.value = message
  window.setTimeout(() => { if (notice.value === message) notice.value = '' }, 2600)
}

async function addTasks() {
  const names = mode.value === 'direct'
    ? validDirectUrls.value.map((url) => ({ filename: decodeURIComponent(url.split('/').pop()?.split('?')[0] || 'download'), source: `直接 URL · ${url.replace(/^https?:\/\//, '').slice(0, 46)}` }))
    : previewItems.value.map((item) => ({ filename: `${item.name}.hpi`, source: `规则 · ${selectedRule.value} · ${item.version}` }))

  if (!names.length) {
    setNotice(mode.value === 'direct' ? '请输入有效的 HTTP 或 HTTPS 链接' : '请输入名称和版本以生成下载地址')
    return
  }
  if (mode.value === 'direct') {
    try {
      const config = await getRuntimeConfig()
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (config.sessionToken) headers['X-Session-Token'] = config.sessionToken
      const response = await fetch(new URL('/api/v1/tasks/direct', config.apiBaseUrl), {
        method: 'POST', headers, body: JSON.stringify({ urls: directUrls.value.join('\n'), output_dir: outputDir.value }),
      })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
      const result = await response.json() as { created: ApiTask[]; errors: Array<{ line: number }> }
      for (const item of result.created) applyTaskEvent({ type: 'task.created', data: item, occurred_at: null })
      setNotice(`已加入 ${result.created.length} 个任务${result.errors.length ? `，${result.errors.length} 行无效` : ''}`)
    } catch {
      setNotice('无法连接下载服务，请确认桌面服务已启动')
    }
    return
  }
  tasks.value.unshift(...names.map((item) => ({ ...item, id: nextId++, status: 'waiting' as TaskStatus, progress: 0, size: '—' })))
  const invalidCount = mode.value === 'direct' ? directUrls.value.length - validDirectUrls.value.length : ruleRows.value.filter((row) => !row.valid).length
  setNotice(`已加入 ${names.length} 个任务${invalidCount ? `，跳过 ${invalidCount} 行无效输入` : ''}`)
}

async function stopTask(task: DownloadTask) {
  if (typeof task.id === 'string') {
    try {
      const config = await getRuntimeConfig()
      const headers = config.sessionToken ? { 'X-Session-Token': config.sessionToken } : undefined
      const response = await fetch(new URL(`/api/v1/tasks/${encodeURIComponent(task.id)}/cancel`, config.apiBaseUrl), { method: 'POST', headers })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
    } catch { setNotice(`无法停止 ${task.filename}`); return }
  } else if (task.status === 'downloading' || task.status === 'waiting') task.status = 'cancelled'
  setNotice(`已停止 ${task.filename}`)
}

async function retryTask(task: DownloadTask) {
  if (typeof task.id === 'string') {
    try {
      const config = await getRuntimeConfig()
      const headers = config.sessionToken ? { 'X-Session-Token': config.sessionToken } : undefined
      const response = await fetch(new URL(`/api/v1/tasks/${encodeURIComponent(task.id)}/retry`, config.apiBaseUrl), { method: 'POST', headers })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
    } catch { setNotice(`无法重试 ${task.filename}`); return }
  } else {
    task.status = 'waiting'
    task.progress = 0
  }
  setNotice(`已重新加入 ${task.filename}`)
}

function removeTask(task: DownloadTask) {
  tasks.value = tasks.value.filter((item) => item.id !== task.id)
}

function clearCompleted() {
  const before = tasks.value.length
  tasks.value = tasks.value.filter((task) => task.status !== 'completed')
  setNotice(`已清除 ${before - tasks.value.length} 个已完成任务`)
}

async function stopAll() {
  await Promise.all(tasks.value
    .filter((task) => task.status === 'downloading' || task.status === 'waiting')
    .map((task) => stopTask(task)))
  setNotice('已停止所有活动任务')
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const config = await getRuntimeConfig()
    const headers = config.sessionToken ? { 'X-Session-Token': config.sessionToken } : undefined
    const response = await fetch(new URL('/api/v1/logs?limit=200', config.apiBaseUrl), { headers })
    if (!response.ok) throw new Error(`Request failed (${response.status})`)
    const result = await response.json() as { items: LogEntry[] }
    logItems.value = result.items
    showLogs.value = true
  } catch {
    setNotice('无法读取应用日志')
  } finally {
    logsLoading.value = false
  }
}

async function exportLogs() {
  try {
    const config = await getRuntimeConfig()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (config.sessionToken) headers['X-Session-Token'] = config.sessionToken
    const response = await fetch(new URL('/api/v1/logs/export', config.apiBaseUrl), {
      method: 'POST', headers, body: JSON.stringify({ limit: 5000 }),
    })
    if (!response.ok) throw new Error(`Request failed (${response.status})`)
    const result = await response.json() as { filename: string; content: string; count: number }
    const url = URL.createObjectURL(new Blob([result.content], { type: 'application/x-ndjson;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = result.filename
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    setNotice(`已导出 ${result.count} 条日志`)
  } catch {
    setNotice('无法导出应用日志')
  }
}

async function chooseFolder() {
  const api = nativeApi()
  if (!api) {
    setNotice('文件夹选择仅在桌面版中可用')
    return
  }
  try {
    const selected = await api.choose_folder(outputDir.value)
    if (selected) outputDir.value = selected
  } catch {
    setNotice('无法打开文件夹选择器')
  }
}

async function openDownloadFolder() {
  const api = nativeApi()
  if (!api) {
    setNotice(`文件位置：${outputDir.value}`)
    return
  }
  try {
    if (!await api.open_folder(outputDir.value)) setNotice('下载目录不存在')
  } catch {
    setNotice('无法打开下载目录')
  }
}

function minimizeWindow() {
  void nativeApi()?.minimize()
}

function toggleMaximizeWindow() {
  void nativeApi()?.toggle_maximize()
}

function closeWindow() {
  void nativeApi()?.close_window()
}
</script>

<template>
  <main class="app-frame">
    <header class="titlebar">
      <div class="brand"><span class="brand-arrow">↓</span><strong>通用下载器</strong><span class="brand-divider">|</span><span class="brand-context">工作台</span></div>
      <div class="window-controls" aria-label="窗口控制">
        <button type="button" aria-label="最小化" @click="minimizeWindow">−</button>
        <button type="button" aria-label="最大化或还原" @click="toggleMaximizeWindow">□</button>
        <button type="button" aria-label="关闭" @click="closeWindow">×</button>
      </div>
    </header>

    <div class="app-body">
      <aside class="sidebar">
        <div class="product-mark"><span class="download-icon">↓</span><span>下载器</span></div>
        <p class="side-label">下载</p>
        <nav class="main-nav" aria-label="主导航">
          <button v-for="item in navigation.slice(0, 2)" :key="item.id" type="button" :class="{ active: currentPage === item.id }" @click="currentPage = item.id"><span class="nav-icon">{{ item.icon }}</span>{{ item.label }}</button>
        </nav>
        <p class="side-label config-label">配置</p>
        <nav class="main-nav" aria-label="配置导航">
          <button v-for="item in navigation.slice(2)" :key="item.id" type="button" :class="{ active: currentPage === item.id }" @click="currentPage = item.id"><span class="nav-icon">{{ item.icon }}</span>{{ item.label }}</button>
        </nav>
        <p class="side-label saved-label">收藏规则</p>
        <div class="saved-rules"><button type="button" @click="selectedRule = 'Jenkins HPI'; currentPage = 'workspace'"><span>◇</span>Jenkins HPI</button><button type="button" @click="selectedRule = 'GitHub Release'; currentPage = 'workspace'"><span>◇</span>GitHub Release</button></div>
        <div class="sidebar-footer"><span class="online-dot"></span>本地工作区</div>
      </aside>

      <section class="workspace">
        <div class="workspace-heading">
          <div><h1>{{ pageTitle }}</h1><p>{{ currentPage === 'workspace' ? '粘贴链接，或用规则从数据生成下载地址' : pageDescription }}</p></div>
          <div class="ready-pill"><span></span>就绪</div>
        </div>

        <template v-if="currentPage === 'workspace'">
          <section class="compose-grid">
            <article class="panel source-panel">
              <div class="panel-heading"><h2>下载来源</h2><span>支持多行批量导入</span></div>
              <div class="mode-switch" role="tablist" aria-label="下载来源模式">
                <button type="button" role="tab" :aria-selected="mode === 'direct'" :class="{ selected: mode === 'direct' }" @click="mode = 'direct'">直接 URL</button>
                <button type="button" role="tab" :aria-selected="mode === 'rule'" :class="{ selected: mode === 'rule' }" @click="mode = 'rule'">规则拼接</button>
              </div>

              <template v-if="mode === 'direct'">
                <label class="field-label" for="direct-urls">下载链接（每行一个 HTTP/HTTPS URL）</label>
                <textarea id="direct-urls" v-model="directInput" class="direct-textarea" spellcheck="false" placeholder="https://example.com/file.zip"></textarea>
                <p class="field-help">{{ validDirectUrls.length }} 个有效链接 · {{ directUrls.length - validDirectUrls.length }} 行无效输入；加入队列时跳过无效行。</p>
              </template>
              <template v-else>
                <div class="rule-fields">
                  <label class="field-group"><span class="field-label">规则模板</span><select v-model="selectedRule"><option>Jenkins HPI</option><option>GitHub Release</option></select></label>
                  <label class="field-group base-field"><span class="field-label">基础网址</span><input v-model="baseUrl" type="url" spellcheck="false"></label>
                </div>
                <label class="field-label input-label" for="plugin-rows">插件名 + 版本（支持从表格粘贴）</label>
                <textarea id="plugin-rows" v-model="ruleInput" class="plugin-textarea" spellcheck="false"></textarea>
                <p class="field-help input-validation">{{ previewItems.length }} 行可生成 · {{ ruleRows.filter(row => !row.valid).length }} 行格式无效（每行需包含名称和版本）</p>
                <label class="field-label template-label" for="rule-template">生成规则</label>
                <input id="rule-template" v-model="template" class="template-input" spellcheck="false">
                <p class="field-help">可编辑模板变量，也可保存为自己的规则</p>
                <div class="source-actions"><button class="button secondary" type="button" @click="currentPage = 'rules'">＋ 添加规则</button><button class="text-button preview-link" type="button" @click="showPreview = true">预览 {{ previewItems.length }} 个 URL</button><button class="button primary" type="button" @click="addTasks">加入下载队列</button></div>
              </template>
              <div v-if="mode === 'direct'" class="source-actions direct-actions"><button class="button primary" type="button" @click="addTasks">加入下载队列</button></div>
            </article>

            <article class="panel destination-panel">
              <div class="panel-heading"><h2>保存位置</h2><button class="text-button" type="button" @click="chooseFolder">可更改</button></div>
              <label class="field-label" for="output-directory">下载到</label>
              <input id="output-directory" v-model="outputDir" class="directory-input" readonly>
              <button class="button secondary choose-button" type="button" @click="chooseFolder">选择文件夹…</button>
              <label class="field-label concurrency-label" for="concurrency">同时下载</label>
              <select id="concurrency" v-model.number="concurrency" class="full-select"><option v-for="n in 32" :key="n" :value="n">{{ n }} 个任务</option></select>
              <label class="field-label conflict-label" for="conflict-policy">文件已存在</label>
              <select id="conflict-policy" v-model="conflictPolicy" class="full-select"><option value="overwrite">覆盖</option><option value="rename">自动重命名</option><option value="skip">跳过</option><option value="ask">询问</option></select>
              <div class="stats-grid"><div><span>待下载</span><strong>{{ counts.waiting + tasks.filter(t => t.status === 'downloading').length }}</strong></div><div><span>完成</span><strong>{{ counts.completed }}</strong></div><div><span>失败</span><strong>{{ counts.failed }}</strong></div></div>
              <button class="drop-zone" type="button" @click="setNotice('拖放导入将在桌面版联调阶段接入')">也可以把 URL 文件拖到这里</button>
            </article>
          </section>

          <section class="panel queue-panel">
            <div class="queue-heading"><div><h2>下载队列 <span>当前批次 {{ tasks.length }} 项</span></h2></div><div class="queue-actions"><button class="text-button" type="button" @click="clearCompleted">清空已完成</button><button class="button secondary stop-all" type="button" @click="stopAll"><span class="stop-square">■</span> 全部停止</button></div></div>
            <div class="queue-table-wrap"><table class="queue-table"><thead><tr><th>文件 / 来源</th><th>状态</th><th>大小</th><th>操作</th></tr></thead><tbody>
              <tr v-for="task in tasks" :key="task.id"><td class="file-cell"><strong>{{ task.filename }}</strong><span>{{ task.source }}</span><div v-if="task.status === 'downloading'" class="progress-track"><span :style="{ width: `${task.progress}%` }"></span></div></td>
                <td><span class="status" :class="`status-${task.status}`"><i>{{ task.status === 'downloading' ? '↓' : task.status === 'waiting' ? '◷' : task.status === 'completed' ? '✓' : task.status === 'failed' ? '!' : task.status === 'skipped' ? '↷' : 'Ⅱ' }}</i>{{ task.status === 'downloading' ? `下载中 ${task.progress}%` : task.status === 'waiting' ? '等待中' : task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : task.status === 'skipped' ? '已跳过' : '已取消' }}</span></td>
                <td class="size-cell">{{ task.size }}</td><td class="actions-cell"><button v-if="task.status === 'downloading' || task.status === 'waiting'" type="button" @click="stopTask(task)">暂停</button><button v-else-if="task.status === 'failed' || task.status === 'cancelled'" type="button" @click="retryTask(task)">重试</button><button v-else type="button" @click="openDownloadFolder">打开位置</button><button v-if="task.status === 'waiting' || task.status === 'cancelled'" class="remove-action" type="button" @click="removeTask(task)">移除</button></td>
              </tr>
              <tr v-if="tasks.length === 0"><td colspan="4" class="empty-state">队列为空，可以从上方新建下载任务。</td></tr>
            </tbody></table></div>
            <div class="queue-footer"><span>下载中 {{ tasks.filter(t => t.status === 'downloading').length }}　·　等待中 {{ counts.waiting }}　·　已完成 {{ counts.completed }}</span><span>并发数 {{ concurrency }}　　网络超时 30 秒</span></div>
          </section>
          <div class="recent-logs"><span class="log-indicator"></span>近期活动：<span>{{ eventConnected ? '实时事件已连接' : '正在连接任务事件' }}</span><button type="button" :disabled="logsLoading" @click="loadLogs">{{ logsLoading ? '读取中…' : '查看日志' }}</button></div>
        </template>

        <template v-else-if="currentPage === 'history'">
          <section class="panel subpage-panel"><div class="subpage-toolbar"><div><h2>最近下载</h2><p>查看已完成、失败和取消的下载任务</p></div><button class="button secondary" type="button" @click="setNotice('历史记录已导出')">导出记录</button></div>
            <div class="history-list"><div v-for="task in tasks.filter(t => t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled')" :key="task.id" class="history-row"><span class="history-file-icon">↓</span><div class="history-main"><strong>{{ task.filename }}</strong><span>{{ task.source }}</span></div><span class="history-date">今天 14:32</span><span class="status" :class="`status-${task.status}`">{{ task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : '已取消' }}</span><button class="icon-button" type="button" aria-label="更多操作" @click="setNotice(`文件位置：${outputDir}`)">···</button></div>
              <div v-if="!tasks.some(t => ['completed', 'failed', 'cancelled'].includes(t.status))" class="empty-state">完成的任务会显示在这里。</div></div>
          </section>
        </template>

        <template v-else-if="currentPage === 'rules'">
          <section class="panel subpage-panel"><div class="subpage-toolbar"><div><h2>我的规则</h2><p>管理 URL 模板和默认文件名</p></div><button class="button primary" type="button" @click="setNotice('新规则编辑器将在规则功能阶段接入')">＋ 新建规则</button></div>
            <div class="rule-list"><article class="rule-card"><div class="rule-card-icon">J</div><div class="rule-card-content"><div class="rule-card-title"><strong>Jenkins HPI</strong><span class="builtin-tag">内置规则</span></div><p>下载 Jenkins 插件包及其指定版本。</p><code>{base_url}/{name}/{version}/{name}.hpi</code></div><button class="icon-button" type="button" aria-label="编辑 Jenkins HPI" @click="selectedRule = 'Jenkins HPI'; currentPage = 'workspace'">编辑</button></article>
              <article class="rule-card"><div class="rule-card-icon github-mark">GH</div><div class="rule-card-content"><div class="rule-card-title"><strong>GitHub Release</strong><span class="builtin-tag">内置规则</span></div><p>按仓库和版本拼接 Release 下载地址。</p><code>{base_url}/releases/download/{version}/{filename}</code></div><button class="icon-button" type="button" aria-label="编辑 GitHub Release" @click="selectedRule = 'GitHub Release'; currentPage = 'workspace'">编辑</button></article></div>
          </section>
        </template>

        <template v-else>
          <div class="settings-grid"><section class="panel settings-panel"><h2>下载设置</h2><label class="setting-row"><span><strong>默认下载目录</strong><small>{{ outputDir }}</small></span><button class="button secondary" type="button" @click="chooseFolder">更改</button></label><label class="setting-row"><span><strong>同时下载任务数</strong><small>范围 1–32，默认值为 4</small></span><select v-model.number="concurrency"><option v-for="n in 32" :key="n" :value="n">{{ n }}</option></select></label><label class="setting-row"><span><strong>文件冲突策略</strong><small>目标文件已存在时的默认操作</small></span><select v-model="conflictPolicy"><option value="overwrite">覆盖</option><option value="rename">自动重命名</option><option value="skip">跳过</option><option value="ask">询问</option></select></label></section>
            <section class="panel settings-panel"><h2>应用信息</h2><div class="about-row"><span>版本</span><strong>0.1.0 · 开发预览</strong></div><div class="about-row"><span>运行模式</span><strong>本地工作区</strong></div><div class="about-row"><span>服务状态</span><strong class="service-state"><i></i>就绪</strong></div></section></div>
        </template>
      </section>
    </div>
    <div v-if="showPreview" class="preview-backdrop" @click.self="showPreview = false">
      <section class="preview-dialog" role="dialog" aria-modal="true" aria-labelledby="preview-title">
        <div class="preview-dialog-heading"><div><h2 id="preview-title">URL 预览</h2><p>以下地址由当前规则模板生成</p></div><button type="button" aria-label="关闭预览" @click="showPreview = false">×</button></div>
        <div v-if="previewItems.length" class="preview-list"><article v-for="item in previewItems" :key="`${item.name}-${item.version}`"><div><strong>{{ item.name }}</strong><span>{{ item.version }}</span></div><code>{{ item.url }}</code></article></div>
        <div v-else class="preview-empty">输入至少一行名称和版本后即可预览。</div>
        <div class="preview-dialog-actions"><button class="button secondary" type="button" @click="showPreview = false">关闭</button><button class="button primary" type="button" @click="showPreview = false; addTasks()">加入下载队列</button></div>
      </section>
    </div>
    <div v-if="showLogs" class="preview-backdrop" @click.self="showLogs = false">
      <section class="preview-dialog log-dialog" role="dialog" aria-modal="true" aria-labelledby="logs-title">
        <div class="preview-dialog-heading"><div><h2 id="logs-title">应用日志</h2><p>最近 {{ logItems.length }} 条记录</p></div><button type="button" aria-label="关闭日志" @click="showLogs = false">×</button></div>
        <div v-if="logItems.length" class="preview-list log-list"><article v-for="(entry, index) in logItems" :key="`${entry.timestamp}-${index}`"><div><strong :class="`log-level-${entry.level.toLowerCase()}`">{{ entry.level }}</strong><span>{{ entry.timestamp }} · {{ entry.logger }}</span></div><code>{{ entry.message }}<template v-if="entry.filename"> · {{ entry.filename }}</template><template v-if="entry.status"> · {{ entry.status }}</template></code></article></div>
        <div v-else class="preview-empty">目前还没有日志记录。</div>
        <div class="preview-dialog-actions"><button class="button secondary" type="button" @click="showLogs = false">关闭</button><button class="button primary" type="button" @click="exportLogs">导出 JSONL</button></div>
      </section>
    </div>
    <Transition name="toast"><div v-if="notice" class="toast-message" role="status">{{ notice }}</div></Transition>
  </main>
</template>
