# Universal Downloader 后续 AI 开发全流程

> 用途：作为 Coding AI / AI 开发助手的长期项目上下文与执行规范。  
> 项目：Universal Downloader（通用下载器）  
> 平台：Windows 10 / Windows 11  
> 依据：
> - `通用下载器需求.md`
> - `通用下载器技术架构设计文档.md`
> - UI 参考图（视觉实现时以参考图为最高优先级）

---

## 1. 项目目标

开发一款 Windows 桌面通用下载器，最终交付为可直接运行的 Windows 程序。

核心能力包括：

- 单条 / 多条 HTTP、HTTPS URL 下载；
- 内置 Jenkins HPI 规则；
- 用户自定义规则；
- URL 批量生成；
- 下载队列；
- 实时进度；
- 并发下载；
- 断点续传；
- 自动重试；
- 手动取消；
- 文件冲突处理；
- 下载历史；
- 设置持久化；
- 日志查看与导出；
- 程序异常退出后的任务恢复；
- Windows EXE 打包；
- 后续扩展 AI 规则生成、错误分析、下载列表解析。

最终用户无需安装：

- Python
- Node.js
- npm

即可运行程序。

---

# 2. 固定技术栈

除非明确批准，不得擅自更换技术栈。

```text
Frontend
Vue 3
TypeScript
Vite
Pinia
自定义 CSS / SCSS

Desktop
pywebview

Backend
FastAPI
Uvicorn

Download
asyncio
httpx.AsyncClient
aiofiles

Database
SQLite
aiosqlite

Realtime
WebSocket

Testing
pytest
Playwright

Packaging
PyInstaller
```

整体结构：

```text
Vue 3 + TypeScript + Vite
            ↓
        pywebview
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

---

# 3. 核心架构原则

必须始终保持以下模块解耦：

```text
UI
API
DownloadManager
RuleEngine
Persistence
Desktop Bridge
AIService
```

不得把所有逻辑集中在 `main.py`。

正确关系：

```text
┌──────────── Vue UI ────────────┐
│                                │
│ REST                     WS    │
└───┬───────────────────────▲────┘
    │                       │
    ▼                       │
 FastAPI                 EventBus
    │                       ▲
    ▼                       │
 Services                  │
    │                       │
    ├──── RuleEngine ───────┤
    │                       │
    ▼                       │
 TaskFactory                │
    │                       │
    ▼                       │
 DownloadManager ───────────┘
    │
    ├── Scheduler
    ├── Worker
    ├── RetryPolicy
    ├── ResumeManager
    ├── ConflictManager
    └── PathService
    │
    ├──── SQLite
    │
    └──── File System

        AIService
            │
            ▼
 RuleEngine / Parser / Validator
            │
            ▼
        TaskFactory
            │
            ▼
     DownloadManager
```

---

# 4. UI 规则

UI 必须以用户提供的参考图为最终视觉标准。

优先级：

```text
UI参考图
>
最终确认的UI规范
>
需求文档中的文字描述
>
AI自行判断
```

禁止：

- 擅自换主题；
- 擅自重设计；
- 因“更现代”而修改布局；
- 使用大型 UI 组件库默认视觉覆盖参考图；
- 在视觉验收完成前大规模接入业务逻辑。

建议：

```text
Vue 3
TypeScript
自定义 CSS / SCSS
```

主要结构：

```text
App
├── TitleBar
├── Sidebar
│   ├── 任务工作台
│   ├── 下载历史
│   ├── URL规则
│   └── 偏好设置
│
└── Workspace
    ├── DownloadSource
    ├── SaveLocation
    └── DownloadQueue
```

适配尺寸：

```text
1024×768
1124×1068
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

推荐中文字体：

```css
"Microsoft YaHei UI",
"Microsoft YaHei",
"Segoe UI",
sans-serif
```

UI 验收使用 Playwright 截图对比：

```text
reference.png
current.png
diff.png
```

---

