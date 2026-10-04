# 测试计划（验收基线）

本文件定义后续阶段的测试范围；DEV-01 不实现或运行测试。优先使用本地模拟 HTTP 服务，不依赖公网。

## 0. 开发环境检查

- Python 命令通过项目根目录 `.venv` 执行；推荐 `uv sync` 后运行 `uv run ...`。
- `uv.lock` 固定 Python 依赖解析结果；`.venv`、缓存及构建产物不进入 Git/发布包。
- DEV-02 需运行 `uv run pytest` 确认测试框架可用，并验证 FastAPI 健康接口；不使用系统 Python 中偶然安装的项目依赖。

## 1. 单元测试

- Parser：空行、合法/非法行、字段缺失、行号、批次部分成功。
- Renderer/URL Validator：所有变量、缺失/未知变量、预览与任务地址一致、只允许 HTTP/HTTPS。
- PathService：路径穿越、Windows 保留名、Unicode、扩展名、根目录包含关系。
- TaskStateMachine：允许/拒绝的转移、取消优先、终态、等待用户。
- RetryPolicy：超时/连接中断/指定 5xx 重试；普通 4xx、取消、路径及冲突不重试；上限和 1/2/4 秒退避。
- Settings/Rule/Task repository：默认值、校验、持久化、重启读取、事务与删除限制。

## 2. 集成下载测试

以本地 HTTP 服务模拟：200 正常、大文件流、206 Range、忽略 Range 返回 200、无 Content-Length、慢响应、连接中断、500 后恢复、502/503/504、404、文件名冲突、Content-Disposition（优先级待需求冻结）、零字节文件。验证 `.part`、进度、最终原子替换、错误分类及可恢复性。

## 3. API / 桌面集成

- REST DTO/状态码、逐行批处理、规则 CRUD/预览、设置持久化、取消/重试/冲突决议。
- Session Token 缺失/错误拒绝；监听地址确认为 loopback；无任意 CORS。
- WebSocket 认证、事件种类、进度限流、断线后任务快照恢复。
- Native 文件夹对话框、打开目录、标题栏 controls、安全关闭及后端线程生命周期。

## 4. UI / 视觉 E2E

Playwright 覆盖直接 URL、规则模式/预览、创建任务、进度、取消、失败重试、冲突决议、完成、历史、设置、日志导出。视觉截图覆盖 1024×768、1124×1068、1366×768、1440×900、1920×1080 及 DPI 100/125/150%；与已确认参考图比较。

## 5. 恢复与发布验收

- 下载中强制退出并重启：任务恢复 pending、`.part` 与实际字节对齐并按 Range 续传。
- 并发 1、默认 4、上限 32；用户取消无自动重试；等待冲突不占并发槽。
- Win10/Win11 与无 Python/Node/npm 环境启动；单 EXE 和 portable 目录版；下载、关闭、重启基本流程。

## 6. 阶段门槛

DEV-01 只审阅文档一致性。之后每阶段仅运行相关测试，失败先修复再推进；Release Gate 见 `ACCEPTANCE_CHECKLIST.md`。不把未执行/未通过的验证描述成通过。
