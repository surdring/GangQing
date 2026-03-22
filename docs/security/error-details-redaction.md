# ErrorResponse.details 与审计摘要脱敏规则（Contract Validation）

本文档定义 GangQing（钢擎）对外 `ErrorResponse.details` 与审计事件 `actionSummary/argsSummary` 的 **脱敏（redaction）** 规则与验收口径。

适用范围：
- 对外 REST 错误响应体：`ErrorResponse.details`
- 流式（SSE/WebSocket）错误事件载荷中的 `ErrorResponse.details`
- 审计落库 JSON 字段：`audit_log.action_summary`（或等价字段）
- 工具审计摘要：`tool_call.args_summary`（或等价字段）

## 1. 强制原则（MUST）

- **先脱敏后落库/对外**：任何 `details/actionSummary/argsSummary` 在落库或对外输出前必须经过递归脱敏。
- **0 容忍泄露**：不得包含任何凭证原文、连接串、cookie、私钥、原始 SQL、完整 rows、堆栈等。
- **仅保留结构化摘要**：只允许保留排障所需的最小结构化信息（例如字段级错误摘要、稳定原因枚举、契约来源标识）。
- **英文 message**：对外错误 `message` 必须为英文（便于日志检索）；本文件不改变该约束。

## 2. 禁止内容（MUST NOT）

### 2.1 禁止 key 片段（递归处理）

若任意对象 key（大小写不敏感）命中以下片段，必须将对应 value 替换为固定字符串：`[REDACTED]`。

- `password`
- `passwd`
- `secret`
- `token`
- `api_key`
- `apikey`
- `authorization`
- `cookie`
- `set-cookie`

说明：该规则适用于任意层级的嵌套对象与数组元素。

### 2.2 禁止数据类型/大对象

- **原始 SQL**：不得记录完整 SQL 文本（即使不包含敏感字段，也可能泄露内部结构）。
- **完整 rows**：不得记录查询结果的完整行数据。
- **连接串/主机端口**：不得记录 DB URL、内部 host:port（除非是公开的外部健康检查 URL 且经过审核）。
- **异常堆栈**：不得对外返回 traceback；审计中也不得写入完整堆栈。

## 3. 允许字段（SHOULD，建议最小化）

- `reason`：稳定原因枚举或简短字符串（不包含敏感信息）
- `fieldErrors`：字段级错误摘要数组
  - `path`：字段路径（字符串或字符串数组序列化）
  - `reason`：英文简述
- `source`：契约来源标识（例如 `tool.postgres_readonly.result`）
- `capability`：被拒绝的 capability 名称（例如 `tool:postgres:read`）
- `durationMs`：耗时（毫秒）

## 4. 实现要求（MUST）

- 后端必须提供统一的递归脱敏函数，并在以下位置调用：
  - 写入审计事件前
  - 组装对外 `ErrorResponse.details` 前（如 details 来自上游/异常上下文）
- 支持通过环境变量扩展敏感 key 片段：
  - `.env.example`：`GANGQING_REDACTION_SENSITIVE_KEY_FRAGMENTS`
  - 用法：逗号分隔，小写比较

## 5. 验收用例（MUST）

- 当入参校验失败（`VALIDATION_ERROR`）：
  - `ErrorResponse.details.fieldErrors` 存在
  - `details` 不包含禁止 key 片段与敏感值
- 当输出契约违规（`CONTRACT_VIOLATION`）：
  - `ErrorResponse.details.source` 存在
  - `details.fieldErrors` 存在
  - 审计 `tool_call` 事件的 `argsSummary` 同样不包含敏感信息
- 当 RBAC 拒绝（`FORBIDDEN`）：
  - `details.capability` 可检索
  - `details` 不包含 token/cookie/authorization 原文
