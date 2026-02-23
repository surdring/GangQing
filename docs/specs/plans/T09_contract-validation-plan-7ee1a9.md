# T09 工具参数 Schema 校验与契约校验（Pydantic 单一事实源）执行计划
本计划在后端以 Pydantic 为单一事实源统一落地“入参校验 + 输出校验 + 错误映射 + 审计留痕 + 契约测试门禁”，并在前端以 Zod 对齐解析与运行时校验，避免工具链与模型输出发生契约漂移。

## 0. 背景与权威参考（不可偏离）
- 权威需求：`docs/requirements.md`
  - `R8.2` 工具参数校验（Pydantic）
  - `R9.3` 输出结构化校验（Pydantic，失败 -> `CONTRACT_VIOLATION`）
  - `R6.3` SSE 错误流式处理（结构化错误，含 `requestId`）
- TDD：`docs/design.md`
  - 第 6 章错误处理（结构化错误、错误码清单）
  - 第 3.5 章 SSE 事件与 `error`/`final` 规则
  - 第 7 章测试策略（真实依赖、No Skip）
- 对外契约：`docs/contracts/api-and-events-draft.md`
  - `ErrorResponse` 仅允许 `code/message/details?/retryable/requestId`
  - SSE envelope 字段与事件序列
  - REST 与 SSE 错误同构
- OpenAPI：`docs/api/openapi.yaml`

## 1. 当前代码现状盘点（作为接入点）
### 1.1 已存在的“契约基线”模型/模块
- **错误模型**：`backend/gangqing/common/errors.py`
  - `ErrorCode`、`ErrorResponse`、`AppError`（可 `to_response()`）
- **请求上下文**：`backend/gangqing/common/context.py`
  - `RequestContext`，并在缺少 `X-Tenant-Id/X-Project-Id` 时抛 `AppError(AUTH_ERROR)`
- **SSE envelope（部分）**：`backend/gangqing/schemas/sse.py`
  - `SseEnvelope` 已定义，但 `payload` 为 `dict`（目前缺少按事件类型的 payload Pydantic 单一事实源）
- **审计写入**：`backend/gangqing/common/audit.py` + `backend/gangqing_db/audit_log.py`
  - `AuditLogEvent` 为 Pydantic 模型；`insert_audit_log_event()` 会对 `action_summary` 做 `redact_sensitive()`
- **工具示例（Postgres 只读）**：`backend/gangqing/tools/postgres_readonly.py`
  - `PostgresReadOnlyQueryParams` 与 `PostgresReadOnlyQueryResult` 已是 Pydantic
  - 已在部分路径上抛出 `AppError(VALIDATION_ERROR|CONTRACT_VIOLATION)`
- **工具接口（Protocol）**：`backend/gangqing/tools/base.py`（`ReadOnlyTool[TParams, TResult]`）

### 1.2 关键缺口（Task 9 需要补齐的“统一机制”）
- **缺口 A：工具参数校验入口不统一**
  - 目前工具内部零散校验，缺少“工具调用统一入口（框架层）”统一将任意入参映射为 `VALIDATION_ERROR` 并写审计。
- **缺口 B：输出契约校验点不统一**
  - REST/SSE “对外前”缺少强制 schema 断言机制；尤其 SSE 的 `payload` 目前没有按事件类型强类型校验。
- **缺口 C：`details` 脱敏规则未形成明确、可测试的稳定规范**
  - 需明确哪些字段可以出现在 `details`，哪些必须摘要化。
- **缺口 D：契约测试门禁不足**
  - 需要同时具备：单元测试（映射/结构）+ 真实服务冒烟（端到端失败路径也要断言结构化错误）。

## 2. 目标与不变式（Task 9 的验收口径）
### 2.1 强制不变式
- **Pydantic 单一事实源**（后端）：
  - 工具参数 Params
  - 工具输出 Result
  - REST 响应（成功/失败）
  - SSE 事件 envelope + 各事件 payload
  - Evidence
  - 审计事件（落库模型 + 写入前校验）
- **Structured Errors（对外强制）**：
  - 入参无效 -> `VALIDATION_ERROR`
  - 输出不符合契约 -> `CONTRACT_VIOLATION`
  - 对外错误结构固定：`code` + `message`（英文） + `requestId` + `retryable` + `details?`
- **RBAC & Audit & requestId 贯穿**：
  - 任意校验失败必须写审计（包含 `requestId`、`toolName`、`stepId`/阶段信息（若有））
  - `details` 禁止敏感信息：密钥、token、cookie、原始 SQL、完整行数据等
- **真实集成测试（No Skip）**：
  - 冒烟/集成测试必须连接真实 FastAPI + 真实 Postgres + 真实 llama.cpp
  - 缺配置/依赖不可用 -> 测试必须失败，并输出清晰英文错误

