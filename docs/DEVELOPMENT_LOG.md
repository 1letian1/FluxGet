# 开发记录

## DEV-00：开发环境初始化（依据更新后的流程补齐）

- 项目配置改为统一声明运行依赖（FastAPI、Uvicorn、httpx、aiofiles、aiosqlite、pywebview）和开发依赖（pytest、pytest-asyncio、PyInstaller）。
- 按新版流程建立根目录 `.venv` 并生成 `uv.lock`；Python 开发、测试与构建改用 `uv run`。
- 更新 `.gitignore` 排除虚拟环境、pytest 缓存及构建目录。
- 验收：uv 0.12.17、CPython 3.14.7；`uv sync` 成功，创建 `.venv` 并解析 59 个包、安装 45 个包。

## DEV-01：需求冻结文档基线

- 整理产品需求、技术架构、API、数据库、状态机、规则、UI、测试计划与发布验收清单。
- 未决项：UI 参考图未提供；原 HPI 输入样例/默认地址未提供；初始冲突策略 `ask` 为待确认基线解释。
- 结果：文档基线已建立；未实现应用代码。

## DEV-02：项目骨架初始化

- 建立 Vue 3 + TypeScript + Vite 前端骨架及 FastAPI 后端入口。
- 增加 `/api/v1/health`，开发服务器绑定 `127.0.0.1:8765`；Vite 绑定 `127.0.0.1:5173` 并代理 `/api`。
- 暂未实现下载、规则、桌面壳、SQLite 持久化、Range、Retry 或冲突处理。
- 按更新后的流程，验收命令统一使用 `uv run`：`uv run pytest`、`uv run python main.py`。原先系统 Python 的编译/服务检查只作为历史记录，不再作为环境验收依据。
- 验收：`uv run pytest` 通过（1 passed）；`uv run python main.py` 启动后 `/api/v1/health` 返回 200 和 `{"status":"ok"}`。
- 前端按固定技术栈加入 Pinia；验收：`npm run build` 成功，`npm run dev` 页面返回 200；样式入口归位到 `frontend/src/styles/app.css`。后端运行期间曾确认 Vite 代理 `/api/v1/health` 返回 200。
- 依赖安装：`npm install` 完成；保留 `frontend/package-lock.json`。
- 当前工作目录未初始化 Git 仓库，因此 `uv.lock` 已生成但尚不能提交；初始化 Git 后应将其纳入版本控制。

## DEV-03：UI 静态复刻

- 依据 `docs/UI.png` 实现深色桌面壳、标题栏、左侧导航、下载来源/规则表单、保存位置、队列和近期活动入口。
- 使用本地 Mock 任务数据；支持切换直接 URL/规则模式、显示输入行校验、查看生成 URL 预览、加入/移除/停止/重试任务、清空已完成，以及历史、规则和设置导航页。
- 更新 `docs/UI_SPEC.md`，登记已有参考图及尺寸。真实下载、桌面原生窗口控制、文件夹选择和持久化仍未接入。

## DEV-04：UI 响应式

- 增加 1120px、850px、560px 响应式布局断点；桌面下维持参考图的侧栏、双栏来源/保存卡片和队列，较窄屏幕改为图标导航和纵向卡片。
- 前端构建：`npm run build` 通过（`vue-tsc -b`、Vite production build）。浏览器视口已查看 1024×768、1124×1068、1366×768、1440×900、1920×1080。
- 尚未完成 DPI 100%/125%/150% 实机验收，也未产出参考图像素差分图；发布验收清单中的视觉/DPI项目仍保持未验证。

## DEV-05：FastAPI + Native Bridge

- 新增 FastAPI 应用工厂；桌面运行时使用随机 loopback 端口和每进程随机 Session Token，健康检查不要求 Token，其余 HTTP/WS 请求通过常量时间比较校验 `X-Session-Token`（WebSocket 也接受握手参数）。
- 新增桌面生命周期：先启动 Uvicorn 并等待健康检查，再创建无边框 pywebview 窗口；关闭窗口后停止 API 线程。生产前端由同一个 loopback 服务提供，避免 `file://` 跨域访问；开发模式可通过 `UNIVERSAL_DOWNLOADER_FRONTEND_URL` 指向 Vite 服务。
- Native Bridge 提供运行时 API 凭据、原生文件夹选择、打开目录、最小化、最大化/还原和关闭；Vue 的对应按钮已接入桥接，浏览器预览时保留提示行为。窗口使用 pywebview 的 `easy_drag` 支持无边框拖动。
- 本阶段仅建立启动/API/桥接骨架；任务 API、数据库初始化、安全关闭时的下载任务协调仍按后续阶段实现。
- 验收状态：本轮代码完成；需在可用 Windows 桌面会话中验证 pywebview 原生窗口及文件夹选择器。未将此类实机验收标记为通过。

## DEV-08：SQLite

- 新增 aiosqlite 数据库管理器，使用 Windows `%LOCALAPPDATA%\UniversalDownloader\downloader.db`（其他平台使用用户数据目录），首次启动创建 `logs/`、`cache/` 并通过 `PRAGMA user_version` 管理 schema v1。
- 建立 `settings`、`rules`、`download_tasks` 表、任务索引，以及基于终态任务的 `download_history` 视图；加入字段约束和删除规则时解除任务外键的行为。
- FastAPI lifespan 负责初始化数据库并预置默认设置，启动入口已连接到真实持久化层。
- 验收状态：实现完成；本轮未运行测试，数据库迁移及恢复场景尚未验证。

## DEV-09：Settings

