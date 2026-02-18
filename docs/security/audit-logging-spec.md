# 审计日志规范（Audit Logging Spec）

本文件固化 GangQing（钢擎）的审计事件模型、采集范围、字段要求、脱敏要求与验收口径。审计用于“可追溯、可复核、可问责”，并与 `requestId/tenantId/projectId` 贯穿约束一致。

## 0. 强制原则
- **覆盖范围**：用户查询、工具调用、审批动作、写操作执行必须审计。
- **结构化**：必须输出结构化字段，便于后续写入 Elasticsearch/Loki 等。
- **脱敏**：审计中的参数必须做摘要与脱敏，禁止写入敏感原文（如配方、成本明细全量、密钥）。
- **可关联**：必须包含 `requestId`，并在可用时包含 `tenantId/projectId/sessionId/taskId/stepId/toolName`。

## 1. 事件类型（最小集合）
- `query`
  - 用户发起查询、对话、检索等只读行为
- `tool_call`
  - Agent 调用外部系统（ERP/MES/DCS/EAM）或内部工具
- `approval`
  - 审批链动作（submit/approve/reject/withdraw/timeout）
- `write_operation`
  - 实际写入/下发/执行/回滚

## 2. 审计事件字段（最小闭环）
必须字段：
- `event_id`：事件唯一 ID
- `ts`：UTC 时间戳（ISO8601）
- `requestId`
- `action_type`：见事件类型

强烈建议字段：
- `tenantId` / `projectId`
- `user_id` / `role`
- `resource`：如 API path、工具名、审批单号、执行对象
- `parameters`：结构化参数摘要（必须脱敏）
- `result`：结构化结果摘要（成功/失败、错误码、影响范围）

## 3. 脱敏与参数摘要规则
- **禁止**写入：密码、JWT、API Key、配方全量、财务原始单据全量、OT 点位写入明文（可写摘要）。
- 允许写入：
  - 哈希摘要（如 `sha256`）
  - 区间化数值（如 `cost_per_ton_range: 2800-2900`）
  - 资源标识（如设备统一 ID）

## 4. 错误与失败审计
- 认证/鉴权失败必须审计（含目标资源与失败原因摘要）。
- 工具调用失败必须审计：
  - `code`（如 `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE`）
  - `retryable`
  - `toolName`

## 5. 存储与检索（实现建议）
- PoC/试点阶段可先写入 SQLite/PostgreSQL。
- 生产阶段建议：
  - 结构化日志 -> Loki
  - 审计事件 -> Elasticsearch（或 ClickHouse）

## 6. 最小验收用例
- 调用 `/api/v1/chat`：至少写 `query` 审计。
- 工具调用：写 `tool_call` 审计（参数脱敏）。
- 审批动作：写 `approval` 审计。
- 写操作执行：写 `write_operation` 审计。
- 缺少 `requestId`：服务端生成并贯穿，审计中必须出现。