# 5. 推荐项目目录

```text
universal-downloader/
├── .venv/                  # Python开发虚拟环境，不提交Git/不进入发布包
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── stores/
│   │   ├── types/
│   │   └── styles/
│   ├── package.json
│   └── vite.config.ts
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
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
│
├── docs/
│   ├── REQUIREMENTS.md
│   ├── ARCHITECTURE.md
│   ├── API_SPEC.md
│   ├── DATABASE_SCHEMA.md
│   ├── TASK_STATE_MACHINE.md
│   ├── RULE_SPEC.md
│   ├── UI_SPEC.md
│   ├── TEST_PLAN.md
│   └── ACCEPTANCE_CHECKLIST.md
│
├── main.py
├── pyproject.toml
├── uv.lock                
├── .gitignore
└── UniversalDownloader.spec
```

---

# 6. 完整开发阶段

推荐严格按照以下顺序执行：

```text
00 开发环境初始化（.venv + uv + pyproject.toml）
   ↓
01 需求冻结
   ↓
02 项目骨架初始化
   ↓
03 UI 1:1 复刻
   ↓
04 pywebview 桌面壳
   ↓
05 FastAPI + Native Bridge
   ↓
06 SQLite / Settings
   ↓
07 RuleEngine
   ↓
08 DownloadManager
   ↓
09 WebSocket / EventBus
   ↓
10 恢复 / 日志 / 安全退出
   ↓
11 前后端联调
   ↓
12 自动化测试
   ↓
13 Windows 打包
   ↓
14 Win10 / Win11 / DPI 验收
   ↓
15 Release Candidate
   ↓
16 AIService
```

核心下载器稳定之前，不开发软件内部 AI 功能。

---

# 7. DEV-00：开发环境初始化

Python 后端在**开发阶段必须使用项目根目录的 `.venv` 虚拟环境**，禁止把项目依赖直接安装到系统 Python。

推荐统一使用：

```text
uv + .venv + pyproject.toml + uv.lock
```

职责划分：

```text
开发阶段
Windows
  ↓
项目根目录 .venv
  ↓
Python Backend
  ├── FastAPI
  ├── Uvicorn
  ├── httpx
  ├── aiofiles
  ├── aiosqlite
  ├── pywebview
  └── pytest / PyInstaller
  ↓
开发 / 测试 / 构建
```

最终发布阶段：

```text
.venv 中的 Python 环境
        ↓
   PyInstaller
        ↓
收集 Python 解释器 + 项目代码 + 运行依赖
        ↓
UniversalDownloader.exe / portable
        ↓
最终用户无需 Python、.venv、pip 或 uv
```

## 7.1 推荐初始化方式

优先使用 `uv`：

```powershell
cd universal-downloader

uv venv .venv

.\.venv\Scripts\Activate.ps1

uv sync
```

如果项目尚未配置依赖，可按实际依赖执行：

```powershell
uv add fastapi uvicorn httpx aiofiles aiosqlite pywebview
uv add --dev pytest pytest-asyncio pyinstaller
```

如果开发机没有 `uv`，允许临时使用标准 `venv`：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

但项目正式依赖仍应统一写入 `pyproject.toml`，避免只存在于某台开发机的全局环境中。

## 7.2 Python 命令执行规则

后续 AI 执行 Python 开发、测试和构建命令时，必须确保使用项目虚拟环境。

推荐：

```powershell
uv run python main.py
uv run pytest
uv run pyinstaller UniversalDownloader.spec
```

如果已经激活 `.venv`，也可以：

```powershell
python main.py
pytest
pyinstaller UniversalDownloader.spec
```

禁止：

```text
把 FastAPI/httpx/pywebview/PyInstaller 等项目依赖安装到系统 Python
使用来源不明的全局 Python 环境构建 Release
依赖“本机刚好安装过某个包”才能运行测试或打包
把 .venv 整个复制进最终发布目录
```

## 7.3 Git 忽略规则

