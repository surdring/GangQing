# T09 工具参数 schema 校验与契约校验（Pydantic 单一事实源）执行计划

本计划通过在“工具调用边界/对外输出边界”建立统一的 Pydantic 校验、结构化错误映射、审计留痕与契约测试门禁，系统性避免工具链与流式输出的契约漂移。

## 0. 背景与权威参考

- **PRD**：`docs/requirements.md`（R8.2 工具参数校验 / R9.3 输出结构化校验 / R6.3 SSE 错误流式处理）
- **TDD**：`docs/design.md`（第 6 章错误处理 / 第 7 章测试策略 / 3.5 SSE 规则）
- **Contracts**：`docs/contracts/api-and-events-draft.md`（ErrorResponse、SSE Envelope、事件序列与 `details` 脱敏约束）
- **Security**：`docs/security/error-details-redaction.md`
- **OpenAPI**：`docs/api/openapi.yaml`

## 1. 当前实现盘点（用于确定改造边界）

### 1.1 后端：工具调用与契约校验已具备的“骨架”

- **工具调用统一入口（边界点）**：`backend/gangqing/tools/runner.py::run_readonly_tool`
  - 入参：`tool.ParamsModel.model_validate(raw_params)`
  - 输出：`tool.ResultModel.model_validate(payload)`
  - 错误码：
    - 入参校验失败 -> `build_validation_error(...)` -> `VALIDATION_ERROR`
    - 输出校验失败 -> `build_contract_violation_error(...)` -> `CONTRACT_VIOLATION`
  - 审计：失败/成功都会 `write_tool_call_event(...)`，并携带 `stage`（`tool.params.validate` / `tool.output.validate` / `tool.execution`）

- **统一错误模型（对外）**：`backend/gangqing/common/errors.py`
  - `ErrorResponse`：`code/message/details?/retryable/requestId`（其中 `request_id` 用 alias `requestId`）
  - `build_validation_error` / `build_contract_violation_error`：已生成 `details.fieldErrors[]` + `details.errorCount`，并为 contract violation 包含 `details.source`

- **SSE Envelope（后端）**：`backend/gangqing/schemas/sse.py`
  - 结构：顶层 `type + envelope + payload`
  - `SseErrorEvent.payload` 为 `ErrorResponse`

- **审计落库（后端）**：`backend/gangqing/common/audit.py` -> `backend/gangqing_db/audit_log.py`
  - 先 masking（角色脱敏策略），再 `redact_sensitive(...)` 递归脱敏后落库
  - 审计事件包含 `requestId/tenantId/projectId/sessionId/userId/role/resource/actionSummary/result/errorCode/evidenceRefs`（满足契约最小字段集合）

- **对外 REST 错误（后端）**：`backend/gangqing/app/main.py`
  - `AppError` -> `ErrorResponse` + HTTP status mapping
  - `RequestValidationError`（FastAPI/Pydantic 请求体校验）-> 当前返回 `ErrorResponse(code=VALIDATION_ERROR, message="Validation error")`（HTTP 422）

### 1.2 前端：Zod schema 现状与“漂移风险”

- `web/schemas/errorResponse.ts`：已定义 `ErrorResponseSchema`，形状与后端一致（顶层字段一致）。
- `web/schemas/sseEnvelope.ts`：**当前以扁平结构定义**（顶层直接含 `timestamp/requestId/.../payload`），与后端/契约草案的 **`envelope` 嵌套结构不一致**，属于高风险漂移点。

结论：Task 9 的核心不在“从零实现”，而在**把现有骨架收敛为统一机制 + 配置化 + 契约门禁**，并修复前后端事件 envelope 的一致性。

## 2. 总体目标与不变式（Task 9 范围）

- **Pydantic 单一事实源（后端强制）**：
  - 工具 Params/Result、对外 REST response、SSE event payload、Evidence、审计事件均必须由 Pydantic 模型定义与校验。
