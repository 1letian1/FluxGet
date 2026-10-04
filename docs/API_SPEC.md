# REST 与 WebSocket API 规格

API 版本前缀：`/api/v1`。除健康检查外，REST 请求必须携带当前实例 Session Token（建议请求头 `X-Session-Token`）；Token 的生成和传递由桌面壳与前端约定。FastAPI 仅绑定 loopback 随机端口。JSON 字符串使用 UTF-8。

## 1. 通用约定

- 成功响应为 JSON；创建任务返回已持久化的任务 DTO，不等待下载完成。
- 参数错误返回 422；资源不存在返回 404；冲突状态不允许操作时返回 409；内部错误使用通用错误 DTO，不泄露本机敏感路径或堆栈。
- 错误 DTO：`{ "error": { "code": "...", "message": "...", "details": {} } }`。
- 任务 DTO 至少含 `id,url,filename,output_dir,source_type,status,bytes_downloaded,bytes_total,progress,retry_count,max_retries,error_code,error_message,created_at,updated_at`。路径是否对 UI 完整展示由 UI 规格决定。

## 2. 端点

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查，不要求 Token |
| GET | `/api/v1/tasks` | 读取活动任务及其状态 |
| POST | `/api/v1/tasks/direct` | 校验多行 URL 并为有效项创建任务；返回 created 与逐行 errors |
| POST | `/api/v1/tasks/from-rule` | 用规则及批量输入创建任务；逐行报告无效项 |
| POST | `/api/v1/tasks/{id}/cancel` | 请求取消活动任务 |
| POST | `/api/v1/tasks/{id}/retry` | 手动重试失败或已取消任务 |
| POST | `/api/v1/tasks/retry-failed` | 重试所有失败任务 |
| POST | `/api/v1/tasks/clear-completed` | 清除完成任务的队列记录；历史记录保留 |
| POST | `/api/v1/tasks/{id}/conflict-resolution` | 提交 `overwrite / rename / skip` 冲突处理 |
| GET | `/api/v1/rules` | 列出内置与自定义规则 |
| POST | `/api/v1/rules` | 新增自定义规则 |
| PUT | `/api/v1/rules/{id}` | 更新自定义规则；内置规则返回 409 |
| DELETE | `/api/v1/rules/{id}` | 删除自定义规则；内置规则返回 409 |
| POST | `/api/v1/rules/{id}/preview` | 使用实际 Renderer 预览输入行 |
| GET | `/api/v1/settings` | 读取设置 |
| PUT | `/api/v1/settings` | 校验并保存设置 |
| GET | `/api/v1/history` | 分页读取已结束任务历史 |
| GET | `/api/v1/logs` | 分页读取近期日志 |
| POST | `/api/v1/logs/export` | 导出日志；返回导出位置或 Native Bridge 可处理的导出结果 |

列表接口需支持稳定分页（`limit`,`offset`）和明确排序；默认最新优先。直接任务请求建议 `{ "urls": "每行一个 URL", "output_dir": "...", "subdir": "" }`。规则任务请求包含 `rule_id`、批量输入及输出设置。规则字段详见 `RULE_SPEC.md`。设置字段详见 `DATABASE_SCHEMA.md`。具体 Pydantic DTO 在 DEV-07 实现时按此合同定义。

## 3. 任务控制语义

- Cancel 对 pending/downloading 生效；终态取消请求返回 409 或幂等当前状态，具体统一在实现阶段选定并保持一致。
- Retry 重置错误信息及本轮计数，进入 pending；用户手动重试不算自动重试次数。
- 冲突解决仅接受等待用户任务；`overwrite`、`rename`、`skip` 分别执行覆盖、生成安全的新文件名、结束为跳过（历史保留）。
- `clear-completed` 不删除下载文件和历史记录。

## 4. WebSocket

路径：`/ws/events`。连接需通过握手查询参数或首条消息认证 Session Token；实现选用一种并与本地来源校验共同执行。事件包：`{ "type": "task.progress", "data": {...}, "occurred_at": "ISO-8601" }`。

事件至少包括：`task.created`、`task.started`、`task.progress`、`task.retrying`、`task.waiting_user`、`task.completed`、`task.failed`、`task.cancelled`。进度数据含 task id、已下载字节、总字节（可空）、百分比（不可计算时为空）及速度（可空）。建议限流 4–10 次/秒；连接断开时前端重新 GET 当前任务快照，不使用高频 HTTP 轮询。

## 5. 尚未冻结的细节

批量输入字段的最终 JSON 形状、历史 DTO 保留字段/保留期限、日志导出目标路径选择交互以及 WebSocket Token 的传递载体将在 DEV-07/API 实现前结合 Native Bridge 确定；不得改变上述资源、行为和安全边界。