`.venv` 属于本地开发环境，不提交 Git。

`.gitignore` 至少包含：

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/

build/
dist/

frontend/node_modules/
frontend/dist/
```

`pyproject.toml` 和 `uv.lock` 应提交 Git，以保证不同开发机和 CI 使用一致的 Python 依赖版本。

## 7.4 DEV-00 验收标准

```text
□ 项目根目录存在 .venv
□ Python 项目依赖由 pyproject.toml 管理
□ 使用 uv 时存在并提交 uv.lock
□ .venv 已加入 .gitignore
□ uv run python --version 正常
□ uv run pytest 可以启动测试框架
□ 系统 Python 不承担项目依赖
□ PyInstaller 将从项目虚拟环境执行
```

---

# 8. DEV-01：需求冻结

第一阶段禁止直接写复杂业务代码。

先整理并冻结：

```text
REQUIREMENTS.md
ARCHITECTURE.md
API_SPEC.md
DATABASE_SCHEMA.md
TASK_STATE_MACHINE.md
RULE_SPEC.md
UI_SPEC.md
TEST_PLAN.md
ACCEPTANCE_CHECKLIST.md
```

AI 不得：

- 自行修改产品功能；
- 自行增加需求；
- 自行改变架构；
- 自行重新定义 UI。

---

# 9. DEV-02：项目初始化

目标：

```text
npm run dev
→ Vue 可以启动

uv run python main.py
→ FastAPI 可以启动

uv run pytest
→ Python测试框架可以正常启动

GET /api/v1/health
→ 200 OK
```

本阶段不要实现：

```text
完整下载
Range
Retry
Conflict
复杂SQLite
```

先确保工程结构稳定。

---

# 10. DEV-03：UI 静态 1:1

此阶段全部使用 Mock 数据。

完成：

```text
标题栏
左侧导航
任务工作台
直接URL模式
规则模式
下载队列
保存位置
总体进度
状态标签
按钮
设置页面
历史页面
规则管理
日志区域
```

禁止提前接真实下载。

---

# 11. DEV-04：UI 响应式

分别验证：

```text
1024×768
1124×1068
1366×768
1440×900
1920×1080
```

要求：

- 不裁切；
- 不重叠；
- 文字不溢出；
- 表格正常；
- 中文正常；
- DPI 100/125/150% 均正常。

---

# 12. DEV-05：pywebview 桌面壳

目录：

```text
desktop/
├── window.py
├── bridge.py
└── lifecycle.py
```

实现 Native Bridge：

```text
选择文件夹
打开目录
最小化
最大化 / 还原
关闭窗口
拖动标题栏
```

选择下载目录必须调用 Windows 原生文件夹选择器。

不得使用浏览器文件选择控件代替。

---

# 13. 应用启动流程

必须：

```text
EXE 启动
↓
初始化日志
↓
初始化 SQLite
↓
选择随机本地端口
↓
启动 FastAPI
↓
等待 /api/v1/health
↓
启动 pywebview
↓
加载本地 Vue 页面
```

FastAPI：

```text
127.0.0.1:<随机端口>
```

禁止监听局域网地址。

---

# 14. DEV-06：FastAPI Skeleton

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

Router 只负责：

```text
参数解析
↓
参数校验
↓
调用Service
↓
返回DTO
```

禁止：

```python
@router.post(...)
async def api(...):
    # 直接执行下载
