<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { connectTaskEvents, type ApiTask, type TaskEvent } from './api/taskEvents'
import { getRuntimeConfig, type NativeBridgeApi } from './api/runtime'

type PageId = 'workspace' | 'history' | 'rules' | 'settings'
type Mode = 'direct' | 'rule'
type TaskStatus = 'downloading' | 'waiting' | 'completed' | 'failed' | 'cancelled' | 'skipped' | 'waiting_user'
type DownloadTask = {
  id: number | string
  filename: string
  source: string
  status: TaskStatus
  progress: number
  size: string
  createdAt?: string
}
type LogEntry = { timestamp: string; level: string; logger: string; message: string; filename?: string; status?: string }
type Rule = { id: string; name: string; base_url: string; url_template: string; filename_template: string; default_ext: string; builtin: boolean }
type Settings = { output_dir: string; subdir: string; concurrency: number; max_retries: number; conflict_policy: string; current_mode: Mode }

const currentPage = ref<PageId>('workspace')
const mode = ref<Mode>('rule')
const outputDir = ref('')
const subdir = ref('')
const concurrency = ref(4)
const maxRetries = ref(3)
const conflictPolicy = ref('ask')
const selectedRuleId = ref('builtin:jenkins-hpi')
const baseUrl = ref('')
const ruleInput = ref('')
const directInput = ref('')
const ruleCatalog = ref<Rule[]>([])
const historyTasks = ref<DownloadTask[]>([])
const ruleDraft = ref<Rule>({ id: '', name: '', base_url: '', url_template: '{base_url}/{name}/{version}/{filename}.{ext}', filename_template: '{filename}.{ext}', default_ext: '', builtin: false })
const editingRule = ref(false)
const previewItems = ref<Array<{ line_number: number; name: string; version: string; url: string; filename: string; valid: boolean; error: string | null }>>([])
const previewLoading = ref(false)
const settingsDirty = ref(false)
const notice = ref('')
const showPreview = ref(false)
const eventConnected = ref(false)
const showLogs = ref(false)
const logsLoading = ref(false)
const logItems = ref<LogEntry[]>([])
let disconnectTaskEvents: (() => void) | undefined
let taskEventsDisposed = false

const tasks = ref<DownloadTask[]>([])

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** unit).toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function mapTask(task: ApiTask): DownloadTask {
  const status: TaskStatus = task.status === 'downloading' ? 'downloading'
    : task.status === 'waiting_user' ? 'waiting_user'
      : task.status === 'completed' ? 'completed'
      : task.status === 'failed' ? 'failed'
        : task.status === 'cancelled' ? 'cancelled'
          : task.status === 'skipped' ? 'skipped' : 'waiting'
  let source = '直接 URL'
  try {
    source = task.source_type === 'rule' ? `规则 · ${ruleCatalog.value.find((rule) => rule.id === task.rule_id)?.name ?? task.rule_id ?? ''}` : `直接 URL · ${new URL(task.url).host}`
  } catch { /* Keep a generic source label for malformed historical data. */ }
  return { id: task.id, filename: task.filename, source, status,
    progress: task.progress ?? 0, size: task.bytes_total === null ? formatBytes(task.bytes_downloaded) : formatBytes(task.bytes_total),
    createdAt: (task as ApiTask & { created_at?: string }).created_at }
}

function applyTaskEvent(event: TaskEvent) {
  if (!event.data || typeof event.data !== 'object' || !('id' in event.data)) return
  const task = mapTask(event.data as ApiTask)
  const index = tasks.value.findIndex((item) => item.id === task.id)
  if (index < 0) tasks.value.unshift(task)
  else tasks.value[index] = task
}

function applyCreatedTask(task: ApiTask) {
  // A fast download can finish over WebSocket before the creation POST returns.
  // Keep the newer event state instead of regressing it to the stale pending DTO.
  if (tasks.value.some((item) => item.id === task.id)) return
  applyTaskEvent({ type: 'task.created', data: task, occurred_at: null })
}

