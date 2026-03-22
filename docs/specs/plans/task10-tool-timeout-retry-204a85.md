# Task 10 工具超时与重试策略执行蓝图（可观测、可审计、可降级）

本蓝图定义 GangQing 工具调用的统一超时边界、最多 3 次重试与退避策略、稳定错误码映射、以及在 SSE 流内对重试/降级过程的可见化与审计落库要求。

## 0. 权威约束与对齐点（只列与 Task10 直接相关）

- **PRD**：`docs/requirements.md`（R8.3、R6.3、R11.1）
- **TDD**：`docs/design.md`（6.x 错误处理、SSE 错误输出规则、配置外部化、审计）
- **任务**：`docs/tasks.md`（任务 10：超时区分、最多 3 次、SSE `warning/progress`、审计字段）
- **对外契约**：`docs/contracts/api-and-events-draft.md`
  - `ErrorResponse`：`code/message(英文)/details?/retryable/requestId`
  - SSE：统一 envelope + `warning`/`progress`/`tool.call`/`tool.result`/`error`/`final`

本仓库现状（用于落地时对齐）：
- **RequestContext** 已含 `requestId/tenantId/projectId/sessionId/taskId/stepId`：`backend/gangqing/common/context.py`
- **审计** 已有 `write_tool_call_event()`，且落库字段包含 `requestId/toolName/argsSummary/result/errorCode/evidenceRefs`：`backend/gangqing/common/audit.py`
- **工具运行包装器**：`run_readonly_tool()` 目前负责 params 校验、RBAC、输出契约校验与审计：`backend/gangqing/tools/runner.py`
- **工具级超时配置示例**（Postgres）：`GANGQING_POSTGRES_TOOL_DEFAULT_TIMEOUT_SECONDS` / `...MAX...`：`backend/gangqing/common/settings.py` 与 `backend/gangqing/tools/postgres_readonly.py`
- **SSE schema** 当前仅实现 `meta/error` 两类强类型模型，其余事件由 `SseEnvelope(payload: dict)` 承载：`backend/gangqing/schemas/sse.py`

---

## 1) Task 10.1 统一超时边界与错误码映射

### 1.1 超时边界分层（必须“可解释、可观测、可审计”）

定义三层超时，避免“工具超时”与“模型超时”混淆：

- **HTTP/SSE 连接层超时（transport）**
  - 范围：客户端连接中断/反向代理 idle timeout/服务端取消传播。
  - 对外表现：通常不是 `ErrorResponse`，而是连接断开；但**服务端必须尽量**在感知取消时停止后续工具调用与输出（契约要求“取消向下传播”）。

- **编排步骤级超时（step timeout）**
  - 范围：某个 step（例如“工具拉取数据”阶段）允许的最大耗时上限。
  - 目的：避免单 step 挂死导致 SSE 长时间无事件；与 `progress` 的节奏绑定。

- **工具调用级超时（tool timeout）**（Task10 的核心）
  - 范围：单次工具调用（一次 attempt）的执行上限。
  - 原则：
    - **每个 attempt 都有独立超时**（否则重试无意义）。
    - attempt 超时应归类为 `UPSTREAM_TIMEOUT`（`retryable=true` 通常成立）。

### 1.2 错误码映射规则（强制）

工具调用失败时，对外统一映射到 `gangqing.common.errors.ErrorCode` 对齐 contracts：

- **超时**（任何 “deadline exceeded/statement_timeout/read timeout/async timeout”）
  - `code=UPSTREAM_TIMEOUT`
  - `retryable=true`（默认；除非明确为不可重试超时场景）
  - `message`（英文）示例语义："Upstream timeout" / "Tool execution timed out"（实际措辞可统一模板化）
  - `details`（结构化，脱敏）建议字段：
    - `details.toolName`
    - `details.timeoutMs`
    - `details.attempt`
    - `details.reason`（稳定枚举，例如 `statement_timeout|read_timeout|deadline_exceeded`）

- **上游不可用**（连接失败、DNS、拒绝连接、依赖不可用、DB OperationalError 等）
  - `code=UPSTREAM_UNAVAILABLE`
  - `retryable=true`（通常成立）
  - `message` 英文示例："Upstream unavailable" / "Postgres is unavailable"
  - `details` 建议字段：`toolName/service/causeClass/reason/attempt`