```

---

# 15. DEV-07：SQLite

永久数据目录：

```text
%LOCALAPPDATA%\UniversalDownloader\
├── downloader.db
├── logs\
└── cache\
```

至少包含：

```text
settings
rules
download_tasks
download_history
```

关键设置：

```text
output_dir
concurrency
max_retries
conflict_policy
current_mode
```

程序重新启动后必须保留：

- 下载目录；
- 并发数；
- 当前模式；
- 自动重试次数；
- 冲突策略；
- 用户自定义规则。

---

# 16. DEV-08：RuleEngine

规则逻辑必须和下载逻辑彻底分开。

结构：

```text
RuleEngine
├── Parser
├── Renderer
├── URLValidator
├── Preview
└── TaskFactory
```

处理链：

```text
用户输入
↓
Parser
↓
Renderer
↓
URLValidator
↓
Preview
↓
TaskFactory
```

最重要的约束：

```text
URL Preview
和
实际创建下载任务
必须使用同一个 Renderer
```

绝对不能分别实现两套模板渲染逻辑。

---

# 17. 内置 Jenkins HPI 规则

变量：

```text
{base_url}
{name}
{version}
{filename}
{ext}
```

默认模板：

```text
{base_url}/{name}/{version}/{name}.hpi
```

自定义规则支持：

```text
新增
编辑
删除
保存
重启后恢复
```

批量输入中某一行解析失败时：

```text
提示 / 跳过该行
但不应中断整批
```

---

# 18. DEV-09：DownloadTask 模型

建议：

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

任务状态必须持久化。

---

# 19. TaskStateMachine

不得在整个项目中随意：

```python
task.status = "xxx"
```

建议实现统一状态机：

```text
pending
↓
downloading
├── completed
├── failed
├── cancelled
└── waiting_user

failed
└── retry → pending/downloading

waiting_user
└── resolve → pending/downloading/failed
```

所有状态变化经过：

```text
TaskStateMachine
```

---

# 20. DEV-10：DownloadManager

核心结构：

```text
DownloadManager
├── Queue
├── Scheduler
├── Worker
├── RetryPolicy
├── ResumeManager
├── ConflictManager
└── EventBus
```

创建任务：

```text
API
↓
校验URL
↓
创建 DownloadTask
↓
保存 SQLite
↓
加入 Queue
↓
立即返回
```

真正下载：

```text
DownloadManager
```

异步执行。

---

# 21. DEV-11：并发调度

并发范围：

```text
1 ～ 32
```

默认：

```text
4
```

必须使用：

```python
asyncio.Semaphore(concurrency)
```

禁止：

```text
每个下载任务一个Thread
每个下载任务一个Process
```

推荐：

```text
Queue
↓
Scheduler
↓
Semaphore
↓
Async Worker
↓
httpx.AsyncClient
```

建议整个程序复用 `httpx.AsyncClient`。

---

# 22. DEV-12：基础下载

下载流程：

```text
URL
↓
检查路径
↓
检查冲突
↓
确定 .part
↓
建立HTTP请求
↓
流式写入 .part
↓
更新进度
↓
下载完成
↓
os.replace()
↓
正式文件
```

临时文件统一：

```text
filename.ext.part
```

所有下载必须：

```text
网络
↓
.part
↓
完成
↓
正式文件
```

不得直接写正式目标文件。

---

# 23. DEV-13：断点续传

如果 `.part` 已存在：

```http
Range: bytes=<已下载字节数>-
```

服务器返回：

```text
206
→ 从已有位置继续追加

200
→ 服务器不支持 Range
→ 从0重新下载
→ UI提示用户
```

完成后：

```python
os.replace(temp_path, final_path)
```

---

# 24. DEV-14：RetryPolicy

允许自动重试：

```text
连接中断
Timeout
500
502
503
504
```

默认最多：

```text
3次
```

退避：

```text
1秒
2秒
4秒
```

不自动重试：

```text
用户主动取消
普通4xx
非法路径
文件冲突等待用户处理
```

用户取消之后：

```text
保留 .part
status = cancelled
不自动重试
```

---

# 25. DEV-15：取消任务

取消时：

```text
通知 Worker
↓
停止当前 Response
↓
关闭网络流
↓
保留 .part
↓
写SQLite
↓
status = cancelled
↓
推送 task.cancelled
```

禁止取消后进入 RetryPolicy。

---

# 26. DEV-16：ConflictManager

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
发现正式文件已存在
↓
task.status = waiting_user
↓
WebSocket通知前端
↓
释放下载并发槽
↓
用户选择
↓
POST conflict-resolution
↓
任务重新进入 Scheduler
```

