# Task 10 工具超时与重试策略（规划蓝图）

本计划定义 GangQing 工具调用侧统一的超时边界、重试/退避策略、稳定错误码映射、SSE 流内可见的重试/降级事件，以及契约/配置/审计/可观测的权威落点与验收口径。

## 0. 范围与硬约束（本任务必须遵守）

- **仅覆盖工具调用侧**：不包含“模型推理超时”。
- **只读默认不变**：不新增任何写操作能力；不得绕过 RBAC/隔离/脱敏。
- **Schema First**：
  - 后端对外 I/O、SSE 事件 payload、工具参数、审计事件：以 **Pydantic** 模型为单一事实源。
  - 前端对外 I/O、SSE 事件解析/配置：以 **Zod** schema 为单一事实源。
- **结构化错误**：
  - 工具超时 => `UPSTREAM_TIMEOUT`（通常 `retryable=true`）
  - 上游不可用 => `UPSTREAM_UNAVAILABLE`（通常 `retryable=true`）
  - `message` 必须英文（便于日志检索）。
- **可观测与审计强制**：重试次数、最终结果、耗时必须写审计并带 `requestId/toolName/stepId`。
- **SSE 强制可见**：重试/降级过程必须通过 `progress`/`warning`（或等价事件）对用户可见；不可恢复错误必须 `error` 后紧随 `final`。
- **配置外部化 + 校验**：timeout、max_retries、退避参数必须外部化并校验；缺关键配置必须快速失败（英文错误）。
- **真实集成测试（No Skip）**：配置缺失/真实依赖不可用 => 测试必须失败。

## 1. 现状盘点（作为设计落点依据）

### 1.1 后端工具包装层现状（权威代码落点）

- **统一入口**：`backend/gangqing/tools/runner.py::run_readonly_tool`
  - 已包含：
    - Params Pydantic 校验（失败映射 `VALIDATION_ERROR`）
    - RBAC capability 检查（失败 audit + 抛出结构化 `AppError`）
    - 重试循环（`RetryPolicy.max_attempts = max_retries + 1`）
    - 异常映射：
      - `TimeoutError` => `UPSTREAM_TIMEOUT` + `retryable=True`
      - `(ConnectionError, OSError)` => `UPSTREAM_UNAVAILABLE` + `retryable=True`
      - 其他异常 => `INTERNAL_ERROR` + `retryable=False`
    - 每次失败 attempt 会写 `tool_call` 审计（含 attempt/maxAttempts/backoffMs/durationMs/errorCode/retryable）
    - `retry_observer` 钩子：已经定义 `RetryEvent`（attempt_start/attempt_failure/retry_scheduled/attempt_success/cancelled）
- **重试策略模块**：`backend/gangqing/tools/retry.py`
  - `should_retry_error` 已限制为 `UPSTREAM_TIMEOUT` / `UPSTREAM_UNAVAILABLE` 且 `retryable=true`
  - 退避算法 `compute_backoff_ms` 已实现：指数退避 + jitter + max cap
- **统一配置**：`backend/gangqing/common/settings.py`
  - 已存在并校验的关键配置：
    - `tool_max_retries`（0..3，默认 3）
    - `tool_backoff_base_ms`（默认 200）
    - `tool_backoff_multiplier`（默认 2.0）
    - `tool_backoff_max_ms`（默认 2000，且 >= base）
    - `tool_backoff_jitter_ratio`（默认 0.2）
    - `postgres_tool_default_timeout_seconds`（默认 5.0）
    - `postgres_tool_max_timeout_seconds`（默认 30.0，且 >= default）
  - `.env.local` 加载优先级：环境变量 > `.env.local`，并由 Pydantic Settings 校验。

### 1.2 DB 超时映射现状（必须纳入 Task10 口径）

- `backend/gangqing_db/errors.py::map_db_error`
  - Postgres `pgcode/sqlstate=57014`（QueryCanceled / statement_timeout）=> `UPSTREAM_TIMEOUT`（cause=`query_canceled`）
  - 这满足你给出的验收点：“statement_timeout/QueryCanceled 必须映射到 `UPSTREAM_TIMEOUT`”。

### 1.3 现有真实集成冒烟测试（验收落点）

