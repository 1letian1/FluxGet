# SQLite 数据模型基线

数据库位置：`%LOCALAPPDATA%\UniversalDownloader\downloader.db`。使用 SQLite；异步访问使用 aiosqlite。时间统一存为 UTC ISO-8601 字符串。主键任务/规则使用 UUID 字符串或稳定字符串 ID；实际建表时统一一种格式。

## 1. `settings`

单行键值表或等价结构化单例表，逻辑字段：

| 字段 | 类型/约束 | 默认/说明 |
|---|---|---|
| `id` | INTEGER PK | 固定为 1 |
| `output_dir` | TEXT | 首次启动时平台默认下载目录；若无法解析须引导选择 |
| `subdir` | TEXT | 空字符串 |
| `concurrency` | INTEGER CHECK 1–32 | 4 |
| `max_retries` | INTEGER CHECK >=0 | 3 次自动重试 |
| `conflict_policy` | TEXT enum | `ask` 基线解释，待产品确认 |
| `current_mode` | TEXT enum | `direct` |
| `updated_at` | TEXT | UTC |

覆盖/重命名/跳过/询问的策略值为 `overwrite`,`rename`,`skip`,`ask`。

## 2. `rules`

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| `id` | TEXT PK | 稳定 ID |
| `name` | TEXT NOT NULL | 唯一显示名（是否大小写敏感由实现统一） |
| `base_url` | TEXT NOT NULL | 基础 URL |
| `url_template` | TEXT NOT NULL | URL 模板 |
| `filename_template` | TEXT NOT NULL | 本地文件名模板 |
| `default_ext` | TEXT | 可空或空字符串 |
| `builtin` | INTEGER CHECK 0/1 | 内置记录不可编辑/删除 |
| `created_at`,`updated_at` | TEXT | UTC |

安装/升级时确保 Jenkins HPI 内置规则存在。自定义规则持久化。是否可重命名重名规则需由 RuleService 做一致性检查。

## 3. `download_tasks`

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `url` | TEXT NOT NULL | 已验证 URL |
| `filename` | TEXT NOT NULL | 安全化文件名 |
| `output_dir` | TEXT NOT NULL | 解析出的目标目录 |
| `temp_path` | TEXT NOT NULL | `.part` 路径 |
| `source_type` | TEXT enum | `direct` / `rule` |
| `rule_id` | TEXT NULL | 来源规则，删除规则不删除历史任务 |
| `status` | TEXT enum | 见 `TASK_STATE_MACHINE.md` |
| `bytes_total` | INTEGER NULL | 未知时 NULL |
| `bytes_downloaded` | INTEGER NOT NULL DEFAULT 0 | 当前 `.part` 字节数 |
| `retry_count` | INTEGER NOT NULL DEFAULT 0 | 自动重试已用次数 |
| `max_retries` | INTEGER NOT NULL | 创建时快照 |
| `error_code`,`error_message` | TEXT NULL | 可读错误摘要 |
| `created_at`,`updated_at`,`started_at`,`finished_at` | TEXT | UTC；后两者可空 |

索引：`status, created_at`、`created_at`。任务状态和进度需在关键转移与节流进度点持久化。

## 4. `download_history`

终态任务历史。最小字段：`id`（任务 ID 主键）、`url`、`filename`、`output_dir`、`source_type`、`status`、`bytes_downloaded`、`bytes_total`、`retry_count`、`error_code`、`error_message`、`created_at`、`finished_at`。历史可以通过归档复制或从终态任务视图提供，但 `clear-completed` 不删除历史。避免任务表和历史重复事实不一致；实现选择单表查询视图或事务归档，并在 DEV-08 统一。

## 5. 事务及恢复

- 创建任务时，在同一事务内写入任务后入队；队列失败须可重建。
- 终态更新与历史可见性原子化。
- 启动恢复将状态 `downloading` 更新为 `pending`，保留 `.part` 路径/字节计数；恢复后依据文件实际大小校准字节数。
- SQLite 不保存 Session Token、请求头密钥或敏感凭据。

