# Universal Downloader 技术架构基线

## 1. 目标与固定技术

Windows 10/11 桌面程序；最终以 PyInstaller 提供单 EXE 和 portable 目录版。除非明确批准，不改变既定技术栈：Vue 3 + TypeScript + Vite + Pinia、自定义 CSS、pywebview、FastAPI + Uvicorn、asyncio + httpx.AsyncClient + aiofiles、SQLite + aiosqlite、WebSocket、PyInstaller。

## 2. 组件边界

```text
Vue UI / Pinia
  ├─ REST API ──> FastAPI Router ──> Services
  │                                  ├─ RuleEngine / Parser / Renderer
  │                                  ├─ TaskFactory
  │                                  ├─ Settings / History / Log services
  │                                  └─ DownloadManager
  │                                        ├─ Queue / Scheduler / Semaphore
  │                                        ├─ Worker / RetryPolicy / ResumeManager
  │                                        ├─ ConflictManager / PathService
  │                                        └─ EventBus
  └─ WebSocket <── WebSocketManager <── EventBus

pywebview Native Bridge ── folder dialog / window controls / open folder
SQLite ── settings / rules / tasks / history
File system ── .part and completed downloads
```

Router 负责解析、验证请求、调用服务和返回 DTO，不直接执行下载。下载只由 DownloadManager 调度；规则预览和任务创建共用 Renderer；所有路径通过 PathService。模块不得依赖 Vue 或直接操作 UI。

## 3. 进程与启动

桌面主进程创建数据目录、日志及 SQLite，生成随机端口与仅当前实例有效的 Session Token，在后台线程运行 asyncio/FastAPI；FastAPI 绑定 `127.0.0.1:<random-port>`。应用等待 `/api/v1/health` 成功后启动无边框 pywebview 并加载本地 Vue 构建产物。前端请求携带 Token。关闭流程停止新任务、通知/取消 Worker、关闭响应流、保留 `.part`、提交数据库、关闭 HTTP 客户端与 Uvicorn，等待后台线程后销毁窗口。

## 4. 下载数据流

```text
输入 -> URL/规则校验 -> TaskFactory -> SQLite(pending) -> Queue
     -> Scheduler/Semaphore -> PathService/ConflictManager
     -> HTTP stream -> <filename>.part -> atomic replace -> completed
     -> EventBus -> WebSocket -> Pinia/UI
```

使用复用的 `httpx.AsyncClient` 和 `asyncio.Semaphore`，并发范围 1–32，默认 4。进度事件限流至约 4–10 次/秒。Range 续传、重试、冲突及状态转换详见专门规格。

## 5. 数据与安全边界

永久数据位于 `%LOCALAPPDATA%\UniversalDownloader\`，包括 `downloader.db`、`logs/`、`cache/`。任务、规则、设置持久化；启动时将遗留的 `downloading` 转为 `pending`，保留有效 `.part`。SQLite schema 见 `DATABASE_SCHEMA.md`。

只允许绝对 HTTP/HTTPS URL；服务仅绑定 loopback；随机 Session Token 仅在当前进程有效；不开放任意 CORS。文件名、子目录、规则输出名和解析后的完整路径必须经过统一安全校验，并确保位于下载根目录内。AI（未来阶段）只能产生候选内容，必须经 Parser、Validator、TaskFactory 和 DownloadManager，不能直接访问文件系统或启动下载。

## 6. 建议目录结构

```text
.venv/                              # 本机 Python 环境；忽略、不打包
frontend/
├── index.html
├── package.json
├── package-lock.json
├── vite.config.ts
└── src/
    ├── api/
    ├── components/
    ├── pages/
    ├── stores/
    ├── types/
    ├── styles/app.css
    ├── App.vue
    └── main.ts
backend/
├── api/
│   └── app.py
├── core/
├── download/
├── rules/
├── models/
├── persistence/
└── ai/
desktop/{window.py,bridge.py,lifecycle.py}  # 桌面阶段实现
tests/{unit,integration,e2e,fixtures}/
docs/{REQUIREMENTS,ARCHITECTURE,API_SPEC,DATABASE_SCHEMA,TASK_STATE_MACHINE,RULE_SPEC,UI_SPEC,TEST_PLAN,ACCEPTANCE_CHECKLIST,DEVELOPMENT_LOG}.md
main.py
pyproject.toml
uv.lock                              # 锁定 Python 依赖并纳入版本控制
.gitignore
UniversalDownloader.spec            # PyInstaller 阶段新增
```

Python 开发、测试和 PyInstaller 构建统一通过根目录 `.venv` 执行，依赖由 `pyproject.toml` 管理，推荐 `uv sync`/`uv run`。`.venv` 不提交 Git，也不进入发布包；`uv.lock` 应提交。前端依赖由 `frontend/package.json` 和 `frontend/package-lock.json` 管理，`frontend/node_modules/` 不提交。

## 7. 阶段边界

DEV-00 先建立隔离、可复现的 Python 环境；DEV-01 冻结文档；DEV-02 初始化可启动骨架并验证 pytest；之后实现静态 UI 与响应式，再接桌面壳/API/持久化/规则，最后实现下载引擎、恢复、安全、测试与打包。核心 Release Gate 全部通过前不开发软件内部 AI 功能。不得跳过 DEV-00 或从 DEV-01 跳到发布阶段，也不得顺手做无关重构。
