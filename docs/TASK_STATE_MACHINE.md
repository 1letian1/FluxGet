# 下载任务状态机

## 1. 状态

| 状态 | 含义 | 终态 |
|---|---|---|
| `pending` | 已创建，等待调度或等待手动重试 | 否 |
| `downloading` | Worker 持有并发槽并传输数据 | 否 |
| `waiting_user` | 文件冲突待用户选择；不占并发槽 | 否 |
| `completed` | 文件完整写入并提交至目标路径 | 是 |
| `failed` | 不可自动恢复或自动重试耗尽 | 是 |
| `cancelled` | 用户主动停止；保留部分文件 | 是 |
| `skipped` | 冲突策略选择跳过 | 是 |

`skipped` 是架构冲突策略的明确结果，UI 可归入已结束记录展示；历史需求中的五种状态仍需按原名支持。

## 2. 允许转移

```text
创建 -> pending
pending -> downloading | cancelled
downloading -> completed | failed | cancelled | waiting_user | pending(retry/backoff)
waiting_user -> pending(overwrite/rename) | skipped | failed
failed -> pending(用户手动重试)
cancelled -> pending(用户手动重试)
```

禁止其他直接状态赋值；所有变化经 TaskStateMachine 并持久化后发事件。`completed`、`skipped` 不允许重试。状态 DTO/event 需包含转移原因或错误摘要。

## 3. 重试与取消

- 自动重试只适用于超时、连接中断及配置定义的服务器错误（基线：500、502、503、504），最多默认 3 次，等待 1、2、4 秒。`retry_count` 表示已消耗的自动重试次数。
- 普通 4xx、非法 URL/路径、磁盘写入错误和文件冲突不自动重试。其他 5xx 基线按失败处理，除非以后明确调整。
- 取消优先于重试：取消令牌置位后关闭响应流、保留 `.part`，最终状态 `cancelled`；取消操作不得进入 RetryPolicy。
- 用户手动 retry 将 `failed`/`cancelled` 重新置为 `pending`，清除本次错误并从可续传 `.part` 开始；它不会被当作自动重试次数。

## 4. 冲突处理

调度后、请求或最终提交前都要避免无意覆盖。策略 `ask` 时进入 `waiting_user`、通知 UI、释放 Semaphore。覆盖或重命名后回到 `pending`；跳过转为 `skipped`。若目标在下载过程中被外部创建，提交前重新检查并依照策略处理。

## 5. 持久化与崩溃恢复

所有状态转换事务性持久化。启动时校验残留任务的根目录、文件名、相对子目录和 `.part` 目标路径；有效任务将 `downloading` 转为 `pending`，再以 `.part` 实际字节数恢复。缺失 `.part` 从 0 字节重新开始；越界/符号链接/不可读取的临时文件标记为 `failed` 并提供通用错误摘要。关闭时先停止接收请求，再取消活动流并事务性恢复为 `pending`，不把用户未取消的任务误记为 `cancelled`；`.part` 保留以供下次启动续传。
