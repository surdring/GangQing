# Task 17 执行蓝图：审计落库与不可篡改（append-only + 查询也要被审计）
本计划用于在现有 GangQing 代码与契约基础上，补齐 Task 17 的审计事件模型、append-only 不可篡改策略、以及“审计查询的二次审计”，并确保 `requestId` 贯穿与 RBAC/脱敏/结构化错误一致。

## 0. 现状盘点（来自仓库现有实现）

### 0.1 已具备能力（可复用）
- **审计落库（基础）**：
  - `backend/gangqing/common/audit.py` 提供 `write_audit_event(...)` 与 `write_tool_call_event(...)`，已使用 `RequestContext` 写入审计。
  - `backend/gangqing_db/audit_log.py` 定义 `AuditLogEvent`（Pydantic）并执行 INSERT；落库前对 `actionSummary` 做递归脱敏（`redact_sensitive`），并做了 role-based masking 的兜底处理。
- **append-only（DB 防篡改）**：
  - `backend/migrations/versions/0001_init_min_schema.py` 中 `audit_log` 已设计为分区表，并通过 `BEFORE UPDATE/DELETE` trigger 阻断变更。
  - 已定义 DB role：`gangqing_migrator`（owner）、`gangqing_app`（SELECT/INSERT）、`gangqing_auditor`（SELECT）。
- **RBAC（capability）**：
  - `backend/gangqing/common/rbac.py` 采用“role -> capabilities”映射；API 通过 `require_capability(...)` 做能力点校验，且 RBAC 拒绝会写 `rbac.denied` 审计事件。
- **审计查询 API（基础）**：
  - 已存在 `GET /api/v1/audit/events`（`backend/gangqing/api/audit.py`），支持按 `requestId` 过滤、分页，返回结构化列表。
  - 已存在 `backend/gangqing_db/audit_query.py:list_audit_events(...)`，按 `tenant_id/project_id` scope 查询，且设置 session GUC（为未来 RLS 预留）。
- **结构化错误**：
  - `backend/gangqing/common/errors.py` 定义对外 `ErrorResponse`（code/message/details?/retryable/requestId），满足契约要求（message 英文）。

### 0.2 与 Task 17 的关键差距（必须补齐）
- **事件覆盖面不全**：当前审计事件类型枚举（`AuditEventType`）不完整；`tool.result`/`response`/`error` 等仍缺少统一口径（现有更多偏向 `tool_call` 与拒绝类事件）。
- **“查询也要被审计（二次审计）”未落地**：
  - `GET /audit/events` 当前只读，不会为“这次查询行为”写入审计事件（仅在发生 masking hits 时写 `data.masked`）。
- **append-only 的“更正只能追加”关联字段缺失**：
  - `audit_log` 表与 `AuditLogEvent` 模型未包含 `correlation_id` / `supersedes_event_id` 等字段，无法表达“更正/补录”的追加链路。
- **审计事件的字段口径需与契约对齐**：
  - 合同草案 `docs/contracts/api-and-events-draft.md` 的审计字段使用 `eventId/eventType/result` 等语义；现有 DB 模型使用 `id/event_type/result_status` 等，需要明确“对外命名 vs DB 命名”的映射策略。

## 1. RBAC 策略推荐（对 Task 17 的选择）

### 1.1 推荐：Hybrid（对外 capability 契约化 + 内部 role 映射）
- **对外契约**：所有“读审计/导出审计/解除脱敏”等能力点，均以 capability 字符串作为单一授权语义（便于扩展与审计）。
- **内部实现**：继续保留 `Role -> set[capabilities]` 的映射（适合 L1 阶段快速落地）。

### 1.2 建议 capability 设计（仅规划，不实现）
- **audit:event:read**：读取审计事件列表（现有已使用）。
- **audit:event:export**（预留）：导出/大批量读取（可与限流、最大条数强绑定）。
- **audit:event:read_unmasked** 或沿用现有 **data:unmask:read**：允许对审计中的 `actionSummary/resultSummary` 做解脱敏查看（需与 masking policy 统一）。

