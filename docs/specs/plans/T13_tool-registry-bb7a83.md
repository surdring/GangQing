# Task 13：编排层工具链注册与 Function Calling（可控调用 + 可追溯证据）执行蓝图

本计划通过“工具注册表 + 工具白名单门禁 + SSE 工具生命周期事件 + 审计/Evidence 绑定”四件套，落实 Task 13 的可控工具调用与可追溯证据链，并以 `docs/contracts/api-and-events-draft.md` 为对外契约权威来源。

## 0. 权威参考与对齐基线

- 权威契约：`docs/contracts/api-and-events-draft.md`
- 需求/TDD：`docs/requirements.md`（R15.3）、`docs/design.md`（2.5.3/3.5.1/3.9）
- 现状实现（只读核对结果）：
  - 前端 Zod：`web/schemas/sseEnvelope.ts`、`web/schemas/errorResponse.ts`、`web/schemas/evidence.ts`
  - 后端 Pydantic：`backend/gangqing/schemas/sse.py`、`backend/gangqing/common/errors.py`、`backend/gangqing/common/context.py`
  - 工具执行与重试：`backend/gangqing/tools/runner.py`（参数校验/契约校验/重试/审计）
  - SSE 发射点：`backend/gangqing/api/chat.py`（已输出 `tool.call/tool.result/error/final` 的雏形）
  - 意图路由与 tool allowlist 雏形：`backend/gangqing/agent/routing.py`
- 外部最佳实践（用于决策理由，不作为权威契约）：
  - SSE 可靠性（心跳、事件 id/sequence、sentinel/终止事件）：Speakeasy SSE OpenAPI 指南
  - EventSource 重连语义与 `Last-Event-ID`：javascript.info SSE 文档
  - 审计：事件采集层（emitters）+ 追加写（append-only）+ 可验证链路：Audit Trails for Accountability in LLMs（arXiv:2601.20727）

## 1. 范围与非目标（Task 13 边界）

### 1.1 范围（必须交付）

- 工具注册机制（声明式注册 + 配置化启用/禁用）
- 可用工具集合门禁（role + intent + data_domain）与服务端强制校验
- SSE：工具调用生命周期事件（`tool.call`/`tool.result`）与错误/终止事件（`error`/`final`）的**序列约束**
- 工具调用与 Evidence / 审计 / `requestId` 绑定（可检索、可导出）

### 1.2 非目标（本任务不做或仅做预留）

- 不实现具体业务工具逻辑（仅定义注册/元信息/门禁/事件/验收口径）
- 写操作的真实执行（L4 才允许）；但本任务需保证“写工具”即使注册也**不能被模型直接执行**

## 2. 核心不变式（必须满足的系统级约束）

- **Read-Only Default**：除 L4 治理链路外，任何写意图都必须阻断或仅生成草案
- **Tool Allowlist**：工具集合必须由“角色 + 意图 + 数据域”决定；禁止模型任意调用
- **Schema 单一事实源**：
  - 前端：Zod 校验 SSE/对外 I/O
  - 后端：Pydantic 校验工具参数、工具输出、Evidence、审计事件
- **错误结构化且英文 message**：对外 `ErrorResponse`/SSE `error` 的 `message` 必须英文
- **Evidence-First**：数值/关键建议必须绑定 Evidence；证据缺失必须降级并发 `warning`
- **RBAC & Audit**：所有工具与接口必须做 RBAC，且审计事件贯穿 `requestId`

## 3. 目标架构（逻辑分层与数据流）

### 3.1 组件与职责

- **Tool Registry（编排层唯一可信来源）**
  - 枚举所有工具（含 disabled/写工具）
  - 提供工具元信息（能力边界、参数模型引用、超时/重试、脱敏策略、只读/写标记、数据域标签）
  - 提供“按门禁过滤后的 allowed tools”计算输入

- **Tool Gate（门禁计算与强制校验）**
  - 计算 `allowedToolNames`：输入 `RequestContext + intent + data_domain + registry`
  - 运行时强制校验：任何 tool call 前必须校验“在 allowed list 内”

- **Tool Runner（统一执行包装器）**
  - 统一完成：参数 Pydantic 校验、RBAC、超时/重试、输出契约校验、审计、可观测字段绑定

- **SSE Emitter（事件发射点/序列管理）**
  - 统一 envelope（`type + timestamp + requestId + tenantId + projectId + sessionId? + sequence + payload`）
  - 输出 `tool.call`/`tool.result`/`error`/`final` 并满足序列约束

- **Evidence Binder（Evidence 引擎绑定点）**
  - 工具返回结果必须带 Evidence 或 Evidence 引用（`toolCallId` 关联）

### 3.2 关键数据流（成功与失败）