- 新增设置 Repository/Service 和受 Session Token 保护的 `GET/PUT /api/v1/settings`。
- 默认值为用户 Downloads 目录、空子目录、并发 4、自动重试 3、冲突策略 `ask`、模式 `direct`；PUT 以完整对象写入并更新 UTC 时间。
- 校验绝对输出目录、拒绝空路径/null byte/额外字段，并发范围 1–32、重试非负、冲突策略及模式枚举；数据库约束同步兜底。
- 验收状态：实现完成；本轮未运行测试或做跨进程重启验证，前端设置页面尚未接入该 API，属于后续前后端联调阶段。

## DEV-10：RuleEngine

- 新增纯规则引擎模块：逐行 Parser、统一 Renderer、HTTP/HTTPS URLValidator、Preview DTO 和 TaskFactory 任务输入 DTO；引擎不依赖数据库或下载调度。
- 当前输入采用现有 UI 示例对应的空格/Tab 分隔格式：`name version [filename] [ext]`。每行独立返回结果，坏行不会阻断有效行；旧 HPI 输入兼容性仍待样例确认。
- URL 与文件名预览只由同一个 Renderer 生成；任务输入从 Preview 结果构造。校验拒绝未知占位符、非 HTTP(S) URL、URL 凭据及 Windows 不安全文件名。
- Jenkins HPI 规则模板已提供，但 `base_url` 保持未配置，不臆造默认站点地址。
- 验收状态：实现及规格记录完成；本轮未运行测试。规则 CRUD/SQLite 读写和预览 HTTP API 属于 DEV-11，尚未实现。

## DEV-13–23：DownloadManager、调度与传输链路

- 新增 `DownloadTask` 模型、SQLite Repository 和状态机；数据库 schema 从 v1 迁移到 v3，为任务保存创建时的冲突策略快照及根目录/相对子目录，并在启动时把中断中的下载恢复为 pending、按 `.part` 实际大小校准进度。
- 新增异步 DownloadManager：复用 `httpx.AsyncClient`，使用 asyncio 队列和 32 个轻量协程 Worker，通过可配置并发门限制实际下载数；支持设置变更后动态调整并发。
- 增加直链/规则任务创建、活动任务列表、取消、单项/批量重试与冲突决议 API。规则任务创建读取已保存规则，并复用 RuleEngine 预览结果。
- 下载先流式写入 `.part`，限制文件名/相对目录并验证输出目录包含关系；支持 Range 续传、服务器忽略 Range 时重写、进度事件节流及完成后 `os.replace`。
- 自动重试仅覆盖超时、连接中断和 HTTP 500/502/503/504，退避为 1/2/4 秒；用户取消保留部分文件。冲突支持 overwrite、rename、skip、ask，等待决议时释放并发槽。
- 新增 EventBus 和受 Session Token 保护的 `/ws/events`，任务状态与进度通过事件推送；FastAPI lifespan 创建并关闭 DownloadManager，关闭期间活动任务恢复到 pending。
- 本阶段做了 Python 语法编译检查（通过），未运行 pytest 或下载集成测试。Range、重试、冲突竞态、重启恢复、API/WS 和 Windows 文件行为仍需按 TEST_PLAN 实测；规则 CRUD/预览 API、完成队列清理和历史独立保留仍是后续工作。

## DEV-24：WebSocket / EventBus 联调

- EventBus 对慢订阅者清理过期积压并发出 `connection.resync_required`，避免静默丢失关键状态后 UI 长期过期。
- `/ws/events` 同时监听事件和客户端输入；支持应用层 ping/pong，客户端断开时及时取消接收任务并注销订阅。
- 进度事件在最多每秒 5 次的节流下附带 `speed_bytes_per_second`，同时复用任务 DTO 的字节数和百分比字段。
- 前端新增带 Session Token 的 WebSocket 客户端：首次连接、重连及队列溢出时获取活动任务 REST 快照；指数退避重连、心跳及事件增量合并均已接入工作台。直接 URL 创建、取消、重试请求已连到现有 API。
- 验收状态：实现已接通；本轮未运行测试或前端构建，因此端到端认证、断线恢复和事件节流仍待按 TEST_PLAN 验证。

## DEV-25：恢复与安全退出

- 启动恢复重新校验根目录、子目录、文件名和 `.part` 路径；只恢复位于经校验目标的普通临时文件，并按其实际大小校准进度。缺少 `.part` 时从 0 字节恢复；不安全、非普通文件或无法读取的项标记 `recovery_failed`，不再进入 Worker 队列。
- 正常窗口关闭先通知 Uvicorn 停止接收请求并等待 FastAPI lifespan；DownloadManager 取消延迟重试和 Worker，下载中任务保存为 pending 并保留 `.part`，关闭 HTTP 客户端后才销毁窗口。原生关闭按钮、窗口关闭事件及进程清理共用幂等停止逻辑；超过宽限期才强制退出。
- 验收状态：关闭和恢复流程已实现；异常终止/重启、文件系统边界和 Windows 窗口关闭顺序尚未实测。

## DEV-26：应用日志与导出

- 在用户数据目录 `logs/app.jsonl` 写入 UTF-8 JSONL 结构化日志；单文件 5 MiB，最多保留 4 个轮转文件。
- 记录任务创建、状态转移、恢复结果及管理器启停；记录下载 URL 时移除查询和片段，错误摘要不包含本地路径。
- 新增受 Session Token 保护的近期日志分页和 JSONL 导出 API；读取轮转文件、跳过损坏行并限制最大读取量。导出由前端触发文件下载，API 不接受任意服务端写入路径。
- 工作台近期活动入口可查看最近日志并导出。
- 验收状态：实现已接通；本轮未运行测试或前端构建，日志轮转、脱敏、下载和 API 认证仍待实测。