重要：

```text
waiting_user
不得长期占用 Semaphore
不得阻塞其他下载
```

---

# 27. DEV-17：PathService

所有文件名、目录和输出路径必须统一经过：

```python
PathService.safe_filename()
PathService.safe_subdir()
PathService.resolve_output_path()
```

必须禁止路径穿越：

```text
../../Windows/System32
..\..\xxx
```

最终输出路径必须确认：

```text
仍位于用户选择的下载根目录内部
```

同时处理 Windows 保留名称：

```text
CON
PRN
AUX
NUL
COM1...
LPT1...
```

以下数据全部必须经过安全处理：

```text
URL 文件名
Content-Disposition 文件名
规则生成文件名
用户子目录
自定义模板生成路径
```

---

# 28. DEV-18：EventBus + WebSocket

禁止 DownloadManager 直接操作 Vue。

正确链路：

```text
DownloadManager
↓
EventBus
↓
WebSocketManager
↓
Vue
↓
Pinia
↓
UI
```

地址：

```text
/ws/events
```

事件：

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

进度事件建议控制在：

```text
4 ～ 10 次 / 秒
```

禁止：

```text
每写一个chunk推一次WS
高频HTTP轮询
```

---

# 29. DEV-19：历史与日志

日志至少记录：

```text
应用启动
应用关闭
任务创建
任务开始
任务完成
任务失败
任务取消
任务重试
文件冲突
断点续传
规则错误
数据库异常
```

推荐：

```text
RotatingFileHandler
5 MB / 文件
保留 5 个历史文件
```

UI：

```text
查看近期日志
导出日志
```

---

# 30. DEV-20：程序恢复

测试场景：

```text
任务正在下载
↓
强制结束程序
↓
重新启动
```

启动时：

```text
downloading
→ pending
```

如果 `.part` 存在：

```text
重新进入Queue
↓
Range续传
```

任务状态、已下载字节等关键数据必须持久化。

---

# 31. DEV-21：安全退出

关闭窗口时绝不能直接：

```python
sys.exit()
```

必须：

```text
停止接收新任务
↓
通知/停止 Worker
↓
关闭HTTP Response
↓
保留 .part
↓
保存 SQLite
↓
关闭 httpx
↓
关闭 WebSocket
↓
停止 Uvicorn
↓
等待 Backend Thread
↓
销毁窗口
↓
退出
```

不得让后台线程继续访问已经销毁的 UI。

---

# 32. DEV-22：本地 API 安全

FastAPI 必须：

```text
仅监听 127.0.0.1
```

推荐：

```text
随机端口
启动时生成 Session Token
前端每次请求携带 Token
严格 CORS
禁止局域网访问
```

Session Token 仅用于当前应用实例。

---

# 33. DEV-23：前后端联调顺序

不要一次接全部功能。

顺序：

```text
1. Settings
2. Native Folder Select
3. Rule CRUD
4. Rule Preview
5. Direct Task Creation
6. Rule Task Creation
7. Queue
8. WebSocket
9. Progress
10. Cancel
11. Retry
12. Conflict
13. Resume
14. History
15. Logs
16. Shutdown
17. Restart Recovery
```

每完成一项先测试，再继续下一项。

---

# 34. 测试体系

测试分四层：

```text
Unit
Integration
Download E2E
UI E2E
```

---

# 35. Unit Tests

重点：

```text
Parser
Renderer
URLValidator
PathService
RetryPolicy
ConflictPolicy
TaskStateMachine
SettingsRepository
RuleRepository
TaskRepository
```

例如：

```text
test_retry_timeout
test_retry_500
test_retry_503
test_no_retry_404
test_no_retry_cancelled
test_no_retry_invalid_path
```

---

# 36. Integration Tests