- **参数校验失败**（工具 ParamsModel 校验）
  - `code=VALIDATION_ERROR`、`retryable=false`（现状已实现）

- **RBAC/隔离拒绝**
  - `code=FORBIDDEN` 或 `AUTH_ERROR`，`retryable=false`

- **输出契约违反**（工具结果 schema 校验失败）
  - `code=CONTRACT_VIOLATION`，`retryable=false`
  - 注意：此类错误**禁止自动重试工具**（重试不应掩盖契约问题）；如要重试，应由更上层“修复输出/重新生成”策略负责，不属于 Task10 的工具重试。

### 1.3 统一英文 message（强制）

- `ErrorResponse.message` 必须英文，且可用于日志检索。
- SSE 的 `warning.payload.message` 可以中文，但需要用稳定 `warning.payload.code` 支撑可检索与前端逻辑分支。

---

## 2) Task 10.2 重试策略：次数/退避/幂等要求

### 2.1 重试上限与术语（强制）

- `max_retries`：最多 3 次 **重试次数**（与 PRD/Task10 一致）。
- 建议将“attempt”统一定义为：
  - `attempt = 1 + retry_index`（首次为 attempt=1；之后为 attempt=2..max_attempts）
  - `max_attempts = 1 + max_retries`（如果 max_retries=3，则最多 4 次 attempt）

本任务口径已确认：采用 **A**，即 `max_retries=3` 表示“失败后最多再试 3 次”，因此 `max_attempts=4`。

### 2.2 可重试判定（Retry Policy）

只有在满足以下条件时才执行重试：

- **错误码可重试**：
  - `UPSTREAM_TIMEOUT`、`UPSTREAM_UNAVAILABLE` 通常可重试
  - 其他错误码默认不可重试（尤其 `VALIDATION_ERROR/FORBIDDEN/AUTH_ERROR/CONTRACT_VIOLATION`）

- **工具幂等性要求**（必须显式声明）
  - Task10 处于 L1 “只读默认”阶段：工具应为只读，通常幂等。
  - 仍需在工具元数据中明确 `is_idempotent=true`（或等价声明），避免未来混入写工具后被误重试。
  - 若未来出现写工具：默认 `is_idempotent=false`，禁止自动重试，除非提供 idempotency key 与后端保证。

- **预算与取消**：
  - 若 SSE 连接断开/取消信号触发，应立即停止后续重试。
  - 若整体 step budget 已不足（例如剩余时间 < 下次 timeout），应放弃重试并进入降级/失败输出。

### 2.3 退避策略（Backoff Strategy）

目标：减少雪崩、避免对上游造成脉冲压力、保持用户可感知进度。

- **策略**：指数退避 + 抖动（jitter）。
- **参数全部外部化并校验**（强制）：
  - `base_delay_ms`（初始延迟）
  - `multiplier`（指数倍数）
  - `max_delay_ms`（上限）
  - `jitter_ratio`（0..1）
- **默认建议（仅建议值，需通过配置体现，不写死）**：
  - `base_delay_ms=200`
  - `multiplier=2.0`
  - `max_delay_ms=2000`
  - `jitter_ratio=0.2`

### 2.4 降级策略（Degrade Strategy）

当重试耗尽或判定不再重试时，必须进入“可审计、可解释”的降级分支：

- **降级优先级（建议）**
  1. **返回部分结果**（如果工具支持分页/分片且已获得部分 evidence）
  2. **返回缓存/最近一次成功结果**（若未来引入缓存；需在 evidence 中标注来源与时间）
  3. **降级为“仅展示数据与来源/不确定项”**（对齐 Evidence 降级规则与 `warning`）
  4. **最终失败**：输出 `error` + `final(status=error)`

- **降级的对外表达**
  - 必须先发 `warning` 或 `progress`，说明“正在降级/已降级”与下一步动作。
  - 若最终仍失败，必须按契约输出结构化 `error`。

---

## 3) Task 10.3 SSE 事件：重试可视化 + 审计落库

### 3.1 SSE 中“重试/降级”事件可视化（强制）

对齐 `docs/contracts/api-and-events-draft.md` 的事件集合，且满足：
- 用户能在流中看见：
  - 正在调用哪个工具
  - 第几次尝试（attempt）
  - 发生了什么错误（至少稳定 `code`）
  - 将在多久后重试（backoff）或将降级

**推荐事件序列（单工具调用含重试）**：

