# URL 规则规格

## 1. 规则模型

规则包含：`id`、`name`、`base_url`、`url_template`、`filename_template`、`default_ext`、`builtin`。内置 Jenkins HPI 规则随应用提供且不可编辑/删除；用户规则可创建、编辑、删除并写入 SQLite。

## 2. 模板变量

| 变量 | 来源/意义 |
|---|---|
| `{base_url}` | 规则基础 URL |
| `{name}` | 当前输入行名称 |
| `{version}` | 当前输入行版本 |
| `{filename}` | 当前行的文件名主体/输入值，采用 Parser 归一化结果 |
| `{ext}` | 当前行扩展名；缺省时使用规则 `default_ext` |

`filename`/`ext` 在输入中的提取优先级尚未在来源文档定义。基线约定：Parser 接受明确字段（name、version，可选 filename、ext）；未提供 filename 时取 name，未提供 ext 时取 default_ext。若兼容旧 HPI 输入需要不同解析方式，DEV-10 前以样例冻结。

## 3. Jenkins HPI 基线规则

```text
url_template      = {base_url}/{name}/{version}/{name}.hpi
filename_template = {name}-{version}.hpi
default_ext       = hpi
```

`base_url` 的默认具体地址及旧版输入格式未提供，作为待确认配置；不要硬编码臆测地址。模板渲染完成后规范化分隔符并验证最终为绝对 HTTP/HTTPS URL。

## 4. Parser 与批量输入

- 输入可粘贴多行；空白行忽略。
- 每一行独立解析并返回原始行号、归一化字段或行级错误。坏行不阻断其他行。
- 字段分隔符、引号/转义规则必须依据原 HPI 示例冻结；当前资料未提供示例，故本阶段将格式标记为未决。实现不得静默猜测多种歧义格式。
- 规则字段必须非空/可解释；模板中未定义占位符、缺少必填变量、非法 URL 均以明确错误报告。

## 5. Renderer、预览与任务创建

唯一 Renderer 输入为已验证 Rule + Parser 输出，产生 URL 和本地文件名。预览和实际创建任务调用同一方法/结果 DTO，避免双重实现。渲染结果再经过 URLValidator 和 PathService；Renderer 不负责写文件或调度下载。预览至少显示每一行 URL、文件名及错误状态。

## 6. CRUD 与兼容

- 新建/更新的自定义规则持久化；规则 ID 稳定。
- 内置规则可用于预览/下载，不可编辑/删除。
- 删除规则不删除既有任务和历史快照。
- 除五个定义变量外的变量一律拒绝，避免未解析占位符进入 URL。