- **成功路径**
  - `meta(seq=1)`
  - （可选）`intent.result`、`routing.decision`
  - `tool.call`（每次 attempt 开始）
  - `tool.result(status=success)`（每次 attempt 结束）
  - （可选）`evidence.update`（工具产生证据后）
  - `final(status=success)`

- **失败路径（不可恢复）**
  - 任意阶段失败 => 尽快 `error(payload=ErrorResponse)`，随后 `final(status=error)`，**final 后不得再输出事件**

## 4. 契约与 Schema 设计（对外与内部）

### 4.1 SSE 事件契约（必须以 contracts 为准）

- 对外契约以 `docs/contracts/api-and-events-draft.md` 第 2.1.0.* 与第 6.1 章为准
- 本任务需要确保后端 `backend/gangqing/schemas/sse.py` 与前端 `web/schemas/sseEnvelope.ts` 对齐：
  - **事件类型最小集合**：`meta/progress/tool.call/tool.result/warning/error/final`（以及现状已有的 `intent.result/routing.decision/draft.created`）
  - **字段命名**：对外 JSON 使用 camelCase（后端通过 Pydantic alias 输出）
  - **sequence**：单连接内单调递增（不重复、不回退）

### 4.2 `tool.call`/`tool.result` payload（Task 13 必须强化点）

contracts 当前对 `tool.call` 要求：`toolCallId/toolName/argsSummary`；对 `tool.result` 要求：`toolCallId/toolName/status` + 可选 `resultSummary/error/evidenceRefs`。

现状代码中：
- 后端 `SseToolCallPayload`/`SseToolResultPayload` 只有 `toolName/attempt/maxAttempts/error?`，缺少 `toolCallId/argsSummary/resultSummary/evidenceRefs`
- 前端 Zod `SseToolCallPayloadSchema`/`SseToolResultPayloadSchema` 同样缺少 `toolCallId/argsSummary/resultSummary/evidenceRefs`

**本任务计划口径（不写实现，仅定义必补字段与验收）**：
- `toolCallId`：每次工具调用的稳定 id（跨 attempt 共享或 attempt 级 id 需在计划中明确；推荐“toolCallId=一次工具调用会话 id，attempt 在 payload 单独表达”）
- `argsSummary`：**脱敏**参数摘要（禁止原文 SQL、token、密码、原始数据行）
- `resultSummary`：脱敏结果摘要（例如行数、聚合值范围、返回 evidence 数量）
- `evidenceRefs`：`evidenceId[]`，用于前端关联证据面板

### 4.3 ErrorResponse（强制同构）

- 以 `docs/contracts/api-and-events-draft.md` 2.1.* 为准
- SSE `type=error` 的 `payload` 必须是 ErrorResponse
- `message` 必须英文

### 4.4 Evidence 契约（工具 -> Evidence 绑定字段）

- Evidence 最小字段以 contracts 第 3 章为准（`evidenceId/sourceSystem/sourceLocator/timeRange/confidence/validation` 等）
- 与工具绑定字段：
  - Evidence 中 `toolCallId?`
  - `tool.result.payload.evidenceRefs[]`
- 降级规则：证据缺失/不可验证必须输出 `warning(code=EVIDENCE_MISSING/EVIDENCE_MISMATCH/...)`，最终回答不得伪装为确定性结论

## 5. Tool Registry 设计规范（Task 13.1）

### 5.1 注册模式（声明式 + 配置化启用）

- **声明式注册（推荐主路径）**
  - 通过装饰器或声明对象定义工具元信息
  - 注册时写入 registry（进程内单例或模块级 registry）

- **配置化启用/禁用（强制）**
  - 工具是否可用必须由配置控制（环境变量或配置文件）
  - 配置缺失/非法 => 启动快速失败（英文错误）

### 5.2 工具元信息（后端 Pydantic 单一事实源）

每个工具元信息最小字段建议：
- **identity**：`toolName`（稳定）、`version?`（可选）
- **io_contract**：`ParamsModelRef`、`ResultModelRef`、`output_contract_source`（契约校验来源字符串）
- **governance**：
  - `isReadOnly`（强制）
  - `requiresApproval`（写工具强制 true）
  - `requiredCapabilities[]`（RBAC）
  - `dataDomains[]`（数据域标签）
- **execution_policy**：默认超时、最大超时、重试策略、并发限制（若有）
- **redaction_policy**：参数/结果摘要脱敏规则 id
- **observability**：事件/审计字段映射（toolName、阶段、attempt、durationMs、status）

### 5.3 工具分类与“写工具”治理

- registry 允许登记写工具（用于能力展示与 L4 草案/审批链路），但：
  - 在 L1/L2/L3 的 `route_intent` 与 allowed tool gate 中必须禁止进入执行路径
  - 任何写意图必须映射为 `GUARDRAIL_BLOCKED` 或 `draft`（以现有 routing 约束为准）