- `backend/scripts/tool_timeout_retry_smoke_test.py`
  - 强制真实 Postgres + 迁移 + 造数
  - 使用 `production_daily_slow` 模板（含 `pg_sleep(1)`）+ 极小 `timeoutSeconds` 触发超时
  - 期望：抛出 `AppError(code=UPSTREAM_TIMEOUT, retryable=True)`
  - 还验证审计表 `audit_log`：同一 requestId 下至少 2 条 `tool_call`（对应 attempt + retry）

### 1.4 SSE 对外契约现状（权威文档 + 前端 schema）

- 权威契约：`docs/contracts/api-and-events-draft.md`
  - SSE Envelope：`{type, envelope:{timestamp,requestId,tenantId,projectId,sessionId?,sequence}, payload}`
  - 事件类型最小集合包含：`progress`/`warning`/`error`/`final` 等，并规定 `error` 后必须紧随 `final(status=error)`。
- 前端 Zod（当前实现范围较小）：`web/schemas/sseEnvelope.ts`
  - 目前仅覆盖 `meta/progress/error/final`，尚未覆盖 `tool.call/tool.result/evidence.update/warning`。
  - 这意味着 Task10 的“重试可视化”如果要在前端严格校验，需要在后续实现任务中扩展 Zod schema（本任务仅规划落点与兼容策略）。

## 2. Task 10.1 统一超时边界与错误码映射（规划）

### 2.1 超时的分层边界（必须明确、避免混淆）

- **工具调用超时（本任务范围）**：
  - 包括：HTTP 调用外部系统超时、DB 查询超时、连接超时、读取超时。
  - 统一对外错误码：`UPSTREAM_TIMEOUT`。
- **模型推理超时（非目标）**：
  - 不在 Task10 中定义；避免将其混入工具重试策略。

### 2.2 错误码映射矩阵（稳定、可审计、可配置扩展）

- 统一规则（对外）：
  - `TimeoutError` / DB `57014` / socket read timeout => `UPSTREAM_TIMEOUT`，`retryable=true`
  - 连接失败/网络不可达/DNS => `UPSTREAM_UNAVAILABLE`，`retryable=true`
  - 参数校验（Pydantic）=> `VALIDATION_ERROR`，`retryable=false`
  - RBAC/隔离/脱敏拒绝 => `FORBIDDEN`/`AUTH_ERROR`，`retryable=false`
  - 输出契约校验失败 => `CONTRACT_VIOLATION`，`retryable=false`
  - 未捕获异常 => `INTERNAL_ERROR`，`retryable=false`

### 2.3 `details` 允许字段与脱敏规则（对外与审计分离）

- 对外 `ErrorResponse.details` 仅允许结构化摘要字段（遵循 contracts 2.1.3）：
  - `reason`（稳定枚举）
  - `source`（例如 `tool.postgres_readonly.result` / `tool.execution`）
  - `fieldErrors[]`（仅在 VALIDATION/CONTRACT）
- **禁止**：SQL 原文、SQL 参数、连接串、token、cookie、堆栈、原始 rows。
- 审计与日志：
  - 审计 `args_summary` 仍必须脱敏，只记录“类型/长度/范围”等摘要（参考 `postgres_templates.summarize_filter_value` 的风格）。

## 3. Task 10.2 重试策略：次数/退避/幂等与降级原则（规划）

### 3.1 默认策略（与需求/设计一致）

- **最多 3 次重试（max_retries=3）**：
  - 意味着最多 4 次尝试（attempts=4）。
  - 当前 `settings.tool_max_retries` 已被约束为 0..3，默认 3；满足“最多 3 次”硬约束。
- **可配置指数退避**：base/multiplier/max/jitter 已具备。

### 3.2 “可重试/不可重试”判定（防止无意义重试）

- 必须同时满足：
  - `error.retryable == true`
  - `error.code in {UPSTREAM_TIMEOUT, UPSTREAM_UNAVAILABLE}`
- 明确不可重试：
  - `VALIDATION_ERROR`/`FORBIDDEN`/`AUTH_ERROR`/`CONTRACT_VIOLATION`/`EVIDENCE_*`/`GUARDRAIL_BLOCKED`/`INTERNAL_ERROR`

### 3.3 总耗时预算（Time Budget）与早停（规划决策点）

