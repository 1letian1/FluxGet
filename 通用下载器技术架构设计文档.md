# 通用下载器技术架构说明（AI开发版）

> 目标：提供给 AI 作为开发上下文。  
> 平台：Windows 10 / Windows 11  
> 最终交付：可直接运行的 Windows EXE，用户无需安装 Python / Node.js。  
> UI：必须按参考图 1:1 复刻，并兼顾不同窗口尺寸和 Windows DPI。  
> 推荐技术栈：Vue 3 + TypeScript + pywebview + FastAPI + asyncio/httpx + SQLite + PyInstaller。

---

## 1. 产品目标

开发一个 Windows 桌面下载器，支持：

- 单条 / 多条 HTTP、HTTPS URL 下载；
- Jenkins HPI 等规则批量生成下载地址；
- 用户新增、编辑、删除自定义规则；
- 下载队列、实时进度、并发控制；
- 断点续传；
- 下载失败自动重试；
- 用户取消、失败任务重试；
- 文件冲突处理；
- 下载历史；
- 设置持久化；
- 日志查看和导出；
- 最终打包成 Windows EXE；
- 未来可接入 AI，用于规则生成、错误分析、下载列表解析。

---

## 2. 核心技术方案

```text
Vue 3 + TypeScript + Vite
        ↓
pywebview Windows 桌面壳
        ↓
FastAPI + Uvicorn
        ↓
DownloadManager / RuleEngine
        ↓
asyncio + httpx + aiofiles
        ↓
SQLite
        ↓
PyInstaller
        ↓
UniversalDownloader.exe
```

### 技术选型

| 模块 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite |
| 状态管理 | Pinia |
| 样式 | 自定义 CSS / SCSS |
| Windows 桌面壳 | pywebview |
| 本地 API | FastAPI |
| ASGI | Uvicorn |
| 下载 | httpx.AsyncClient |
| 异步文件写入 | aiofiles |
| 数据库 | SQLite + aiosqlite |
| 实时进度 | WebSocket |
| EXE 打包 | PyInstaller |
| 测试 | pytest + Playwright |

不要优先使用 Electron、Tauri 或大型 UI 组件库。

---

## 3. 总体架构

```text
UniversalDownloader.exe
│
├── pywebview
│   └── Vue 3 UI
│
└── Backend Thread
    └── asyncio event loop
        ├── FastAPI / Uvicorn
        ├── DownloadManager
        ├── RuleEngine
        ├── WebSocket
        └── SQLite
```

FastAPI 只监听：

```text
127.0.0.1:<随机端口>
```

程序启动流程：

```text
EXE 启动
→ 初始化日志和 SQLite
→ 启动 FastAPI
→ 等待 /api/v1/health 正常
→ 启动 pywebview
→ 加载本地 Vue 页面
```

---

## 4. 前端要求

### 4.1 UI

必须按参考图 1:1 复刻，包括：

- 深色工作台；
- 自定义标题栏；
- 左侧导航；
- 下载来源卡片；
- 保存位置卡片；
- 下载队列表格；
- 状态、进度条、按钮、输入框；
- 字体、颜色、边框、圆角、间距。

建议使用自定义 CSS，不依赖 Element Plus 等组件库默认视觉。

### 4.2 页面

```text
App
├── TitleBar
├── Sidebar
│   ├── 任务工作台
│   ├── 下载历史
│   ├── URL规则
│   └── 偏好设置
└── Workspace
    ├── DownloadSource
    ├── SaveLocation
    └── DownloadQueue
```

### 4.3 响应式

至少适配：

```text
1024×768
1124×1068（参考图）
1366×768
1440×900
1920×1080
```

Windows DPI：

```text
100%
125%
150%
```

中文字体优先：

```css
"Microsoft YaHei UI",
"Microsoft YaHei",
"Segoe UI",
sans-serif
```

---

## 5. 桌面能力

pywebview 使用无边框窗口，由 Vue 绘制标题栏。

需要提供 Native Bridge：

```text
选择文件夹
打开目录
最小化
最大化 / 还原
关闭窗口
拖动标题栏
```

“选择文件夹”必须调用 Windows 原生文件夹选择器，而不是浏览器文件选择。

---

## 6. 下载架构

不要在 FastAPI Router 中直接执行下载。

结构：

```text
FastAPI Router
    ↓
TaskService
    ↓
DownloadManager
    ├── Queue
    ├── Scheduler
    ├── Worker
    ├── RetryPolicy
    ├── ResumeManager
    ├── ConflictManager
    └── EventBus
```

创建任务时：

```text
API 接收请求
→ 校验 URL
→ 创建 DownloadTask
→ 保存 SQLite
→ 加入下载队列
→ 立即返回
```

真正下载由 DownloadManager 异步执行。

---

## 7. DownloadTask

建议字段：