### 1.3 越权与缺上下文拒绝策略
- **缺少 token**：返回 `AUTH_ERROR`（HTTP 401），并写 `auth.denied` 审计事件（已在其它链路覆盖，需确认 audit API 也覆盖）。
- **缺少 capability**：返回 `FORBIDDEN`（HTTP 403），并写 `rbac.denied` 审计事件（已由 `require_capability` 自动记录）。
- **跨 tenant/project**：必须拒绝并审计（建议复用 `FORBIDDEN` 或 `AUTH_ERROR`，以 `docs/contracts/api-and-events-draft.md` 的映射为准）。

## 2. Task 17.1：审计事件模型与字段口径（Schema First）

### 2.1 目标
- 统一审计事件 schema（Pydantic 单一事实源），明确事件类型枚举与最小字段集合，确保可按 `requestId` 聚合追溯。

### 2.2 审计事件最小字段集合（对齐 contracts 4.2）
- **identity（强制）**：`requestId`、`tenantId`、`projectId`、`timestamp`。
- **actor（尽量）**：`userId`、`role`（无登录态时可为空，但必须能表达“auth.denied”场景）。
- **event（强制）**：`eventType`（稳定枚举/字符串）。
- **target/action（建议）**：`resource`（路径/工具名/资源标识）。
- **payload summary（可选但推荐）**：
  - `actionSummary`：参数摘要（必须脱敏）；
  - `resultSummary`（如需要，建议纳入，但需控制体积与敏感信息）。
- **result（强制）**：`result`（success/failure），以及失败时的 `errorCode`（与对外错误码一致）。
- **linkage（可选）**：`sessionId`、`stepId`、`toolCallId`、`evidenceRefs`。
- **correction linkage（新增，append-only 更正链路）**：
  - `correlationId`（同一业务操作/同一链路的聚合 id，可选）；
  - `supersedesEventId`（更正/补录时指向被更正事件，强烈建议）。

### 2.3 事件类型枚举规划（覆盖 MUST 列表）
- **query**：用户查询（包含 query 摘要）。
- **tool.call**：工具调用开始（args 摘要、attempt/耗时等摘要）。
- **tool.result**：工具调用结束（成功/失败、result 摘要/错误码）。
- **response**：对外响应完成（REST 或 SSE final 的摘要 + evidenceRefs）。
- **error**：不可恢复错误（对外 `ErrorResponse` 同构摘要：`code/message/requestId/retryable/details?`，其中 message 必须英文）。
- **预留**：`approval`、`write_operation`（L4）。
- **补充**：`auth.denied`、`rbac.denied`、`guardrail.hit`、`data.masked`（已存在或契约要求）。

### 2.4 脱敏与摘要口径（Data Protection）
- **必须脱敏**：`actionSummary`、`resultSummary`、`details`（如落库）。
- **严禁落库**：token/secret/password/连接串/Authorization/Cookie/原始 SQL/大结果集 rows/堆栈。
- **建议可追溯摘要字段**：
  - tool args：仅保留字段名、数量、范围等摘要；
  - response：仅保留“返回条数/字段集合/耗时/evidenceRefs 数量”等；
  - query：保留 query 文本的 digest（sha256/length）或按产品要求保留简短摘要（需严格红线）。

### 2.5 需要新增/修改的文件（规划）
- **后端模型与类型**：
  - `backend/gangqing/common/audit_event_types.py`：补齐事件类型枚举与命名对齐（注意与 contracts 的点分风格如 `api.response` 的一致性）。
  - `backend/gangqing_db/audit_log.py`：扩展 `AuditLogEvent` 字段以支持更正链路与更完整的事件口径（仅规划）。
- **契约文档（若需要补齐命名/字段）**：
  - `docs/contracts/api-and-events-draft.md`：在 “4 Audit Event” 中明确 `tool.call/tool.result/response/error` 的 eventType 取值与字段映射（仅规划，是否修改由任务拆分决定）。

## 3. Task 17.2：落库与 append-only 不可篡改策略

### 3.1 目标
- 在“应用层 + DB 权限”两层同时确保审计不可篡改，并定义“更正只能追加”的机制与证据链。

### 3.2 DB 层不可篡改（现状确认 + 验证点）
- **触发器阻断 UPDATE/DELETE**：已在 `audit_log_p0` 生效；计划补充验收：
  - 使用真实 Postgres 连接，以应用角色尝试 UPDATE/DELETE 应失败，并返回可审计的错误（错误 message 英文）。