- 建议在工具包装层引入“**总耗时预算**”（例如 `tool_total_budget_ms`），用于：
  - 避免在超时频繁时重试把整体链路拖到不可接受。
  - 在预算耗尽时：停止重试并返回最后一次错误（仍保持结构化错误）。
- 本仓库当前 runner 未体现 budget 字段；本任务规划需决定：
  - 是否作为 Task10 的强制交付项（推荐：是，但实现可在后续任务落地）。

### 3.4 降级原则（SSE 可见、证据链一致）

- 对可恢复错误（timeout/unavailable）允许：
  - **重试**：用户可见“正在重试 + 下次退避时间”。
  - **降级**：如果业务允许，降级为“较弱的工具/较小范围查询/缓存/最近一次结果”。
- 本任务不实现具体降级策略，但必须规定：
  - 降级属于“业务策略层”，仍必须产出 Evidence 或明确 `warning` 说明证据不足。

## 4. Task 10.3 SSE 事件：重试可视化 + 审计落库对齐（规划）

### 4.1 SSE 事件序列（重试相关最小扩展约定）

在不新增对外事件类型的前提下，重试过程可以完全用 `progress` 与 `warning` 表达（保持向后兼容）：

- `progress`：表达 attempt 开始/结束、进入退避等待、降级阶段切换
- `warning`：表达“发生可恢复错误，将重试/已降级”的用户可理解提示
- `error`：最终失败（不可恢复或重试耗尽），payload 为 `ErrorResponse`
- `final`：紧随 `error`，`status=error`（contracts 强制）

推荐在 `progress.payload.stage` 中使用稳定枚举：
- `tooling`（工具执行总阶段）
- `tooling.retry`（进入重试流程）
- `tooling.backoff`（等待退避）
- `tooling.degraded`（触发降级）

### 4.2 retry_observer -> SSE 映射规则（规划落点）

以 `runner.py` 已有 `RetryEvent` 为事实来源，规划 SSE 侧映射：
- `attempt_start` => `progress(stage=tooling, message=...)`
- `attempt_failure` => `warning(code=<ErrorCode>, message=... , details={attempt,maxAttempts,backoffMs,willRetry})`（message 可中文；code 必须稳定）
- `retry_scheduled` => `progress(stage=tooling.backoff, message=..., details/backoffMs)`
- `attempt_success` => `progress(stage=tooling, message=...)`
- `cancelled` => `error` + `final(status=cancelled)`（若契约支持取消态；现 contracts 支持 `final.status=cancelled`）

说明：`warning.payload.code` 可以复用错误码（例如 `UPSTREAM_TIMEOUT`），或扩展 warning 专用枚举；为了最小变更与可检索性，**优先复用 ErrorCode**。

### 4.3 SSE 契约权威落点与前端校验策略

- 权威对外契约：`docs/contracts/api-and-events-draft.md`（事件类型/序列约束为最终裁决）。
- 后端权威模型（Pydantic）：应在后续实现中落在 `backend/gangqing/common/` 或 `backend/gangqing/api/` 的 SSE model（本任务仅规划，不写代码）。
- 前端权威模型（Zod）：`web/schemas/sseEnvelope.ts` 必须扩展以覆盖：
  - `warning`（至少含 code/message/details?）
  - 若实现选择在重试中输出 `tool.call/tool.result`，也应同步扩展

## 5. 配置与环境变量（权威落点与验收口径）

### 5.1 必需配置项（必须外部化 + 启动校验）

- 后端（env prefix `GANGQING_`，以 `GangQingSettings` 为单一事实源）：
  - `GANGQING_TOOL_MAX_RETRIES`（0..3）
  - `GANGQING_TOOL_BACKOFF_BASE_MS`
  - `GANGQING_TOOL_BACKOFF_MULTIPLIER`
  - `GANGQING_TOOL_BACKOFF_MAX_MS`
  - `GANGQING_TOOL_BACKOFF_JITTER_RATIO`
  - （工具维度 timeout）`GANGQING_POSTGRES_TOOL_DEFAULT_TIMEOUT_SECONDS` / `GANGQING_POSTGRES_TOOL_MAX_TIMEOUT_SECONDS`

### 5.2 缺配置失败策略（必须）