## 6. Tool Gate 设计规范（Task 13.3）

### 6.1 输入/输出与决策可观测

- 输入：
  - `RequestContext`（至少 `requestId/tenantId/projectId/userId?/role?/stepId?`）
  - `intent`（见现状 IntentType：QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）
  - `data_domain`（本任务需定义“数据域枚举的权威来源”；若当前仓库未定稿，必须在计划中给出落地路径：后端 Pydantic + 前端 Zod 同步）
  - `tool_registry`

- 输出：
  - `allowedToolNames[]`
  - `blockedReasonCode?`（不泄露敏感策略细节）
  - `auditTags`（现状已有：intent/riskLevel/hasWriteIntent）

### 6.2 强制校验点（服务端）

- **双层门禁**：
  - 路由层：先算 allowlist（例如 `routing.decision.payload.allowedToolNames`）
  - 执行层：tool runner 再次校验“请求调用的 toolName 在 allowlist 内”

- **拒绝映射**：
  - 不在 allowlist => `FORBIDDEN`（或 contracts 约定的码）
  - 跨域/隔离失败 => `AUTH_ERROR`/`FORBIDDEN`（按 contracts 与现有实现一致）
  - 写意图 => `GUARDRAIL_BLOCKED`

### 6.3 审计要求

- 记录：
  - 决策输入摘要（role/intent/data_domain/候选工具数量，不记录敏感原文）
  - 决策输出摘要（allowedToolNames、blockedReasonCode）
  - 关联 `requestId/tenantId/projectId/stepId`

## 7. Tool Call Streaming（Task 13.2）：SSE 事件与序列约束

### 7.1 序列与终止语义（强制）

- `meta` 必须是首事件（`sequence=1`）
- `sequence` 单连接单调递增
- `final` 必须是最后一个事件
- 不可恢复错误：必须输出 `error`，并紧随 `final(status=error)`

### 7.2 工具事件（tool.call / tool.result）触发时机

- `tool.call`：每次 attempt 开始前输出（用于前端展示“正在调用某工具，第几次尝试”）
- `tool.result`：每次 attempt 结束后输出
  - success：`status=success`，可带 `resultSummary` + `evidenceRefs`
  - failure：`status=failure`，必须带 `error: ErrorResponse`

### 7.3 可靠性增强（建议项；以不破坏 contracts 为前提）

结合 SSE 最佳实践（Speakeasy/javascript.info）：
- **心跳/保活**：长耗时场景可输出轻量 `progress` 或新增 `ping` 类型（若新增需先补 contracts，再同步前端/后端 schema）
- **去重/续传**：浏览器原生 EventSource 支持 `id/Last-Event-ID`，但当前后端以 `POST /chat/stream` + StreamingResponse 为主；
  - 本任务可先以 `sequence` 做“乱序/丢包检测”，续传作为后续任务（若要做续传必须引入服务端事件缓存或可重放存储）
- **sentinel/终止**：GangQing 已用 `final` 作为终止哨兵事件，满足“sentinel event”最佳实践

## 8. 审计与证据链绑定（RBAC & Audit）

### 8.1 审计事件字段（最小集合）

以 `docs/contracts/api-and-events-draft.md` 第 4 章为准，并结合现状 `backend/gangqing/common/audit.py`：
- `eventType=tool_call`
- `resource=toolName`
- `actionSummary`：至少包含 `toolName`、`argsSummary`（脱敏）以及 attempt/durationMs/timeoutMs 等
- `result`：success/failure + errorCode
- `evidenceRefs?`：`evidenceId[]`

### 8.2 追加写与可验证性（建议增强）

参考审计最佳实践（arXiv）：
- 存储层建议具备 append-only 语义（现阶段可先保证“逻辑追加写”与权限控制）
- 后续可引入 hash chain/签名以实现可篡改检测（不作为本任务强制验收，但可在计划中列为架构演进点）

## 9. 配置化与环境变量（必须外部化）

### 9.1 Registry/Gate/Runner 相关配置项（建议清单）

- `GANGQING_TOOL_REGISTRY_ENABLED`：总开关
- `GANGQING_TOOL_ENABLED_LIST` / `GANGQING_TOOL_DISABLED_LIST`：按 toolName 控制启停（优先级规则在实现阶段确定）
- `GANGQING_TOOL_DEFAULT_TIMEOUT_SECONDS` / `GANGQING_TOOL_MAX_TIMEOUT_SECONDS`
- `GANGQING_TOOL_MAX_RETRIES`、`GANGQING_TOOL_BACKOFF_*`
- `GANGQING_CONTRACT_VALIDATION_STRICT`（现状已有）
- `GANGQING_AUDIT_ASYNC_ENABLED`（现状已有）
- （若引入 data_domain）`GANGQING_DATA_DOMAIN_POLICY_JSON`：role/intent/domain -> tools 的策略配置