建立本地测试 HTTP Server，模拟：

```text
200
206
Ignore Range
Slow Response
Connection Drop
500 → 200
404
Content-Length 缺失
Content-Disposition
```

不要依赖公网测试。

---

# 37. Download E2E

至少覆盖：

```text
正常 200
Range 206
不支持 Range
中途断开
500 后恢复
404
慢速下载
取消
文件冲突
```

额外建议：

```text
重启续传
重试耗尽
磁盘路径错误
自动重命名
并发1
并发32
大文件
0 byte文件
URL带query
Unicode文件名
Content-Disposition
```

---

# 38. UI E2E

Playwright 测试：

```text
直接URL
规则模式
切换模式
任务创建
进度
取消
失败
重试
冲突
完成
历史
设置
日志
```

视觉测试：

```text
reference.png
current.png
diff.png
```

---

# 39. DEV-24：PyInstaller 打包

PyInstaller **必须从项目 `.venv` 对应的 Python 环境执行**，不得使用系统 Python 或其他项目的虚拟环境构建正式版本。

推荐流程：

```text
uv sync
↓
npm run build
↓
Vue dist
↓
uv run pytest
↓
测试通过
↓
uv run pyinstaller UniversalDownloader.spec
↓
PyInstaller 从 .venv 收集 Python 解释器、项目代码和运行依赖
↓
UniversalDownloader.exe
```

同时建议输出：

```text
dist/
├── UniversalDownloader.exe
└── UniversalDownloader-portable/
```

---

# 40. 干净 Windows 环境测试

必须使用：

```text
无 Python
无 Node.js
无 npm
无开发工具
```

的 Windows 环境验证。

要求：

```text
双击 EXE
↓
正常启动
↓
创建下载
↓
下载完成
↓
关闭
↓
重新启动
```

全部正常。

---

# 41. Release Gate

只有以下项目全部通过，才可以声明第一版完成：

```text
□ 单URL正常
□ 多URL正常
□ HPI规则正常
□ 自定义Rule CRUD正常
□ Preview与实际URL一致
□ 默认并发4
□ 并发1～32有效
□ 取消不自动重试
□ 网络异常自动重试
□ 普通4xx不自动重试
□ Range续传有效
□ 不支持Range会回退
□ .part逻辑正确
□ conflict ask有效
□ waiting_user不阻塞其他任务
□ 输出路径安全
□ 设置持久化
□ 重启任务恢复
□ 历史正常
□ 日志正常
□ 日志导出正常
□ WebSocket正常
□ 安全退出正常
□ API只监听127.0.0.1
□ Session Token正常
□ UI参考图1:1验收通过
□ 100% DPI正常
□ 125% DPI正常
□ 150% DPI正常
□ Win10正常
□ Win11正常
□ 无Python机器正常
□ Portable正常
□ 单EXE正常
```

---

# 42. 软件内部 AI 功能开发时机

需要区分：

```text
使用AI开发软件
≠
软件内部AI功能
```

前面的 DEV 阶段是：

```text
使用AI开发下载器
```

只有下载核心通过 Release Gate 后，才允许开发：

```text
backend/ai/
```

---

# 43. AIService

未来接口：

```http
POST /api/v1/ai/generate-rule
POST /api/v1/ai/analyze-error
POST /api/v1/ai/parse-download-list
```

Provider 可预留：

```text
OpenAI
Azure OpenAI
Ollama
其他 OpenAI-compatible API
```

---

# 44. AIService 安全边界

AI 输出禁止直接执行下载。

必须：

```text
AI
↓
Parser / RuleEngine
↓
URLValidator
↓
TaskFactory
↓
DownloadManager
```

AI 不能：

```text
绕过 URL 校验
绕过 PathService
自行写任意磁盘路径
直接启动下载
绕过任务状态机
绕过下载队列
绕过权限与安全检查
```

AI 可以：

```text
生成候选规则
解析下载列表
分析错误
生成用户可确认的建议
```