- **Zod 对齐（前端强制）**：
  - 对外 I/O 与 SSE 事件解析必须用 Zod schema 校验，且 shape 与后端 Pydantic 对齐。
- **结构化错误（强制）**：
  - 入参无效 -> `VALIDATION_ERROR`
  - 输出不符合契约 -> `CONTRACT_VIOLATION`
  - 对外错误统一 `ErrorResponse`：`code + message(英文) + requestId + retryable + details?`
- **RBAC & Audit & requestId 贯穿（强制）**：
  - 任一校验失败都必须写审计（含 `requestId`、`toolName`、`stage`、`stepId` 若有）。
  - `details` 与审计摘要必须脱敏，**禁止敏感信息**。
- **配置外部化（强制）**：
  - 严格模式、最大 field errors 数、输出校验策略、脱敏敏感 key 片段扩展等必须可配置。
- **真实集成测试（No Skip）**：
  - 冒烟/集成必须连接真实 FastAPI + Postgres + llama.cpp；缺配置直接失败（英文）。

## 3. 统一机制设计：校验边界与责任划分（避免“工具内部各自为政”）

### 3.1 责任边界（必须明确）

- **API Handler 层（HTTP 入站边界）负责**：
  - RequestContext 构建与 scope headers 校验（`tenantId/projectId/requestId`）
  - REST 请求体的 Pydantic 校验失败统一映射为 `ErrorResponse(code=VALIDATION_ERROR)`
  - 把 `requestId` 写入响应 header（`X-Request-Id`）

- **工具运行时（Tool Invocation Boundary）负责**：
  - 在调用任何工具业务逻辑前，统一执行 `ParamsModel.model_validate(raw_params)`
  - 把 `ValidationError` 统一映射为 `AppError(VALIDATION_ERROR)`
  - 对 Params 校验失败写审计（`tool_call`），`stage=tool.params.validate`
  - 在工具业务逻辑成功返回后，统一执行 `ResultModel.model_validate(...)`
  - 把输出契约违规统一映射为 `AppError(CONTRACT_VIOLATION)`
  - 对 output 校验失败写审计（`stage=tool.output.validate`）

- **对外输出封装器（Output Boundary）负责**：
  - REST：在返回前确保响应对象符合 Pydantic response model（必要时 `model_dump`/`model_validate`）
  - SSE：发送事件前保证 `SseEvent`、`SseEventEnvelope`、对应 payload model 全部可序列化且可校验
  - SSE 出错时：必须输出 `error`（payload 为 `ErrorResponse`）并紧随 `final(status=error)`

- **工具实现函数/类内部（禁止承担的责任）**：
  - 不允许每个工具“自己决定是否校验/如何映射错误/是否审计”。
  - 工具内部可以做业务校验，但**对外错误形态**必须交给统一映射机制收敛为 `AppError -> ErrorResponse`。

### 3.2 “统一校验管线”阶段模型（用于审计与排障）

- **tool.params.validate**：raw -> ParamsModel
- **tool.rbac**：capability check
- **tool.execution**：业务执行（含重试 attempt 信息）
- **tool.output.validate**：ResultModel
- **api.response.validate**：REST response 输出校验（适用时）
- **sse.event.validate**：SSE event 输出校验（适用时）

要求：上述阶段名出现在审计 `actionSummary.argsSummary.stage` 或等价字段中，以便可检索与统计。

## 4. 字段级对齐：统一错误模型 + SSE error 载荷 + REST 错误响应

### 4.1 统一错误模型（唯一对外形态）：`ErrorResponse`

权威字段（后端 Pydantic / 前端 Zod 必须一致）：

- `code: string`（稳定码，必填）
- `message: string`（**英文**，必填）
- `retryable: boolean`（必填）
- `requestId: string`（必填）
- `details?: object | null`（可选，必须通过脱敏与 allow-list 约束）

### 4.2 REST 错误响应对齐规则（强制）

