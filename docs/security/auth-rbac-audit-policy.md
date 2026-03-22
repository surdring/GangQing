# Auth/RBAC/Audit 一致性策略（Task 3.3）

本文档定义 GangQing（钢擎）在 **认证（Auth）/权限（RBAC）/审计（Audit）** 上的最小一致性策略与验收口径。

目标：
- 任何关键安全拒绝事件必须 **可落库、可检索、可按 `requestId` 聚合取证**。
- 对外错误模型与审计事件之间必须可关联（至少通过 `requestId` + `errorCode`）。
- 审计/日志中 **禁止**记录任何密钥与凭证原文。

## 1. 审计事件最小字段集合（落库字段）

审计表：`audit_log`（append-only）字段最小集合：
- `eventType`
- `timestamp`
- `requestId`
- `tenantId`
- `projectId`
- `sessionId?`
- `userId?`
- `role?`
- `resource?`
- `actionSummary?`（JSON；必须脱敏）
- `result`（`success|failure`）
- `errorCode?`

索引与检索能力要求：
- 必须支持按 `tenantId/projectId/requestId` 检索事件序列（用于聚合取证）
- 必须支持按 `tenantId/projectId/eventType` + 时间范围检索

## 2. 事件类型（最小集合）

- `login.success`
- `login.failure`
- `auth.denied`
  - 触发：缺少 token / token 无效或过期 / scope（tenantId/projectId）缺失或不一致
- `rbac.denied`
  - 触发：capability 缺失导致拒绝（`FORBIDDEN`）
- `tool_call`
  - 触发：工具调用（必须记录参数摘要 `argsSummary`，且必须脱敏）
- `api.response`
  - 触发：API 响应摘要（成功/失败均记录）

## 3. 拒绝策略矩阵（对外错误码）

| 场景 | 对外错误码 | HTTP 状态码 | 是否写审计 | 审计 eventType | 备注 |
| --- | --- | --- | --- | --- | --- |
| 缺少 `Authorization` | `AUTH_ERROR` | 401 | 必须 | `auth.denied` + `api.response` | 禁止记录 token（不存在也不记录） |
| `Authorization` 非 Bearer / token 格式非法 | `AUTH_ERROR` | 401 | 必须 | `auth.denied` + `api.response` | `actionSummary.details` 只允许结构化原因 |
| token 过期 | `AUTH_ERROR` | 401 | 必须 | `auth.denied` + `api.response` |  |
| `tenantId/projectId` 缺失 | `AUTH_ERROR` | 401 | 必须 | `auth.denied` + `api.response` |  |
| token scope 与 `tenantId/projectId` 不一致 | `AUTH_ERROR` | 401 | 必须 | `auth.denied` + `api.response` |  |
| capability 缺失 | `FORBIDDEN` | 403 | 必须 | `rbac.denied` + `api.response` | `details.capability` 必须可检索 |
| capability 命名不合法（非 `domain:resource:action`） | `CONTRACT_VIOLATION` | 500（默认映射） | 必须（通过 `api.response`） | `api.response` | 属于系统契约错误，不应对外暴露敏感内部信息 |

## 4. 审计脱敏与禁止字段

### 4.1 禁止记录（必须为 0 容忍）
- `Authorization` header 原文
- `Bearer <token>` token 原文
- `password` / `passwd`
- `jwt_secret` / `secret`
- 上游系统凭证（`apiKey`、`accessKey`、`refreshToken` 等）

### 4.2 允许记录（建议最小化）
- `requestId/tenantId/projectId/userId/role`
- `capability`（例如 `finance:report:read`）
- `toolName`
- `statusCode`、`durationMs`（API 响应摘要）
- 结构化原因（例如 `details.reason`、`details.header`），但不得包含任何凭证原文

### 4.2.1 `actionSummary/argsSummary` 建议字段白名单（推荐）

| 场景 | 允许记录字段（建议） | 说明 |
| --- | --- | --- |
| `auth.denied` | `method`、`path`、`details.header`、`details.reason` | 禁止记录 `Authorization` 原文或任何 token 片段 |
| `rbac.denied` | `capability`、`role`、`details.reason` | `capability` 必须可检索；`role` 允许为空 |
| `tool_call` | `toolName`、`argsSummary`（脱敏后）、`durationMs`、`stage` | `argsSummary` 必须脱敏；不得包含原始 SQL/rows |
| `api.response` | `method`、`path`、`statusCode`、`durationMs` | 不记录请求体/响应体原文；仅摘要 |

> 说明：上述为“建议白名单”，实际实现可有少量扩展，但必须满足本节的“禁止字段/脱敏策略”。

### 4.3 脱敏策略
- `actionSummary` 与工具 `argsSummary` 必须经过脱敏：
  - 对 key 命中 `password/secret/token/api_key/authorization/cookie` 等片段的字段统一替换为 `[REDACTED]`
  - 递归处理嵌套对象与数组

### 4.4 禁止内容（补充）

除 4.1 列表外，审计事件中禁止记录：
- 原始 SQL 文本（例如包含 `SELECT ...`）
- 全量结果集/rows 明细
- 异常堆栈（stacktrace）与内部错误对象的 repr

## 5. 与对外错误模型的关联（Correlation）

- 对外错误体必须为 `ErrorResponse`：`code/message/details/retryable/requestId`
- 审计必须至少能通过：
  - `requestId` 聚合
  - `api.response.errorCode` 与对外 `ErrorResponse.code` 对齐
  - `auth.denied` / `rbac.denied` 说明拒绝原因