---

# 45. 推荐 DEV 包拆分

整个项目建议拆成：

```text
DEV-00  开发环境初始化（.venv + uv + pyproject.toml）
DEV-01  需求冻结
DEV-02  项目初始化
DEV-03  UI静态1:1
DEV-04  UI响应式
DEV-05  pywebview
DEV-06  Native Bridge
DEV-07  FastAPI Skeleton
DEV-08  SQLite
DEV-09  Settings
DEV-10  RuleEngine
DEV-11  Rule CRUD
DEV-12  Direct Task Creation
DEV-13  DownloadManager
DEV-14  Scheduler / Semaphore
DEV-15  Basic HTTP Download
DEV-16  .part
DEV-17  Range Resume
DEV-18  RetryPolicy
DEV-19  Cancel
DEV-20  ConflictManager
DEV-21  PathService
DEV-22  EventBus
DEV-23  WebSocket
DEV-24  History
DEV-25  Logging
DEV-26  Restart Recovery
DEV-27  Safe Shutdown
DEV-28  Security
DEV-29  Frontend Integration
DEV-30  Unit Tests
DEV-31  Integration Tests
DEV-32  Playwright Visual Tests
DEV-33  Win10/11 Tests
DEV-34  PyInstaller
DEV-35  Portable Release
DEV-36  Release Acceptance

--------------------------

DEV-37  AIService Skeleton
DEV-38  AI Generate Rule
DEV-39  AI Analyze Error
DEV-40  AI Parse Download List
DEV-41  AI Security Validation
```

禁止跳过 DEV-00，也禁止从 DEV-01 直接跳到 DEV-36。

---

# 46. 每轮 AI 编码的标准流程

每一个 DEV 包都必须执行：

```text
读取项目文档
↓
读取当前代码
↓
确认本轮目标
↓
列出计划修改的文件
↓
实现
↓
静态检查
↓
Unit Test
↓
Integration Test（如适用）
↓
发现问题
↓
修复
↓
重新测试
↓
更新开发记录
↓
输出本轮变更摘要
↓
进入下一阶段
```

---

# 47. 每轮开始前 AI 必须输出

每次开始写代码前，先输出：

```text
【本轮目标】

【依据文档】

【准备修改文件】

【明确不修改的模块】

【验收标准】
```

如果需要修改当前阶段之外的大量文件，应先说明原因。

禁止无边界重构。

---

# 48. 每轮结束后 AI 必须输出

完成后：

```text
【实际修改文件】

【新增功能】

【修复问题】

【测试结果】

【仍存在的问题】

【是否达到本阶段验收标准】

【下一阶段建议】
```

不得仅因为：

```text
代码已经生成
```

就宣称：

```text
功能完成
```

---

# 49. AI 总控 Prompt

以下内容可以直接作为 Coding AI 的长期 System / Project Prompt。