- 任意非 2xx：响应体必须为 `ErrorResponse`（禁止裸字符串/HTML）
- HTTP status mapping 以 `docs/contracts/api-and-events-draft.md#2.1.2` 为准
- 必须回传 header：`X-Request-Id`（与 body `requestId` 一致）

### 4.3 SSE `error` 事件对齐规则（强制）

- SSE `type=error`：`payload` **必须**是 `ErrorResponse`（字段同上）
- SSE `type=tool.result` 且 `status=failure`：`payload.error` **必须**是 `ErrorResponse`（同构）
- SSE 错误事件序列：`meta`（首） -> ... -> `error` -> `final(status=error)`（末）

### 4.4 `details` 允许字段形状（对外与审计摘要共用口径）

遵循 `docs/contracts/api-and-events-draft.md#2.1.3` 与 `docs/security/error-details-redaction.md`。

- **允许 keys（建议最小化）**：
  - `reason?: string`
  - `source?: string`（契约来源标识，如 `tool.postgres_readonly.result`）
  - `capability?: string`（RBAC 拒绝时可用于检索）
  - `durationMs?: number`
  - `fieldErrors?: Array<{ path: string; reason: string }>`
  - `errorCount?: number`
  - `stage?: string`（可选：仅用于审计/内部；**对外是否允许**需在本任务中做一致性决策，默认不建议对外输出）

- **明确禁止（MUST NOT）**：
  - 任何凭证/密钥：`password/secret/token/api_key/authorization/cookie` 等（递归 key 片段命中即 `[REDACTED]`）
  - 原始 SQL、完整 rows、连接串/内网 host:port、traceback/堆栈、上游响应正文
  - `tenantId/projectId/userId/role/sessionId` 等上下文字段（这些应只出现在 SSE envelope / 审计 / 结构化日志中，不出现在对外 ErrorResponse.details）

## 5. Pydantic 单一事实源：模型分层与落点规划

### 5.1 推荐目录结构（后端）

- `backend/gangqing/common/errors.py`
  - 对外 `ErrorResponse`
  - `AppError`（内部异常载体）
  - `build_validation_error` / `build_contract_violation_error`

- `backend/gangqing/schemas/sse.py`
  - `SseEventEnvelope`（envelope 单一事实源）
  - `SseErrorEvent`（payload=ErrorResponse）
  - 逐步扩展 `tool.call/tool.result/warning/progress/final` 的 payload 模型（建议使用 Pydantic discriminated union，但保持与现有结构兼容）

- `backend/gangqing_db/evidence.py`
  - Evidence 单一事实源（已存在）

- `backend/gangqing_db/audit_log.py`
  - `AuditLogEvent` 单一事实源（已存在）

- `backend/gangqing/tools/*`
  - 每个工具必须声明：`ParamsModel`、`ResultModel`、`required_capability`、`output_contract_source`

### 5.2 工具契约清单（本任务至少覆盖 L1 核心工具）

- `PostgresReadOnlyQueryTool`
  - Params：`PostgresReadOnlyQueryParams`
  - Result：`PostgresReadOnlyQueryResult`（内嵌 `Evidence`）
  - 输出契约 source：`tool.postgres_readonly.result`

后续扩展工具必须遵循同一模式（不在本计划阶段实现具体新工具）。

## 6. 配置外部化（校验开关、严格模式、脱敏策略、max errors）

### 6.1 需要配置化的开关/参数（建议最小集合）

- **最大字段错误数**（用于 `fieldErrors` 截断）：
  - `GANGQING_CONTRACT_VALIDATION_MAX_FIELD_ERRORS`（默认 20）

- **输出契约校验严格度**（用于输出前是否强制校验所有事件/响应）：
  - `GANGQING_CONTRACT_VALIDATION_STRICT_MODE`（`true|false`，默认 true）

- **是否允许输出校验降级**（当发生非关键字段缺失时是否可以“降级”而非直接 error）：
  - `GANGQING_CONTRACT_VALIDATION_ALLOW_DEGRADED_OUTPUT`（默认 false；若启用需定义降级规则清单）