- **DB 角色最小权限**：现状 `gangqing_app` 有 SELECT+INSERT；`gangqing_auditor` SELECT。
  - 计划明确：
    - 生产建议：应用账号仅 INSERT + 受控 SELECT（若 audit API 复用应用账号读取审计）；
    - 或引入专用只读账号执行审计读取（如果希望更强隔离）。

### 3.3 应用层 append-only 约束
- **禁止任何 update/delete 的数据访问接口**：所有审计写入仅暴露 “append” 方法（现有 `insert_audit_log_event` 即 append-only）。
- **更正/补录**：
  - 不允许修改原事件；必须追加新事件；
  - 新事件通过 `supersedesEventId` 指向原事件；同时建议同一更正链路共享 `correlationId`。

### 3.4 索引与查询性能（按 contracts 的检索诉求）
- 已有：
  - `tenant_id/project_id/request_id/timestamp`
  - `tenant_id/project_id/timestamp`
  - `tenant_id/project_id/event_type/timestamp`
- 若引入更正链路字段：建议增加（规划）：
  - `tenant_id/project_id/correlation_id/timestamp`
  - `tenant_id/project_id/supersedes_event_id`

## 4. Task 17.3：审计查询 API 与二次审计（Query Is Audited）

### 4.1 目标
- 设计/固化审计查询接口的请求/响应契约（Pydantic），并确保每次查询行为本身产生新的审计事件（成功与失败都要写）。

### 4.2 API 形态（基于现有 `GET /api/v1/audit/events` 迭代）
- **继续使用列表分页响应**：`{ total, items }`（现状已符合）。
- **查询过滤（最小可用）**：
  - `requestId`（现状已支持）
  - `eventType`（建议补齐）
  - `start/end` 或 `since/until`（建议补齐，避免全表扫）
  - `userId`（可选；需谨慎权限）
- **导出/批量**：不在本任务强制实现，但需在计划中明确上限：
  - `limit` 最大值（现状 200），并在 capability 上区分 “read vs export”。

### 4.3 二次审计事件口径
- **事件类型**：建议新增 `audit.query`（或复用 `query` + resource 指向 audit endpoint；最终以契约为准）。
- **写入时机**：
  - 在查询执行完成后写入一条审计事件，包含：过滤条件摘要、limit/offset、返回条数摘要、耗时、是否发生脱敏命中、以及结果 success/failure。
  - 查询失败（DB 错误、权限错误、校验错误）同样写审计（其中 RBAC 拒绝已由 `require_capability` 记录；但 audit.query 自身仍建议记录“查询尝试”摘要，避免只有拒绝事件而缺少查询意图摘要）。
- **脱敏命中审计**：现有 `data.masked` 事件只在 masking hits 时写；计划明确其与 `audit.query` 的关系：
  - 推荐：`audit.query` 作为主事件；`data.masked` 作为补充事件（可选），用于统计策略命中。

### 4.4 受控读取与最小权限
- **必须 capability 校验**：继续使用 `audit:event:read`。
- **可选能力点**：`data:unmask:read` 控制 `unmask=true` 的行为（现状已实现并返回 FORBIDDEN）。
- **字段级安全**：即使具备 `audit:event:read`，仍默认返回脱敏后的 `actionSummary`；仅在 `unmask=true` 且有能力点时才返回更完整版本（需与 masking policy 对齐）。

## 5. RequestContext & Observability 对齐（requestId 全链路贯穿）

### 5.1 写入审计时的字段映射规则
- `RequestContext.request_id` -> audit `requestId`（强制）
- `tenant_id/project_id` -> audit `tenantId/projectId`（强制）
- `session_id`（若有） -> audit `sessionId`
- `user_id/role`（鉴权后） -> audit `userId/role`
- `stepId/toolCallId`：
  - 工具调用：来自编排层或工具封装层（若存在）；
  - 审计查询：可不填，但建议记录 `resource=/api/v1/audit/events`。

### 5.2 与 SSE 的对齐点
- SSE 错误与 tool.result failure 的 `payload.error` 必须同构 `ErrorResponse`。
- 审计中的 error 记录必须包含：`code` + **英文** `message`，并可按 `requestId` 关联到同次 SSE 链路。

## 6. 结构化错误（Structured Errors）与审计记录的对齐
- **对外**：统一 `ErrorResponse`（`code/message/details?/retryable/requestId`）。
- **审计内**：
  - `errorCode` 字段记录稳定错误码；
  - `actionSummary/resultSummary` 内可包含 `error.message`（必须英文，且需脱敏/裁剪）。