```text
你正在开发 Universal Downloader。

所有实现必须以：
1. 通用下载器需求
2. 通用下载器技术架构设计文档
3. UI参考图
为唯一产品和架构依据。

开发原则：

1. 不擅自改变技术栈。
2. 不擅自修改UI设计。
3. UI以参考图1:1复刻为最高优先级。
4. 不把全部代码写入main.py。
5. FastAPI Router禁止直接执行下载。
6. 所有下载必须经DownloadManager。
7. 规则生成全部经RuleEngine。
8. Preview和实际任务必须共用Renderer。
9. 下载必须先写.part。
10. 完成后通过os.replace原子替换。
11. 所有外部文件名必须经过PathService。
12. 所有输出路径必须确认位于下载根目录。
13. 用户取消不得自动重试。
14. 普通4xx不得自动重试。
15. 网络异常与指定5xx按RetryPolicy处理。
16. waiting_user不得阻塞其他Worker。
17. 下载状态必须写入SQLite。
18. 程序异常退出后任务能够恢复。
19. 实时进度使用EventBus + WebSocket。
20. 禁止高频HTTP轮询。
21. Backend只监听127.0.0.1随机端口。
22. 前后端请求必须校验Session Token。
23. 程序关闭必须执行安全Shutdown流程。
24. 每实现一个模块必须同时增加测试。
25. 未通过当前阶段测试不得进入下一阶段。
26. 不主动开发额外功能。
27. 不为了“优化”擅自重构已经稳定的模块。
28. 不引入未经批准的大型新依赖。
29. 所有持久数据进入%LOCALAPPDATA%\UniversalDownloader。
30. 最终必须支持未安装Python/Node的Windows电脑。
31. Python开发、测试和PyInstaller构建必须使用项目根目录 `.venv`，禁止依赖系统Python中的项目包。
32. Python依赖必须由 `pyproject.toml` 管理；推荐使用 `uv.lock` 锁定版本。
33. `.venv` 不提交Git，也不得作为最终发布内容直接分发。
34. 不得让AI功能绕过RuleEngine、Validator、PathService、TaskFactory和DownloadManager。
35. 如需求文档、架构文档和UI文字描述存在视觉冲突，UI参考图优先。
36. 在不明确的情况下，不自行发明新的业务需求。
37. 每次修改尽量限制在当前DEV阶段相关模块。
38. 所有重要行为必须可以通过自动化测试验证。

每次开始开发前必须：
- 阅读相关文档；
- 阅读现有代码；
- 说明本轮目标；
- 说明准备修改哪些文件；
- 说明本轮不修改哪些稳定模块；
- 给出本轮验收标准。

每次完成后必须：
- 列出实际修改文件；
- 列出测试结果；
- 列出仍存在的问题；
- 明确是否通过当前阶段验收；
- 不得仅凭代码生成成功宣称功能完成。

如果发现当前实现与架构冲突：
- 不要继续叠加临时代码；
- 先指出冲突位置；
- 给出最小修复方案；
- 修复后重新执行测试。

如果需要大规模重构：
- 先解释为什么当前架构已无法满足既定设计；
- 尽可能采用最小范围修改；
- 不得顺手修改无关模块。
```

---

# 50. 推荐给 AI 的单阶段任务模板

后续每次可以这样给 AI 下任务：

```text
当前执行 DEV-XX：<阶段名称>。

请先阅读：
- 通用下载器需求
- 通用下载器技术架构设计文档
- 当前项目代码
- 当前阶段相关测试

本轮只完成：
<具体目标>

本轮禁止：
<禁止修改内容>

完成标准：
<明确验收项>

工作流程：
1. 先检查现有实现。
2. 输出本轮修改计划。
3. 实现最小必要修改。
4. 增加/更新测试。
5. 运行相关测试。
6. 修复失败项。
7. 输出最终变更摘要。
8. 未达到验收标准不得宣称完成。
```

---

# 51. 最终原则

整个项目始终坚持：

```text
先建立隔离、可复现的开发环境（.venv）
↓
先规范
↓
再UI
↓
再桌面壳
↓
再API
↓
再规则
↓
再下载核心
↓
再恢复与安全
↓
再测试
↓
再打包
↓
再验收
↓
最后才做软件内部AI功能
```

核心目标不是：

```text
让AI尽快写最多代码
```

而是：

```text
让AI在明确边界内
逐阶段实现
逐阶段测试
逐阶段验收
保证最终软件可维护、可恢复、可打包、可稳定运行
```

---

## 项目最终交付目标

```text
UniversalDownloader.exe
```

要求：

```text
Windows 10 / Windows 11
无需安装Python
无需安装Node.js
无需安装npm
支持直接URL下载
支持规则批量下载
支持断点续传
支持重试
支持取消
支持冲突处理
支持历史
支持日志
支持设置持久化
支持安全退出和重启恢复
UI按参考图1:1复刻
```

达到以上 Release Gate 后，第一版核心下载器才算完成。
