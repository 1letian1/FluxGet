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