## 7. 交付物与文件清单（按仓库结构）

> 说明：本 Umbrella 阶段只做规划；下游子任务实施时按此清单逐项落盘。

### 7.1 后端（Backend）
- `backend/gangqing/common/audit_event_types.py`
  - 扩展事件类型枚举，补齐 `tool.result/response/error/audit.query` 等口径（以最终契约为准）。
- `backend/gangqing/common/audit.py`
  - 补齐写入便捷函数（如 `write_tool_result_event` / `write_response_event` / `write_error_event` / `write_audit_query_event` 的边界定义）。
- `backend/gangqing_db/audit_log.py`
  - 扩展 `AuditLogEvent` Pydantic 模型以支持更正链路字段（`correlationId/supersedesEventId`），并确保所有摘要字段脱敏。
- `backend/gangqing_db/audit_query.py`
  - 扩展查询过滤字段（时间范围/eventType 等）与排序策略；确保按 scope 过滤；并为 audit API 提供所需查询能力。
- `backend/gangqing/api/audit.py`
  - 在 `GET /audit/events` 中增加“二次审计”写入点；并明确 unmask 权限与 masking hit 的审计策略。

### 7.2 数据库迁移（Migrations）
- `backend/migrations/versions/*_extend_audit_log_for_corrections.py`（规划）
  - 为更正链路新增字段与索引（若决定引入）。
  - 验证 `upgrade -> downgrade -> upgrade` 仍成功（遵循项目回滚验证规范）。

### 7.3 文档与契约（Docs）
- `docs/contracts/api-and-events-draft.md`（规划）
  - 明确 audit eventType 枚举与字段映射（尤其 `tool.call/tool.result/response/error/audit.query`）。
  - 明确“更正只能追加”的字段命名（`supersedesEventId` 或等价字段）。

## 8. Verification Plan（验收与测试计划）

### 8.1 自动化测试（必须真实集成，不得 skip）
- **Unit**：`pytest -q`
  - 覆盖点（至少）：
    - 审计事件 Pydantic 校验（必填字段/别名映射）。
    - 脱敏：敏感 key 命中必须被替换为 `[REDACTED]`。
    - 二次审计：调用审计查询逻辑后应产生新的审计事件（成功与失败各至少 1 条）。
    - 结构化错误：审计记录中的 error message 必须英文且可检索。
- **Smoke**：`backend/scripts/audit_log_smoke_test.py`
  - 覆盖点（端到端，真实 FastAPI + 真实 Postgres）：
    - 写入审计事件成功（包含 `requestId/tenantId/projectId`）。
    - 查询审计事件成功，并验证查询行为本身产生二次审计事件。
    - RBAC 拒绝与结构化错误返回（`FORBIDDEN/AUTH_ERROR`），并验证 `rbac.denied/auth.denied` 审计存在。
    - append-only：尝试对 audit_log 执行 UPDATE/DELETE 必须失败（如脚本具备 DB 直连能力）。

### 8.2 验收通过判定标准（Definition of Done for Task 17）
- **覆盖面**：审计写入覆盖 `query/tool.call/tool.result/response/error`，并预留 `approval/write_operation`。
- **二次审计**：任意审计查询都会写入审计事件（成功/失败均记录）。
- **append-only**：应用层无 update/delete；DB 层 trigger + 最小权限有效。
- **RBAC**：审计读取受控；越权返回结构化错误且写审计。
- **requestId 贯穿**：HTTP -> 编排 -> 工具 -> SSE -> 审计可按 `requestId` 回溯。
- **数据保护**：审计摘要与错误 details 均脱敏，不出现密钥/token/连接串/原始大对象。

## 9. 风险与决策点（需在子任务开始前确认）
- **审计事件命名风格一致性**：现有 `AuditEventType` 同时存在 `api.response` 与 `tool_call` 等风格，需统一为 contracts 口径（建议点分 + 关键域前缀）。
- **对外契约与 DB 字段映射**：是否对外暴露 `eventId`（=DB `id`）与更多字段，需在 contracts 中明确。
- **审计 query 的内容保留程度**：是否允许存储 query 明文；若允许，需明确脱敏/裁剪与合规边界；默认建议仅存 digest。