```python
class DownloadTask:
    id: UUID
    url: str
    filename: str
    output_dir: str
    temp_path: str
    source_type: Literal["direct", "rule"]

    status: Literal[
        "pending",
        "downloading",
        "waiting_user",
        "completed",
        "failed",
        "cancelled",
    ]

    bytes_total: int | None
    bytes_downloaded: int
    retry_count: int
    max_retries: int
    error_code: str | None
    error_message: str | None
```

任务状态必须持久化，程序重启后可恢复。

---

## 8. 并发下载

并发范围：

```text
1 ～ 32
```

默认：

```text
4
```

使用：

```python
asyncio.Semaphore(concurrency)
```

不要为每个任务创建独立线程或进程。

---

## 9. 断点续传

未完成文件统一使用：

```text
filename.ext.part
```

如果 `.part` 已存在：

```http
Range: bytes=<已下载字节数>-
```

服务端返回：

```text
206 → 继续追加
200 → 服务端不支持 Range，重新从 0 下载并提示用户
```

完成后：

```python
os.replace(temp_path, final_path)
```

即：

```text
网络 → .part → 完成 → 原子替换正式文件
```

---

## 10. 重试与取消

### 自动重试

适用于：

```text
连接中断
超时
500 / 502 / 503 / 504
```

默认最多：

```text
3 次
```

退避：

```text
1 秒 → 2 秒 → 4 秒
```

### 不自动重试

```text
用户主动取消
普通 4xx
非法路径
文件冲突等待用户处理
```

取消后保留 `.part`，状态设为 `cancelled`，不自动重试。

---

## 11. 文件冲突

支持：

```python
ConflictPolicy = Literal[
    "overwrite",
    "rename",
    "skip",
    "ask",
]
```

`ask` 模式：

```text
发现文件已存在
→ task.status = waiting_user
→ WebSocket 通知前端
→ 用户选择覆盖 / 重命名 / 跳过
→ API 提交处理结果
→ 继续任务
```

不能阻塞其他下载任务。

---

## 12. 路径安全

必须统一经过 `PathService`：

```python
safe_filename()
safe_subdir()
resolve_output_path()
```

禁止路径穿越，例如：

```text
../../Windows/System32
..\..\xxx
```

所有最终输出路径必须确认仍位于用户选择的下载根目录内。

同时处理 Windows 保留文件名：

```text
CON
PRN
AUX
NUL
COM1...
LPT1...
```

---

## 13. 规则引擎

规则逻辑与下载逻辑完全分离。

```text
RuleEngine
├── Jenkins HPI
└── Custom Rules
```

规则字段：

```python
class DownloadRule:
    id: str
    name: str
    base_url: str
    url_template: str
    filename_template: str
    default_ext: str
    builtin: bool
```

支持变量：

```text
{base_url}
{name}
{version}
{filename}
{ext}
```

Jenkins HPI 默认模板：

```text
{base_url}/{name}/{version}/{name}.hpi
```

规则处理：

```text
输入
→ Parser
→ Renderer
→ URL Validator
→ Preview
→ TaskFactory
```

**URL 预览和真正创建任务必须使用同一个 Renderer。**

---

## 14. FastAPI API

统一前缀：

```text
/api/v1
```

建议接口：

```http
GET    /api/v1/health

GET    /api/v1/tasks
POST   /api/v1/tasks/direct
POST   /api/v1/tasks/from-rule
POST   /api/v1/tasks/{id}/cancel
POST   /api/v1/tasks/{id}/retry
POST   /api/v1/tasks/{id}/conflict-resolution
POST   /api/v1/tasks/retry-failed
POST   /api/v1/tasks/clear-completed

GET    /api/v1/rules
POST   /api/v1/rules
PUT    /api/v1/rules/{id}
DELETE /api/v1/rules/{id}
POST   /api/v1/rules/{id}/preview

GET    /api/v1/settings
PUT    /api/v1/settings

GET    /api/v1/history
GET    /api/v1/logs
POST   /api/v1/logs/export
```

---

## 15. WebSocket

地址：

```text
/ws/events
```

推荐事件：

```text
task.created
task.started
task.progress
task.retrying
task.waiting_user
task.completed
task.failed
task.cancelled
```

进度示例：

```json
{
  "type": "task.progress",
  "data": {
    "task_id": "uuid",
    "downloaded": 12345678,
    "total": 45678900,
    "percent": 27.03,
    "speed": 1820000
  }
}
```

进度更新频率控制在：

```text
4 ～ 10 次 / 秒
```

不要使用高频 HTTP 轮询。

---

## 16. SQLite

数据目录：

```text
%LOCALAPPDATA%\\UniversalDownloader\\
├── downloader.db
├── logs\\
└── cache\\
```

主要保存：

```text
settings
rules
tasks / history
```

关键设置：

```text
output_dir
concurrency
max_retries
conflict_policy
current_mode
```

程序启动时可将异常退出遗留的：

```text
downloading → pending
```

如果 `.part` 存在，则继续断点续传。

---

## 17. 日志

记录：