- `progress`：进入 tooling 阶段
- `tool.call`：attempt=1 开始
- `tool.result(status=failure, error=ErrorResponse)`：attempt=1 失败
- `warning` 或 `progress`：声明将重试（包含 attempt、backoffMs、原因 code）
- （sleep/backoff）
- `tool.call`：attempt=2
- `tool.result(...)`
- ...
- 若最终 success：
  - `tool.result(status=success, ...)`
  - `evidence.update`（如有）
- 若最终失败：
  - （可选）`warning`：声明重试耗尽/进入降级
  - `error(payload=ErrorResponse)`
  - `final(status=error)`

本任务口径已确认：重试期间**不输出** `error` 事件；重试过程的失败仅使用 `tool.result(status=failure)` + `warning/progress` 可视化；仅在“最终失败且不再重试”时输出 `error` + `final(status=error)`。

### 3.2 SSE payload 字段建议（保持契约兼容）

由于当前 `backend/gangqing/schemas/sse.py` 对除 `meta/error` 外事件未做强类型约束，蓝图只定义“必须包含”的字段（未来可进一步 schema 化）。

- `progress.payload`：
  - `stage`：固定枚举（`tooling`/`finalizing` 等）
  - `message`：中文可
  - `stepId`：如有编排步骤，必须带上
  - `details?`：建议包含 `toolName/attempt/maxAttempts`

- `warning.payload`：
  - `code`：建议复用错误码（例如 `UPSTREAM_TIMEOUT`）或扩展 `TOOL_RETRY_SCHEDULED/TOOL_DEGRADED`
  - `message`：中文可
  - `details`：建议包含 `toolName/attempt/maxAttempts/backoffMs/timeoutMs`

- `tool.call.payload`（契约强制字段）：
  - `toolCallId/toolName/argsSummary`
  - 建议 `argsSummary` 里加入：`attempt/timeoutMs`（脱敏）

- `tool.result.payload`（契约强制字段）：
  - `toolCallId/toolName/status`
  - `status=failure` 时：`error=ErrorResponse`
  - 建议补充：`resultSummary.durationMs`、`resultSummary.attempt`

### 3.3 审计落库（强制字段与统计口径）

满足任务硬约束：**重试次数、最终结果、耗时必须写审计并带 `requestId/toolName/stepId`**。

在审计事件（`eventType=tool_call`）中建议形成两类记录：

- **Attempt 级审计（每次 attempt 都写）**
  - `requestId`（来自 ctx）
  - `resource=toolName`
  - `actionSummary.argsSummary` 最少包含：
    - `stage`（例如 `tool.execution`）
    - `attempt`（1..N）
    - `maxAttempts`
    - `timeoutMs`
    - `backoffMs`（非最后一次且计划重试时）
    - `durationMs`（本次 attempt）
    - `stepId`（如有；来自 ctx）
  - `result`：`success|failure`
  - `errorCode`：失败时写稳定码（例如 `UPSTREAM_TIMEOUT`）

- **Tool 调用聚合审计（可选但强烈建议，用于快速检索）**
  - 目的：一条记录总结本工具调用的整体重试过程（attempts、总耗时、最终码）。
  - 可作为同一个 `tool_call` 事件的另一种 `stage`（例如 `tool.retry.summary`）。
  - 最少字段：
    - `attemptCount`（实际 attempts）
    - `retryCount`（实际 retries）
    - `totalDurationMs`
    - `finalStatus`
    - `finalErrorCode?`

> 现状 `write_tool_call_event()` 已能承载 `argsSummary`，因此落地时只需统一约定 `argsSummary` 字段口径。

### 3.4 可观测性补充（非契约，但强制工程要求）

- 结构化日志至少包含：`requestId/toolName/stepId/attempt/durationMs/errorCode`
- 指标（如已接入 METRICS）：建议至少观测
  - 工具调用延迟分布（attempt 级与聚合级）
  - 工具错误率（按 errorCode）
  - 重试次数分布（retryCount）

---

## 4) 配置外部化与校验（强制）

### 4.1 配置项清单（建议命名，不写死实现）

要求：timeout、max_retries、退避参数必须外部化并校验。

建议按“全局默认 + 工具覆盖”设计：