- **脱敏敏感 key 片段扩展**：
  - `GANGQING_REDACTION_SENSITIVE_KEY_FRAGMENTS`（逗号分隔；补齐到 `.env.example`）

> 说明：当前后端已有 `redact_sensitive(...)` 且 `docs/security/error-details-redaction.md` 已要求该 env；本任务的重点是把它纳入统一 settings 校验与 fast-fail 机制。

### 6.2 配置缺失策略（强制）

- **关键配置缺失必须 fast-fail**（英文错误，不交互式询问）。
- 对测试脚本：缺少 `GANGQING_DATABASE_URL` / llama.cpp 地址等必须失败并输出明确英文信息。

## 7. 审计留痕与可观测性约束

### 7.1 审计事件最小字段集（必须满足 contracts）

- `requestId`、`tenantId`、`projectId`（强制）
- `resource`（工具名/接口 path）
- `result`（success/failure）
- `errorCode`（失败必填）
- `actionSummary.argsSummary.stage`（失败原因定位）

### 7.2 校验失败的审计规则（强制）

- 入参校验失败：必须写 `tool_call` 审计，`stage=tool.params.validate`。
- 输出契约失败：必须写 `tool_call` 审计，`stage=tool.output.validate`。
- REST 入参（RequestValidationError）：必须写 `api_response` 审计，并带上 `errorCode=VALIDATION_ERROR`。

### 7.3 details/摘要脱敏执行点（强制）

- 写审计前：递归脱敏（当前 `audit_log.insert_audit_log_event` 已做 `redact_sensitive(...)`）
- 对外输出前：任何来自异常上下文/上游的 `details` 都必须递归脱敏后再进入 `ErrorResponse.details`

## 8. 契约测试门禁（Task 9.3）

### 8.1 单元测试（pytest，必须覆盖）

覆盖点（最少）：

- `VALIDATION_ERROR`：
  - `ErrorResponse` 字段齐全：`code/message/requestId/retryable/details`
  - `message` 必须英文（稳定可检索）
  - `details.fieldErrors[]` shape 与最大条数截断规则

- `CONTRACT_VIOLATION`：
  - `details.source` 必须存在且稳定
  - `details.fieldErrors[]` shape

- **脱敏断言**：
  - 对外 `details` 与审计 `actionSummary` 均不包含禁止 key 片段（大小写不敏感）

### 8.2 真实集成冒烟测试（No Skip，必须覆盖）

- 复用并扩展现有：`backend/scripts/contract_validation_smoke_test.py`
  - 已覆盖：
    - Params missing -> `VALIDATION_ERROR`
    - 强制输出契约违规 -> `CONTRACT_VIOLATION`
    - 审计落库存在失败事件
    - 审计不泄露敏感关键词
  - 建议补齐：
    - 通过真实 FastAPI 启动后，对 `/api/v1/chat/stream` 触发一次 `tool.result(status=failure)`，断言 `payload.error` 同构 `ErrorResponse`
    - SSE 事件序列：`meta` 首事件、`final` 末事件、错误路径 `error` 紧随 `final(status=error)`

> 注意：冒烟测试必须连接真实 Postgres；llama.cpp 若在本任务链路未使用，可不强行依赖，但如设计要求“必须真实 llama.cpp”，则需在 CI/本地准备服务并由 env 提供地址，缺失即失败。

## 9. 文件改动清单（规划级，不在本阶段写实现）

> 以下为“应该改哪些文件/落点在哪”，不包含任何函数实现代码。

### 9.1 后端（backend/）

- `backend/gangqing/common/settings.py`
  - 新增 Task 9 相关配置项（max field errors / strict mode / allow degraded output / redaction fragments）并纳入 Pydantic settings 校验

- `backend/gangqing/common/errors.py`
  - 统一 `details` allow-list 输出策略（确保与 contracts + redaction 文档一致）
  - 统一英文 `message` 文案（稳定可检索）