### 2.2 可交付成果（Deliverables 对齐你的清单）
- **Directory Structure**：新增/修改目录树与文件清单
- **API Contracts**：对外错误模型与 SSE error 事件字段与同构策略
- **Tool Contracts**：每个工具 Params/Result Pydantic 模型清单与落点
- **Error Model**：触发条件 + `details` 脱敏规则
- **Audit**：审计事件类型 + 最小字段集 + 失败也必须记
- **Test Gate**：单元测试 + 冒烟脚本（真实服务）覆盖点

## 3. 统一机制设计（核心：入口/出口/映射/审计/门禁）

### 3.1 统一“工具调用”生命周期（框架层规范）
目标：任何工具调用都通过统一的生命周期包裹，以便把校验/审计/错误映射做成“强制门禁”。

#### 3.1.1 阶段定义（用于日志/审计/错误 details）
- `phase=tool.params_validation`
- `phase=tool.rbac`
- `phase=tool.execution`
- `phase=tool.result_validation`

#### 3.1.2 工具入参校验策略（Pydantic）
- **统一入口**负责：
  - 将“外部输入（dict/JSON）”解析为该工具的 `ParamsModel`（Pydantic）
  - Pydantic 校验失败：稳定映射为 `AppError(ErrorCode.VALIDATION_ERROR, ...)`
- **错误 message（英文）规范**：
  - 例如：`"Tool params validation failed"`
- **details（脱敏且结构化）建议字段**：
  - `toolName`
  - `phase`
  - `issues`: 仅包含 Pydantic 错误的摘要（字段路径、错误类型、简短原因），禁止输出原始输入值
  - `inputShape`: 可选，仅输出字段名列表/类型摘要，不输出值

#### 3.1.3 工具输出校验策略（Pydantic）
- 工具 `run()` 返回后：
  - 若返回类型本身就是 Pydantic 模型实例：仍执行一次“对外序列化前”的 `model_dump`/`model_validate` 保障（防止工具内部拼装 dict 漏字段/类型漂移）
  - 若返回为 dict/原始结构：必须用 `ResultModel` 进行 `model_validate`
- 校验失败：映射为 `CONTRACT_VIOLATION`
  - message（英文）示例：`"Tool result contract validation failed"`
  - details：
    - `toolName`
    - `phase=tool.result_validation`
    - `violations`: 字段路径 + 错误类型 + 计数
    - 禁止把完整 result 原样塞入 details

#### 3.1.4 审计留痕策略（强制）
- **成功**：写 `tool_call` 审计（已有 `write_tool_call_event`），`result=success`
- **失败（任何阶段）**：也必须写 `tool_call` 审计，`result=failure` + `errorCode`
- `actionSummary`：
  - 必须是脱敏摘要（现有 `redact_sensitive` 是第一道防线；仍需在生成摘要时避免把敏感原文/SQL/整行数据放进去）
  - 推荐只记录：templateId、timeRange、filters 字段名与 op、limit/offset 等

### 3.2 统一“对外输出前”校验（REST + SSE）
目标：任何对外输出都必须在最后一跳被 Pydantic 断言。

#### 3.2.1 REST 输出校验
- 适用范围：所有 API handler 的成功响应体（非 SSE）。
- 规则：
  - handler 内部生成响应对象后，必须通过对应 ResponseModel 的 Pydantic 序列化/校验路径产出 JSON。
  - 若序列化/校验失败：
    - `CONTRACT_VIOLATION`
    - 写审计：`eventType=query/response`（按现有审计类型定义扩展或复用），至少包含 `requestId` 与 `errorCode`

#### 3.2.2 SSE 输出校验（事件 envelope + payload）
- **单一事实源**：`SseEnvelope` 必须升级为“可表达 payload 类型”的 Pydantic 模型集合。
- 最小事件集合（按 `docs/contracts/api-and-events-draft.md`）：
  - `meta` / `progress` / `tool.call` / `tool.result` / `message.delta` / `evidence.update` / `warning` / `error` / `final`
- 核心规则：
  - `type=error` 时：`payload` 必须为 `ErrorResponse`（同构）
  - `tool.result(status=failure)` 时：`payload.error` 必须为 `ErrorResponse`
  - envelope 字段必须齐全（`requestId/tenantId/projectId/sequence/timestamp/type/payload`），且 `payload` 内禁止重复上下文字段（避免漂移）
- 一旦 SSE 校验失败（即将输出前发现）：
  - 将其视为 `CONTRACT_VIOLATION`
  - 立即输出 `error` + `final(status=error)`（其中 `error.payload` 为 `ErrorResponse`，保证客户端可解析）
  - 写审计：`result=failure` + `errorCode=CONTRACT_VIOLATION` + `phase=sse.output_validation`