- 全局：
  - `GANGQING_TOOL_TIMEOUT_DEFAULT_SECONDS`
  - `GANGQING_TOOL_TIMEOUT_MAX_SECONDS`
  - `GANGQING_TOOL_MAX_RETRIES`（默认 3）
  - `GANGQING_TOOL_BACKOFF_BASE_MS`
  - `GANGQING_TOOL_BACKOFF_MULTIPLIER`
  - `GANGQING_TOOL_BACKOFF_MAX_MS`
  - `GANGQING_TOOL_BACKOFF_JITTER_RATIO`

- 工具特定（可选，示例 Postgres 已有 timeout 上下限）：
  - `GANGQING_POSTGRES_TOOL_DEFAULT_TIMEOUT_SECONDS`
  - `GANGQING_POSTGRES_TOOL_MAX_TIMEOUT_SECONDS`

### 4.2 校验规则（Pydantic Settings 层）

- `max_retries`：`0..3`（按任务硬约束）
- `timeout_seconds`：`>0` 且 `<= max_timeout_seconds`
- backoff：
  - `base_delay_ms>=0`
  - `multiplier>=1`
  - `0<=jitter_ratio<=1`
  - `max_delay_ms>=base_delay_ms`

---

## 5) 验证（真实集成测试 No Skip）

### 5.1 Unit（`pytest -q`）必须覆盖的断言点

不引入 mock 的前提下，单元测试建议覆盖“纯逻辑/映射/序列化”部分：

- **错误码映射**
  - timeout 类异常 -> `UPSTREAM_TIMEOUT` 且 `retryable=true`
  - unavailable 类异常 -> `UPSTREAM_UNAVAILABLE` 且 `retryable=true`
  - validation/rbac/contract violation -> `retryable=false` 且不触发重试

- **重试上限**
  - 失败 N 次时不超过 `max_attempts`

- **退避参数计算**
  - 指数递增 + 上限裁剪 + jitter 范围

- **SSE 事件顺序（最小序列）**
  - `meta` 必须首事件
  - 最终成功：存在 `final(status=success)` 且为最后事件
  - 最终失败：存在 `error` 后紧随 `final(status=error)`

> 单元测试中允许通过依赖注入传入“具备真实失败行为”的实现（fake fetch / fake tool runner），但不得用 mock 掩盖错误分类与 retry 逻辑。

### 5.2 Smoke（`backend/scripts/tool_timeout_retry_smoke_test.py`）必须覆盖的真实链路

必须连真实 FastAPI + 真实 Postgres（按仓库规则）。

建议覆盖两个场景（至少）：

- **场景 A：可重试超时**
  - 人为触发 Postgres `statement_timeout` 或等价机制，导致工具超时
  - 断言：
    - SSE 中出现至少一次 `tool.result(status=failure, error.code=UPSTREAM_TIMEOUT)`
    - SSE 中出现 `warning/progress` 表示将重试
    - 审计表中可按 `requestId` 查到 attempt 级记录（含 `attempt/durationMs/errorCode`）

- **场景 B：上游不可用**
  - 通过真实配置让 DB 不可达（例如指向错误 host/端口；注意不应破坏开发环境，可用临时环境变量覆盖）
  - 断言：
    - 错误码为 `UPSTREAM_UNAVAILABLE`
    - `retryable=true`
    - 重试次数不超过上限
    - 最终输出 `error` + `final(status=error)`

---

## 6) 需要你确认的 2 个决策点（不确认会导致实现口径漂移）

- **D1：重试次数语义（已确认：A）**
  - `max_retries=3` 表示“失败后最多再试 3 次”（总 attempts=4）

- **D2：重试过程是否允许提前对用户输出 `error` 事件（已确认：不允许）**
  - 重试期间仅用 `tool.result(status=failure)` + `warning/progress`，不要输出 `error`；仅在最终失败时输出 `error` + `final(status=error)`。

---

## 7) 本蓝图的完成标准（Definition of Done）

- 文档/契约层：错误码映射与 SSE 可视化规则明确、可被测试用例断言。
- 工程约束：超时/重试/退避参数全部外部化并可校验。
- 审计与可观测：
  - 审计至少可按 `requestId` 还原每次 attempt（含 `toolName/stepId/attempt/durationMs/errorCode`）
  - 失败场景能解释“重试了几次、为何停止、是否降级”
- 验证：`pytest -q` 与 `backend/scripts/tool_timeout_retry_smoke_test.py` 均通过（No Skip）。