- `backend/gangqing/schemas/sse.py`
  - 扩展并强制化 SSE 事件 payload 模型（至少覆盖 error/tool.result.failure 的 ErrorResponse 同构约束）

- `backend/gangqing/api/chat.py`
  - 使 `tool.call/tool.result` payload 字段与 contracts 对齐（例如 `toolCallId/argsSummary` 等）
  - 对 `tool.result(status=failure)` 的 `payload.error` 做 `ErrorResponse` 校验后输出

- `.env.example`
  - 补齐/更新 Task 9 配置项与说明（缺失必须 fast-fail）

### 9.2 前端（web/）

- `web/schemas/sseEnvelope.ts`
  - 修正为 contracts 形态：顶层 `type + envelope + payload`（当前为扁平结构，需对齐）
  - 扩展事件 schema 至最小集合（`meta/progress/tool.call/tool.result/message.delta/evidence.update/warning/error/final`），至少对 error 与 final 建立强校验

- `web/tests/contractSchemas.test.ts`
  - 添加前后端契约一致性断言（最小：ErrorResponse 与 SSE envelope shape）

## 10. 关键决策点（需要你确认/拍板）

- **SSE envelope 在前端是否以“嵌套 envelope”作为唯一形态**：
  - 决策：是。
  - 依据：后端 `backend/gangqing/schemas/sse.py` 已明确使用 `type + envelope + payload` 结构；前端当前 `web/schemas/sseEnvelope.ts` 为扁平结构，存在真实漂移风险。
  - 影响：前端 Zod schema 与解析逻辑应以嵌套 envelope 为唯一权威形态；扁平结构仅能作为过渡兼容策略（如保留，必须在契约中声明，否则视为契约漂移）。

- **`RequestValidationError` 的 `message` 文案**：
  - 决策：统一为英文稳定文案，且与工具侧 `Invalid tool parameters` 做语义对齐但不要求字面完全一致。
  - 依据：后端 `backend/gangqing/app/main.py` 当前固定返回 `"Validation error"`，文案过泛且与工具侧文案不一致，后续按日志/错误聚合检索会产生分裂。
  - 影响：应在实现阶段将 REST 入参校验错误的 `message` 收敛为一个稳定英文短语（建议：`Invalid request payload`），并保持 `code=VALIDATION_ERROR`、`details.fieldErrors[]` shape 不变。

- **是否允许输出校验降级（allow degraded output）**：
  - 决策：不允许（L1 强制严格）。
  - 依据：当前 `backend/gangqing/common/settings.py` 中不存在降级开关，且工具 runner 已将输出契约违规统一映射为 `CONTRACT_VIOLATION`；在没有明确降级规则清单与审计口径前，引入降级会带来契约歧义与证据链不可追溯风险。
  - 影响：实现阶段不引入 `ALLOW_DEGRADED_OUTPUT`，仅保留严格校验与明确失败（`CONTRACT_VIOLATION`）路径；如后续确有业务需要，必须新增独立任务，先定义降级规则与契约扩展，再实现。

## 11. 验收与交付物（对应你给的 Deliverables Definition）

- [ ] **Directory Structure**：本计划第 9 章
- [ ] **Environment Variables**：本计划第 6 章
- [ ] **API Contracts**：本计划第 4 章（REST/SSE 字段级对齐）
- [ ] **Tool Contracts**：本计划第 5.2 节（至少 Postgres tool）
- [ ] **Error Model**：本计划第 4.1~4.4 节
- [ ] **Audit**：本计划第 7 章
- [ ] **Observability**：本计划第 3.2/7 章（stage/toolName/stepId/requestId）
- [ ] **Test Gate**：本计划第 8 章

## 12. Verification Plan（自动化验收命令）

- 单元测试：`pytest -q`
- 冒烟测试：`backend/scripts/contract_validation_smoke_test.py`

> 备注：若补齐 SSE/REST 的端到端契约冒烟断言，建议将其作为 smoke 的扩展段落或新增脚本，但必须保持 No Skip 与真实依赖策略。