### 3.3 错误映射总表（强制且可测试）
| 来源 | 条件 | 对外 code | message 语言 | retryable | 审计 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| Pydantic Params 校验失败 | `ValidationError` | `VALIDATION_ERROR` | 英文 | false | 必须 | details 仅含字段路径与原因摘要 |
| Pydantic Result 校验失败 | `ValidationError` | `CONTRACT_VIOLATION` | 英文 | false | 必须 | 视为“内部契约漂移”，禁止自动重试 |
| RBAC 拒绝 | 缺 capability | `FORBIDDEN` | 英文 | false | 必须 | 不在 Task9 主范围，但校验链路需保证一致 |
| 上游超时/不可用 | llama.cpp/DB timeout | `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE` | 英文 | true/true | 必须 | Task9 需保证这些错误也能被 SSE/REST 同构输出 |

### 3.4 `details` 脱敏与最小化规范（必须落到可断言的规则）
- **允许**：字段路径、错误类型、计数、工具名、阶段名、templateId、缺失 headers 名称等
- **禁止**：
  - 密钥、token、cookie、authorization header 值
  - 原始 SQL（尤其含表字段与条件值）
  - 完整行数据（rows）、或能反推敏感字段的原值
  - llama.cpp 原始 prompt（如包含系统指令/敏感上下文）
- **策略**：
  - `details` 始终是“摘要”，不做“回显输入/输出”
  - 对 Pydantic 错误：仅保留 `loc/type/msg` 的改写版，不包含 `input`/`ctx` 等原值

## 4. 目录结构与文件清单（只规划，不写实现）
> 说明：下列为 Task 9 建议落点；实际以仓库现有结构为准，新增文件应尽量靠近既有 `common/`、`schemas/`、`tools/`。

### 4.1 后端（backend/）
- `backend/gangqing/common/`
  - `errors.py`（已存在）：统一错误模型；补齐“错误映射策略”所需的辅助类型（仅规划）
  - `context.py`（已存在）：requestId/tenant/project 生成与校验
  - `audit.py`（已存在）：写审计入口
  - `redaction.py`（已存在）：通用脱敏
- `backend/gangqing/schemas/`
  - `sse.py`（已存在）：SSE envelope；计划扩展为“按事件类型的 payload Pydantic 单一事实源”
  - （建议新增）`contracts/`：对外契约模型聚合目录
    - `error_response.py`（或继续复用 `common/errors.py` 的 `ErrorResponse`，但需明确唯一权威导入路径）
    - `evidence.py`（若当前 `gangqing_db.evidence` 已能满足对外契约，则仅做对齐与导出规划）
    - `sse_events.py`（按事件类型拆分 payload models）
- `backend/gangqing/tools/`
  - `base.py`（已存在）：`ReadOnlyTool` protocol
  - `postgres_readonly.py`（已存在）：已有 Params/Result，可作为示范工具
  - （建议新增）`runner.py`：工具统一入口（参数校验、RBAC、执行、输出校验、审计）；仅规划接口形态，不在本阶段输出实现代码
- `backend/tests/`（或仓库既有 tests 目录）
  - `test_contract_validation_unit.py`：单元测试集合（见第 6 章）
- `backend/scripts/`
  - `contract_validation_smoke_test.py`（任务 9 指定）：真实服务冒烟脚本（见第 6 章）

### 4.2 前端（web/）
- （建议新增）`web/schemas/`
  - `errorResponse.ts`：Zod 的 ErrorResponse（严格限制字段）
  - `sseEnvelope.ts`：Zod 的 SSE envelope + 事件 payload union
- SSE 客户端解析处（现有 Chat/SSE 处理模块附近）
  - 在事件入站时做 Zod 校验；失败时要进入“客户端契约错误”状态并上报（但不能替代后端门禁）

## 5. API Contracts（对外契约对齐策略）
### 5.1 ErrorResponse（权威：contracts + 后端 Pydantic）
- 字段：`code`、`message`（英文）、`details?`、`retryable`、`requestId`
- **约束**：禁止额外字段（严格对齐 `docs/contracts/api-and-events-draft.md#2.1`）

### 5.2 SSE error 事件（REST 与 SSE 同构）
- `type=error` 时：`payload` 必须是 ErrorResponse
- 失败路径最小序列：`meta` -> ... -> `error` -> `final(status=error)`
- `tool.result(status=failure)` 时：`payload.error` 也必须是 ErrorResponse

## 6. 契约测试与门禁（Task 9.3）

### 6.1 单元测试（pytest -q）覆盖点
目标：不依赖外部服务，专注“映射规则与结构稳定性”。
- **用例 1：工具 Params 校验失败 -> VALIDATION_ERROR**
  - 断言：返回/生成的 ErrorResponse 字段齐全且无额外字段
  - 断言：`message` 为英文
  - 断言：`details` 不含敏感 key（token/password/authorization 等）