- 缺关键配置必须快速失败，错误消息英文（参考 design 2.9）。
- 不允许交互式询问配置。

## 6. 审计与可观测（字段对齐与权威落点）

### 6.1 审计字段（attempt 级 + 最终级）

必须至少包含（来自你的任务要求 + runner 现状）：
- `requestId`
- `toolName`
- `stepId`
- `attempt`
- `maxAttempts`
- `durationMs`
- `backoffMs`（仅在 willRetry 时存在）
- `errorCode`
- `retryable`

审计事件类型：复用 `tool_call`（contracts 4.1）即可；attempt 级别可多行记录。

### 6.2 结构化日志/trace（规划要求）

- 日志：必须带 `requestId/toolName/stepId/attempt`（runner 已 bind contextvars）。
- trace/metrics（若后续落地）：
  - span：`tool.<toolName>.attempt`，属性包括 attempt/maxAttempts/errorCode/retryable/durationMs

## 7. 验收与测试策略（Task10 的 DoD 口径）

### 7.1 单元测试（不允许 skip；本任务定义覆盖点）

必须覆盖：
- 超时映射：`TimeoutError` => `UPSTREAM_TIMEOUT` 且 `retryable=true`
- 不可用映射：`ConnectionError/OSError` => `UPSTREAM_UNAVAILABLE` 且 `retryable=true`
- DB 超时：`pgcode/sqlstate=57014` => `UPSTREAM_TIMEOUT`
- 重试次数边界：`tool_max_retries` 为 0/1/3 时 attempt 行为正确；禁止 4（settings 已限制）
- 退避算法：base/multiplier/max/jitter 的边界（0 值、max<base 触发校验）
- 脱敏：`details`/审计 `args_summary` 不包含 SQL/连接串/token 等敏感信息（契约禁止项）
- SSE 序列约束（若有契约测试）：`error` 必须紧随 `final(status=error)`

### 7.2 真实集成冒烟测试（必须）

- 复用并扩展 `backend/scripts/tool_timeout_retry_smoke_test.py` 的口径（该脚本已满足“真实 Postgres + 迁移 + 造数 + 超时触发 + 审计校验”）。
- 必须确保：
  - 缺 `GANGQING_DATABASE_URL` => 测试失败（已实现）
  - 慢查询模板触发超时 => `UPSTREAM_TIMEOUT`
  - 审计表出现至少 2 条 `tool_call`（反映 retry 发生）

## 8. 向后兼容与迁移策略（避免契约漂移）

- SSE：优先用既有 `progress/warning/error/final` 表达重试，不强制新增事件类型。
- 若必须新增字段：
  - 仅在 `payload.details` 或 `warning.details` 中新增，且保持可选
  - 同步更新 `docs/contracts/api-and-events-draft.md`
  - 同步更新前端 Zod schema（否则契约测试应失败）

## 9. 已确定的决策（基于当前代码现状定稿）

1) “**工具总耗时预算**（total retry budget）”
- 决策：**不作为 Task10 强制交付项**（可选增强）。
- 依据：当前 `backend/gangqing/tools/runner.py` 未实现 budget 字段与早停逻辑；本任务先以“最多 3 次重试 + 指数退避”作为稳定基线。

2) `UPSTREAM_UNAVAILABLE` 的重试策略
- 决策：**允许重试**，与 `UPSTREAM_TIMEOUT` 同级，遵循 `tool_max_retries` 上限（最多 3 次重试）。
- 依据：当前 `backend/gangqing/tools/retry.py::should_retry_error` 已将其列为可重试码，且 `settings.tool_max_retries` 已限制为 `0..3`。

3) SSE 对重试的可视化规则
- 决策：当某次 attempt 失败且 `willRetry=true` 时，**必须对用户可见**地输出：
  - 至少 1 条 `warning`（承载稳定 `code`，建议复用 `UPSTREAM_TIMEOUT`/`UPSTREAM_UNAVAILABLE`），并包含 `attempt/maxAttempts/backoffMs/willRetry` 等结构化摘要；
  - 随后输出 `progress(stage=tooling.backoff, ...)` 表达退避等待（可选但推荐）。
- 兼容性约束：不新增事件类型；仍遵循 contracts 的序列规则（最终失败必须 `error` 后紧随 `final(status=error)`）。