onMounted(() => {
  void loadSettings()
  void loadRules()
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
const selectedRule = computed(() => ruleCatalog.value.find((rule) => rule.id === selectedRuleId.value))
const ruleLineCount = computed(() => ruleInput.value.split(/\r?\n/).filter((line) => line.trim()).length)
const directUrls = computed(() => directInput.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean))
const validDirectUrls = computed(() => directUrls.value.filter((url) => /^https?:\/\//i.test(url)))
const structurallyValidRuleLines = computed(() => ruleInput.value.split(/\r?\n/).filter((line) => line.trim()).filter((line) => {
  const columns = line.trim().split(/\s+/)
  return columns.length >= 2 && columns.length <= 4
}).length)

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const config = await getRuntimeConfig()
  const headers = new Headers(init.headers)
  if (config.sessionToken) headers.set('X-Session-Token', config.sessionToken)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(new URL(path, config.apiBaseUrl), { ...init, headers })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { message = (await response.json()).detail ?? message } catch { /* Keep HTTP status text. */ }
    throw new Error(message)
  }
  return await response.json() as T
}

async function loadSettings() {
  try {
    const settings = await apiRequest<Settings & { updated_at: string }>('/api/v1/settings')
    outputDir.value = settings.output_dir
    subdir.value = settings.subdir
    concurrency.value = settings.concurrency
    maxRetries.value = settings.max_retries
    conflictPolicy.value = settings.conflict_policy
    mode.value = settings.current_mode
    settingsDirty.value = false
  } catch { setNotice('无法读取下载设置') }
}

async function saveSettings() {
  try {
    await apiRequest('/api/v1/settings', { method: 'PUT', body: JSON.stringify({
      output_dir: outputDir.value, subdir: subdir.value, concurrency: concurrency.value,
      max_retries: maxRetries.value, conflict_policy: conflictPolicy.value, current_mode: mode.value,
    }) })
    settingsDirty.value = false
    setNotice('设置已保存')
    return true
  } catch (error) { setNotice(`保存设置失败：${error instanceof Error ? error.message : '服务错误'}`); return false }
}

async function loadRules() {
  try {
    const result = await apiRequest<{ items: Rule[] }>('/api/v1/rules')
    ruleCatalog.value = result.items
    if (!ruleCatalog.value.some((rule) => rule.id === selectedRuleId.value)) selectedRuleId.value = ruleCatalog.value[0]?.id ?? ''
  } catch { setNotice('无法读取 URL 规则') }
}

async function loadHistory() {
  try {
    const result = await apiRequest<{ items: ApiTask[] }>('/api/v1/tasks/history?limit=500')
    historyTasks.value = result.items.map(mapTask)
  } catch { setNotice('无法读取下载历史') }
}

watch(currentPage, (page) => {
  if (page === 'history') void loadHistory()
})

watch(selectedRule, (rule) => { baseUrl.value = rule?.base_url ?? '' }, { immediate: true })

watch([outputDir, subdir, concurrency, maxRetries, conflictPolicy, mode], () => { settingsDirty.value = true })

function nativeApi(): NativeBridgeApi | undefined {
  const api = window.pywebview?.api
  return api && typeof api.get_runtime_config === 'function' ? api : undefined
}

function setNotice(message: string) {
  notice.value = message
  window.setTimeout(() => { if (notice.value === message) notice.value = '' }, 2600)
}

async function addTasks() {
  if (settingsDirty.value && !await saveSettings()) return
  try {
    const path = mode.value === 'direct' ? '/api/v1/tasks/direct' : '/api/v1/tasks/from-rule'
    const body = mode.value === 'direct'
      ? { urls: directInput.value, output_dir: outputDir.value, subdir: subdir.value }
      : { rule_id: selectedRuleId.value, inputs: ruleInput.value, base_url: baseUrl.value, output_dir: outputDir.value, subdir: subdir.value }
    const result = await apiRequest<{ created: ApiTask[]; errors: Array<{ line: number }> }>(path, { method: 'POST', body: JSON.stringify(body) })
    result.created.forEach(applyCreatedTask)
    setNotice(`已加入 ${result.created.length} 个任务${result.errors.length ? `，${result.errors.length} 行无效` : ''}`)
  } catch (error) { setNotice(`创建任务失败：${error instanceof Error ? error.message : '服务错误'}`) }
}

async function previewRule() {
  if (!selectedRuleId.value) { setNotice('请先选择规则'); return }
  previewLoading.value = true
  try {
    const result = await apiRequest<{ items: typeof previewItems.value }>(`/api/v1/rules/${encodeURIComponent(selectedRuleId.value)}/preview`, { method: 'POST', body: JSON.stringify({ inputs: ruleInput.value, base_url: baseUrl.value }) })
    previewItems.value = result.items
    showPreview.value = true
  } catch (error) { setNotice(`预览失败：${error instanceof Error ? error.message : '服务错误'}`) }
  finally { previewLoading.value = false }
}

function newRule() {
  ruleDraft.value = { id: '', name: '', base_url: '', url_template: '{base_url}/{name}/{version}/{filename}.{ext}', filename_template: '{filename}.{ext}', default_ext: '', builtin: false }
  editingRule.value = true
}

function editRule(rule: Rule) {
  if (rule.builtin) { selectedRuleId.value = rule.id; currentPage.value = 'workspace'; mode.value = 'rule'; return }
  ruleDraft.value = { ...rule }
  editingRule.value = true
}

async function saveRule() {
  const { id, name, base_url, url_template, filename_template, default_ext } = ruleDraft.value
  try {
    const saved = await apiRequest<Rule>(id ? `/api/v1/rules/${encodeURIComponent(id)}` : '/api/v1/rules', {
      method: id ? 'PUT' : 'POST', body: JSON.stringify({ name, base_url, url_template, filename_template, default_ext }),
    })
    await loadRules()
    selectedRuleId.value = saved.id
    editingRule.value = false
    setNotice('规则已保存')
  } catch (error) { setNotice(`保存规则失败：${error instanceof Error ? error.message : '服务错误'}`) }
}

async function deleteRule(rule: Rule) {
  if (rule.builtin) return
  try {
    await apiRequest(`/api/v1/rules/${encodeURIComponent(rule.id)}`, { method: 'DELETE' })
    if (selectedRuleId.value === rule.id) selectedRuleId.value = ''
    await loadRules()
    setNotice('规则已删除')
  } catch (error) { setNotice(`删除规则失败：${error instanceof Error ? error.message : '服务错误'}`) }
}

async function stopTask(task: DownloadTask) {
  try {
    await apiRequest(`/api/v1/tasks/${encodeURIComponent(task.id)}/cancel`, { method: 'POST' })
    setNotice(`已停止 ${task.filename}`)
  } catch (error) { setNotice(`无法停止 ${task.filename}：${error instanceof Error ? error.message : '服务错误'}`) }
}

async function retryTask(task: DownloadTask) {
  try {
    await apiRequest(`/api/v1/tasks/${encodeURIComponent(task.id)}/retry`, { method: 'POST' })
    setNotice(`已重新加入 ${task.filename}`)
  } catch (error) { setNotice(`无法重试 ${task.filename}：${error instanceof Error ? error.message : '服务错误'}`) }
}

async function resolveConflict(task: DownloadTask) {
  const choice = window.prompt('目标文件已存在，请输入 overwrite（覆盖）、rename（改名）或 skip（跳过）', 'rename')
  if (!choice || !['overwrite', 'rename', 'skip'].includes(choice)) return
  try {
    await apiRequest(`/api/v1/tasks/${encodeURIComponent(task.id)}/conflict-resolution`, { method: 'POST', body: JSON.stringify({ resolution: choice }) })
  } catch (error) { setNotice(`处理文件冲突失败：${error instanceof Error ? error.message : '服务错误'}`) }
}

function removeTask(task: DownloadTask) {
  tasks.value = tasks.value.filter((item) => item.id !== task.id)
}

async function clearCompleted() {
  try {
    const result = await apiRequest<{ cleared: number }>('/api/v1/tasks/clear-completed', { method: 'POST' })
    tasks.value = tasks.value.filter((task) => task.status !== 'completed')
    setNotice(`已从队列清除 ${result.cleared} 个任务，历史记录仍保留`)
  } catch { setNotice('无法清除已完成任务') }
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
      <div class="brand"><span class="brand-arrow">↓</span><strong>URL下载器</strong><span class="brand-divider">|</span><span class="brand-context">工作台</span></div>
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
        <div class="saved-rules"><button v-for="rule in ruleCatalog.slice(0, 4)" :key="rule.id" type="button" @click="selectedRuleId = rule.id; mode = 'rule'; currentPage = 'workspace'"><span>◇</span>{{ rule.name }}</button></div>
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
                  <label class="field-group"><span class="field-label">规则模板</span><select v-model="selectedRuleId"><option v-for="rule in ruleCatalog" :key="rule.id" :value="rule.id">{{ rule.name }}</option></select></label>
                  <label class="field-group base-field"><span class="field-label">基础网址</span><input v-model="baseUrl" type="url" spellcheck="false" placeholder="https://example.com/download"></label>
                </div>
                <label class="field-label input-label" for="plugin-rows">插件名 + 版本（支持从表格粘贴）</label>
                <textarea id="plugin-rows" v-model="ruleInput" class="plugin-textarea" spellcheck="false"></textarea>
                <p class="field-help input-validation">{{ structurallyValidRuleLines }} 行格式可解析 · {{ ruleLineCount - structurallyValidRuleLines }} 行格式无效（每行需包含名称和版本）</p>
                <label class="field-label template-label" for="rule-template">生成规则</label>
                <input id="rule-template" :value="selectedRule?.url_template ?? ''" class="template-input" readonly spellcheck="false">
                <p class="field-help">规则由 URL 规则页面管理，预览和下载共用服务端模板</p>
                <div class="source-actions"><button class="button secondary" type="button" @click="currentPage = 'rules'; newRule()">＋ 添加规则</button><button class="text-button preview-link" type="button" :disabled="previewLoading" @click="previewRule">{{ previewLoading ? '预览中…' : '预览 URL' }}</button><button class="button primary" type="button" @click="addTasks">加入下载队列</button></div>
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
                <td><span class="status" :class="`status-${task.status}`"><i>{{ task.status === 'downloading' ? '↓' : task.status === 'waiting' || task.status === 'waiting_user' ? '◷' : task.status === 'completed' ? '✓' : task.status === 'failed' ? '!' : task.status === 'skipped' ? '↷' : 'Ⅱ' }}</i>{{ task.status === 'downloading' ? `下载中 ${task.progress}%` : task.status === 'waiting' ? '等待中' : task.status === 'waiting_user' ? '等待冲突处理' : task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : task.status === 'skipped' ? '已跳过' : '已取消' }}</span></td>
                <td class="size-cell">{{ task.size }}</td><td class="actions-cell"><button v-if="task.status === 'downloading' || task.status === 'waiting'" type="button" @click="stopTask(task)">暂停</button><button v-else-if="task.status === 'waiting_user'" type="button" @click="resolveConflict(task)">处理冲突</button><button v-else-if="task.status === 'failed' || task.status === 'cancelled'" type="button" @click="retryTask(task)">重试</button><button v-else type="button" @click="openDownloadFolder">打开位置</button><button v-if="task.status === 'waiting' || task.status === 'cancelled'" class="remove-action" type="button" @click="removeTask(task)">移除</button></td>
              </tr>
              <tr v-if="tasks.length === 0"><td colspan="4" class="empty-state">队列为空，可以从上方新建下载任务。</td></tr>
            </tbody></table></div>
            <div class="queue-footer"><span>下载中 {{ tasks.filter(t => t.status === 'downloading').length }}　·　等待中 {{ counts.waiting }}　·　已完成 {{ counts.completed }}</span><span>并发数 {{ concurrency }}　　网络超时 30 秒</span></div>
          </section>
          <div class="recent-logs"><span class="log-indicator"></span>近期活动：<span>{{ eventConnected ? '实时事件已连接' : '正在连接任务事件' }}</span><button type="button" :disabled="logsLoading" @click="loadLogs">{{ logsLoading ? '读取中…' : '查看日志' }}</button></div>
        </template>

        <template v-else-if="currentPage === 'history'">
          <section class="panel subpage-panel"><div class="subpage-toolbar"><div><h2>最近下载</h2><p>查看已完成、失败、跳过和取消的下载任务</p></div><button class="button secondary" type="button" @click="loadHistory">刷新</button></div>
            <div class="history-list"><div v-for="task in historyTasks" :key="task.id" class="history-row"><span class="history-file-icon">↓</span><div class="history-main"><strong>{{ task.filename }}</strong><span>{{ task.source }}</span></div><span class="history-date">{{ task.createdAt ? new Date(task.createdAt).toLocaleString() : '—' }}</span><span class="status" :class="`status-${task.status}`">{{ task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : task.status === 'skipped' ? '已跳过' : '已取消' }}</span></div>
              <div v-if="!historyTasks.length" class="empty-state">完成的任务会显示在这里。</div></div>
          </section>
        </template>

        <template v-else-if="currentPage === 'rules'">
          <section class="panel subpage-panel"><div class="subpage-toolbar"><div><h2>我的规则</h2><p>管理 URL 模板和默认文件名</p></div><button class="button primary" type="button" @click="newRule">＋ 新建规则</button></div>
            <div v-if="editingRule" class="rule-editor"><label class="field-group"><span class="field-label">规则名称</span><input v-model="ruleDraft.name" maxlength="128"></label><label class="field-group"><span class="field-label">基础网址</span><input v-model="ruleDraft.base_url" maxlength="2048"></label><label class="field-group"><span class="field-label">URL 模板</span><input v-model="ruleDraft.url_template" maxlength="2048"></label><label class="field-group"><span class="field-label">文件名模板</span><input v-model="ruleDraft.filename_template" maxlength="255"></label><label class="field-group"><span class="field-label">默认扩展名</span><input v-model="ruleDraft.default_ext" maxlength="32"></label><div class="source-actions"><button class="button secondary" type="button" @click="editingRule = false">取消</button><button class="button primary" type="button" @click="saveRule">保存规则</button></div></div>
            <div class="rule-list"><article v-for="rule in ruleCatalog" :key="rule.id" class="rule-card"><div class="rule-card-icon">{{ rule.name.slice(0, 1).toUpperCase() }}</div><div class="rule-card-content"><div class="rule-card-title"><strong>{{ rule.name }}</strong><span v-if="rule.builtin" class="builtin-tag">内置规则</span></div><p>默认扩展名：{{ rule.default_ext || '未指定' }}</p><code>{{ rule.url_template }}</code></div><button class="icon-button" type="button" @click="editRule(rule)">{{ rule.builtin ? '使用' : '编辑' }}</button><button v-if="!rule.builtin" class="icon-button" type="button" @click="deleteRule(rule)">删除</button></article><div v-if="!ruleCatalog.length" class="empty-state">没有可用规则。</div></div>
          </section>
        </template>

        <template v-else>
          <div class="settings-grid"><section class="panel settings-panel"><h2>下载设置</h2><label class="setting-row"><span><strong>默认下载目录</strong><small>{{ outputDir || '未加载' }}</small></span><button class="button secondary" type="button" @click="chooseFolder">更改</button></label><label class="setting-row"><span><strong>默认子目录</strong><small>可留空</small></span><input v-model="subdir" placeholder="例如 plugins"></label><label class="setting-row"><span><strong>同时下载任务数</strong><small>范围 1–32，默认值为 4</small></span><select v-model.number="concurrency"><option v-for="n in 32" :key="n" :value="n">{{ n }}</option></select></label><label class="setting-row"><span><strong>自动重试次数</strong><small>网络错误时重试</small></span><input v-model.number="maxRetries" type="number" min="0"></label><label class="setting-row"><span><strong>文件冲突策略</strong><small>目标文件已存在时的默认操作</small></span><select v-model="conflictPolicy"><option value="overwrite">覆盖</option><option value="rename">自动重命名</option><option value="skip">跳过</option><option value="ask">询问</option></select></label><button class="button primary" type="button" :disabled="!settingsDirty" @click="saveSettings">保存设置</button></section>
            <section class="panel settings-panel"><h2>应用信息</h2><div class="about-row"><span>版本</span><strong>0.1.0 · 开发预览</strong></div><div class="about-row"><span>运行模式</span><strong>本地工作区</strong></div><div class="about-row"><span>服务状态</span><strong class="service-state"><i></i>{{ eventConnected ? '已连接' : '连接中' }}</strong></div></section></div>
        </template>
      </section>
    </div>
    <div v-if="showPreview" class="preview-backdrop" @click.self="showPreview = false">
      <section class="preview-dialog" role="dialog" aria-modal="true" aria-labelledby="preview-title">
        <div class="preview-dialog-heading"><div><h2 id="preview-title">URL 预览</h2><p>以下地址由当前规则模板生成</p></div><button type="button" aria-label="关闭预览" @click="showPreview = false">×</button></div>
        <div v-if="previewItems.length" class="preview-list"><article v-for="item in previewItems" :key="item.line_number"><div><strong>{{ item.filename || `第 ${item.line_number} 行` }}</strong><span>{{ item.valid ? `${item.name} ${item.version}` : '无效输入' }}</span></div><code>{{ item.valid ? item.url : item.error }}</code></article></div>
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