- **用例 2：工具 Result 校验失败 -> CONTRACT_VIOLATION**
  - 断言：错误码与 retryable=false
  - 断言：`details.violations` 仅为摘要
- **用例 3：SSE error 事件 payload 同构**
  - 断言：`type=error` 的 `payload` 可被 Pydantic（后端）与 Zod（前端）同时通过
- **用例 4：审计事件最小字段集**
  - 断言：校验失败也会构建出可插入的 `AuditLogEvent`（Pydantic 校验通过）

> 说明：单元测试允许通过依赖注入/替身实现隔离数据库写入，但必须模拟真实错误形态；不得用 mock 逃避错误路径。

### 6.2 真实服务冒烟测试（backend/scripts/contract_validation_smoke_test.py）覆盖点
目标：必须连真实 FastAPI + Postgres + llama.cpp。
- **成功路径**：
  - 调用一个实际 API（建议 `GET /api/v1/health` 或一次 chat/semantic API）确保服务可用
- **失败路径 A：触发 VALIDATION_ERROR**
  - 构造一个必然触发 Pydantic 校验失败的请求（例如缺失必填字段/非法 window_seconds）
  - 断言：HTTP 非 2xx 的响应体为 ErrorResponse 且字段同构
- **失败路径 B：触发 CONTRACT_VIOLATION（输出校验失败）**
  - 通过“可控注入方式”触发输出不符合契约（策略需设计为：仅在测试环境开启的受控开关，且不会泄露生产路径；实现阶段再细化）
  - 断言：错误为 `CONTRACT_VIOLATION` 且审计可按 requestId 检索到 failure
- **SSE 失败路径（如覆盖 chat/stream）**：
  - 建立 SSE 连接，触发一次错误，断言收到 `error` + `final` 且 payload 为 ErrorResponse

### 6.3 测试缺配置/依赖不可用的失败策略（No Skip）
- 若缺少关键环境变量（DB URL / llama.cpp URL 等）：
  - 测试必须失败
  - 错误 message 必须英文，且指出缺失的 key 名（只输出 key，不输出 value）

## 7. Task 9 分解与里程碑（对应 9.1/9.2/9.3）

### 7.1 Task 9.1 工具入参校验与错误映射
- **产物**：
  - 工具 Params Pydantic 模型清单（按工具文件就近放置；新增工具需强制配套 ParamsModel）
  - 统一校验失败映射规则（`VALIDATION_ERROR`）
  - 审计事件字段约定：`requestId/toolName/phase/errorCode/result`
- **完成标准**：
  - 任意工具调用的参数不合法，都能稳定返回/输出 ErrorResponse（REST/SSE）
  - 审计中能按 requestId 找到对应 failure 事件

### 7.2 Task 9.2 输出契约校验（对外前）
- **产物**：
  - 工具 Result Pydantic 模型清单（每个工具至少一个 ResultModel）
  - SSE 事件 payload models 的 Pydantic 单一事实源（至少覆盖最小事件集合）
  - REST 与 SSE 错误同构策略落到“统一输出门”
- **完成标准**：
  - 任意对外输出前都执行 schema 断言
  - 失败 -> `CONTRACT_VIOLATION`，且不会泄露敏感信息

### 7.3 Task 9.3 契约测试门禁
- **产物**：
  - 单元测试集合（覆盖 VALIDATION_ERROR / CONTRACT_VIOLATION / SSE 同构 / 审计最小字段）
  - 冒烟脚本 `backend/scripts/contract_validation_smoke_test.py`
- **完成标准**：
  - CI/本地跑：`pytest -q` 通过
  - 真实服务冒烟脚本在真实依赖齐备时通过；缺依赖时明确失败

## 8. Verification Plan（整体验收命令）
- 单元测试：`pytest -q`
- 冒烟测试：`backend/scripts/contract_validation_smoke_test.py`

## 9. 开放问题（需要你确认的决策点）
### 9.1 已确认决策（本计划执行时必须遵守）
1. **CONTRACT_VIOLATION 的“可控触发路径”选择 1A**：
   - 使用“测试环境专用配置开关”，让某个受控路径返回**刻意不符合 ResultModel 的结构**，以在冒烟测试中稳定触发 `CONTRACT_VIOLATION`。
   - 约束：该开关必须默认关闭；必须只在测试/冒烟环境开启；不得对生产路径开放。
2. **ErrorResponse 权威导入路径选择 2（保持单一事实源）**：
   - 继续使用 `backend/gangqing/common/errors.py::ErrorResponse` 作为后端唯一权威对外错误模型。
   - 禁止在其他目录复制定义另一份同名模型，以避免契约漂移。

### 9.2 本阶段范围声明
- 当前仅产出执行计划与门禁设计，**不进入代码实现阶段**。