```text
应用启动 / 关闭
任务创建
开始
完成
失败
取消
重试
文件冲突
断点续传
规则错误
数据库异常
```

建议使用 `RotatingFileHandler`，例如：

```text
5 MB / 文件
保留 5 个历史文件
```

UI 支持查看近期日志和导出日志。

---

## 18. 程序安全关闭

关闭窗口时不要直接 `sys.exit()`。

流程：

```text
停止接收新任务
→ 停止 / 取消 Worker
→ 关闭 HTTP Response
→ 保留 .part
→ 保存 SQLite
→ 关闭 httpx
→ 关闭 WebSocket
→ 停止 Uvicorn
→ 等待 Backend Thread
→ 销毁窗口
→ 退出
```

---

## 19. 本地 API 安全

FastAPI 只监听：

```text
127.0.0.1
```

推荐：

- 随机端口；
- 启动时生成随机 Session Token；
- 前端 API 请求携带 Token；
- 不允许任意 CORS；
- 不允许局域网访问。

---

## 20. EXE 打包

第一版使用：

```text
PyInstaller
```

最终：

```text
UniversalDownloader.exe
```

用户无需安装：

```text
Python
Node.js
npm
```

建议同时产出：

```text
UniversalDownloader.exe
UniversalDownloader-portable/
```

正式发布可增加 Windows Code Signing。

---

## 21. AI 扩展

AI 作为独立服务：

```text
AIService
```

未来接口：

```http
POST /api/v1/ai/generate-rule
POST /api/v1/ai/analyze-error
POST /api/v1/ai/parse-download-list
```

AI 结果仍必须经过：

```text
AI
→ RuleEngine / Parser
→ URL Validator
→ TaskFactory
→ DownloadManager
```

AI 不能绕过路径安全、URL 校验和下载引擎。

Provider 可预留：

```text
OpenAI
Azure OpenAI
Ollama
其他 OpenAI-compatible API
```

---

## 22. 推荐目录

```text
universal-downloader/
├── frontend/
│   └── src/
│       ├── api/
│       ├── components/
│       ├── pages/
│       ├── stores/
│       └── styles/
│
├── backend/
│   ├── api/
│   ├── core/
│   ├── download/
│   ├── rules/
│   ├── models/
│   ├── persistence/
│   └── ai/
│
├── desktop/
│   ├── window.py
│   ├── bridge.py
│   └── lifecycle.py
│
├── tests/
├── main.py
├── pyproject.toml
└── UniversalDownloader.spec
```

---

## 23. 开发顺序

### Phase 1：UI

先完成 Vue 静态界面 1:1 复刻。

### Phase 2：桌面壳与 API

完成：

```text
pywebview
FastAPI
文件夹选择
设置持久化
规则 CRUD
```

### Phase 3：下载引擎

完成：

```text
DownloadManager
并发
Range
.part
取消
重试
冲突
WebSocket
```

### Phase 4：完整桌面能力

完成：

```text
SQLite
历史
日志
程序恢复
安全退出
```

### Phase 5：发布

完成：

```text
PyInstaller
Win10 / Win11
DPI 测试
代码签名
```

AI 功能放在核心下载器稳定后再开发。

---

## 24. 测试重点

下载测试至少覆盖：

```text
正常 200
支持 Range 的 206
不支持 Range
中途断开
500 后恢复
404
慢速下载
取消
文件冲突
```

UI 使用 Playwright 做截图对比：

```text
reference.png
current.png
diff.png
```

以参考图为主要像素级验收基准。

---

## 25. AI 开发时必须遵守的原则

1. 不要将所有逻辑写进 `main.py`。
2. FastAPI Router 不直接执行下载。
3. 下载逻辑集中在 `DownloadManager`。
4. URL 规则集中在 `RuleEngine`。
5. 下载进度通过 EventBus + WebSocket 推送。
6. 所有下载先写 `.part`，完成后再替换正式文件。
7. 用户取消任务不能自动重试。
8. 任何外部文件名和路径必须经过安全校验。
9. UI 必须按参考图 1:1 复刻，不随意改视觉风格。
10. URL 预览和实际下载必须共用同一套 Renderer。
11. 永久数据放在 `%LOCALAPPDATA%\\UniversalDownloader`。
12. FastAPI 仅监听 `127.0.0.1`。
13. AI 不能绕过核心安全和下载流程。
14. 最终程序必须可在未安装 Python 的 Windows 环境运行。

---

## 26. 最终方案

```text
Vue 3 + TypeScript + Vite + Pinia
              +
           pywebview
              +
     FastAPI + Uvicorn
              +
asyncio + httpx + aiofiles
              +
       SQLite + aiosqlite
              +
           WebSocket
              +
          PyInstaller
              ↓
   UniversalDownloader.exe
```

核心原则：

> UI、API、下载引擎、规则引擎、数据持久化、AI 能力保持解耦。

开发优先级：

> 先完成 UI 1:1 复刻，再完成下载核心，最后考虑 AI。