约束：禁止硬编码 URL/端口/超时/重试等；缺关键配置必须快速失败且 message 英文。

## 10. 目录结构与文件落点（交付物定义）

> 仅定义结构与职责；实现阶段再按计划修改。

建议新增/调整的模块边界（以 `backend/gangqing/tools/` 为核心）：
- `backend/gangqing/tools/registry.py`
  - registry 单例、注册 API、按配置过滤、查询元信息
- `backend/gangqing/tools/metadata.py`
  - 工具元信息 Pydantic 模型（ToolMetadata/ToolPolicy/RedactionPolicyRef 等）
- `backend/gangqing/tools/gate.py`
  - allowed tools 计算（role + intent + data_domain）与拒绝原因规范化
- `backend/gangqing/tools/runner.py`
  - 继续作为统一 runner；补齐 toolCallId、argsSummary/resultSummary/evidenceRefs 贯穿点
- `backend/gangqing/schemas/sse.py`
  - 对齐 contracts：补齐 `tool.call`/`tool.result` payload 字段
- `web/schemas/sseEnvelope.ts`
  - 对齐 contracts：补齐 `tool.call`/`tool.result` payload 字段

## 11. 验收口径（Verification Plan）

### 11.1 单元测试（pytest -q，禁止 skip）

必须覆盖（建议最少集合）：
- **Registry**
  - 工具可枚举（含 enabled/disabled）
  - 配置错误 => 快速失败（英文 message）
- **Gate（role+intent+data_domain）**
  - allow：正确输出 allowedToolNames
  - deny：不在白名单 => `FORBIDDEN`（或 contracts 约定码）
  - write intent：`GUARDRAIL_BLOCKED` 或进入 draft（按 routing 策略）
- **Runner**
  - 参数校验失败 => `VALIDATION_ERROR`
  - 输出契约不符 => `CONTRACT_VIOLATION`
  - RBAC 失败 => `FORBIDDEN` 且有审计事件
- **SSE 序列约束**
  - `meta` 首事件、`final` 末事件
  - `error` 后必须紧随 `final(status=error)`
  - `sequence` 单调递增
- **tool.* 事件契约**
  - `tool.call`/`tool.result` 必填字段完整（含 `toolCallId/argsSummary/resultSummary/evidenceRefs` 口径）

### 11.2 冒烟测试（真实服务，禁止 mock）

- 必须脚本：`backend/scripts/tool_registry_smoke_test.py`
  - **成功链路**：启动 FastAPI + 真实 Postgres；发起一次 chat stream
    - 观察 SSE：包含 `tool.call`/`tool.result` 且 `final(success)`
    - 观察 evidence：至少返回 `evidenceRefs` 或后续 `evidence.update`
  - **失败链路**：触发一次拒绝或校验失败
    - SSE：`error(ErrorResponse)` + `final(error)`
    - 审计：可按 `requestId` 查询到 tool_call 或 rbac_denied/routing.decided 事件

### 11.3 契约一致性验收（强制）

- 任何对外 SSE 事件字段必须与 `docs/contracts/api-and-events-draft.md` 一致
- 如果本任务需要补齐 `tool.call/tool.result` 字段（现状缺口），必须：
  - 先更新 contracts（若需）
  - 同步更新后端 Pydantic schema 与前端 Zod schema
  - 增加契约测试（前端/后端均校验）

## 12. 风险与约束清单（计划阶段显式声明）

- **contracts 与现状 schema 不一致风险**：当前 `tool.call/tool.result` 字段与 contracts 有差异，必须在实现前收敛到 contracts
- **data_domain 未定稿风险**：若仓库尚无权威枚举/策略文件，本任务需补齐“数据域枚举与策略配置”作为门禁输入的单一事实源
- **POST SSE 续传限制**：浏览器 EventSource 的 `Last-Event-ID` 语义主要用于 GET；当前实现为 POST streaming，续传/重放需额外设计（不作为本任务强制）

## 13. Milestones（2-5 个里程碑）

1) **Registry 规范定稿**：工具元信息模型、注册/启停策略、只读/写治理标记
2) **Gate 规范定稿**：role+intent+data_domain -> allowedToolNames 的输入输出与拒绝映射
3) **SSE 工具事件对齐 contracts**：`tool.call/tool.result/error/final` 字段与序列约束验收用例
4) **Evidence/Audit 绑定规范**：toolCallId/evidenceRefs/requestId 贯穿与审计字段脱敏规范
5) **验收脚本与测试口径**：pytest + tool_registry_smoke_test 通过

