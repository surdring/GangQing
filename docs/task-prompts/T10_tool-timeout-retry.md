### Task 10 - 工具超时与重试策略（可观测、可审计、可降级）（Umbrella）

```markdown
# Context
你正在执行第 10 号任务：工具超时与重试策略（可观测、可审计、可降级）。
角色：**技术负责人/架构师**。
目标是定义统一的超时、重试（最多 3 次）、退避策略、错误码映射与 SSE 流内可见的降级/重试事件，并明确“契约/配置/审计/可观测”的权威落点。

# Non-Goals (非目标)
- 本任务不覆盖“模型推理超时”（仅覆盖工具调用侧）。
- 本任务不引入任何写操作能力；仍遵守只读默认与写操作治理（L4）。
- 本任务不新增某个具体外部系统连接器（仅实现统一包装层能力）。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **PLANNING ONLY**: 只输出执行蓝图、契约与验收口径，不输出任何可直接运行的实现代码片段。
- **Schema First（强制）**:
  - 后端：对外 I/O、SSE 事件 payload、工具参数、审计事件必须以 Pydantic 模型为单一事实源。
  - 前端（如涉及）：对外 I/O、SSE 事件、配置必须以 Zod schema 为单一事实源。
- **结构化错误（强制）**:
  - 超时 => `UPSTREAM_TIMEOUT`（通常 `retryable=true`）
  - 上游不可用 => `UPSTREAM_UNAVAILABLE`
  - `message` 英文。
- **可观测与审计（强制）**: 重试次数、最终结果、耗时必须写审计并带 `requestId/toolName/stepId`。
- **SSE 流式输出（强制）**: 重试/降级过程必须通过 `warning`/`progress` 或等价事件对用户可见。
- **配置外部化（强制）**: timeout、max_retries、退避参数必须外部化并校验。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R8.3 工具超时与重试；R14.x 可用性/性能；R12.x 可观测/告警）
- TDD: docs/design.md（2.5 工具规范；2.9 配置外部化；6 错误模型；6.4 SSE 错误输出规则；7 测试策略）
- tasks: docs/tasks.md（任务 10）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/*.md
- 实现参考（本任务落盘后以仓库为准）:
  - backend/gangqing/tools/runner.py（工具调用包装层：审计字段补齐、统一执行阶段标记）
  - backend/gangqing_db/errors.py（DB 异常到稳定错误码映射：包含 statement_timeout/QueryCanceled）
  - backend/gangqing/tools/postgres_templates.py（慢查询探针模板 production_daily_slow）
  - backend/scripts/tool_timeout_retry_smoke_test.py（真实集成冒烟测试）

# Execution Plan (执行蓝图)

1) Task 10.1（统一超时边界与错误码映射）
- Goal:
  - 区分“工具调用超时”与“模型推理超时”（只覆盖工具侧）。
  - 将超时/不可用/连接失败等上游异常映射为稳定错误码（`UPSTREAM_TIMEOUT`/`UPSTREAM_UNAVAILABLE`），并填充 `retryable`。
- Deliverables:
  - 统一的工具调用超时配置与应用方式（配置外部化 + schema 校验）。
  - 统一错误映射规则（含 `details` 可观测字段，但禁止敏感信息）。

2) Task 10.2（重试策略：次数/退避/幂等与降级原则）
- Goal:
  - 失败且可重试时自动重试（最多 3 次），并具备可配置退避策略。
  - 明确哪些错误“可重试/不可重试”，避免对确定性失败进行无意义重试。
- Deliverables:
  - 重试策略模块（最大次数、退避、抖动 jitter 可选、总耗时预算）。
  - 审计字段：每次重试记录 attempt 序号、耗时、最终错误码。

3) Task 10.3（SSE 事件：重试可视化 + 审计落库对齐）
- Goal:
  - SSE 流中对用户可见地呈现“正在重试/已降级/最终失败”。
  - SSE 中的错误事件必须为结构化错误模型，并且与 contracts 一致。
- Deliverables:
  - SSE 事件序列约定（重试过程中 `progress/warning`，失败输出 `error` + `final`）。
  - 审计事件落库字段补齐：`requestId/toolName/stepId/attempt/maxAttempts/durationMs/errorCode/retryable`。

# Deliverables Definition (交付物定义)
- [ ] **Environment Variables / Config**:
  - timeout、max_retries、backoff_base_ms、backoff_max_ms（或等价字段）必须外部化并在启动时校验。
  - 缺少关键配置必须快速失败，并输出英文错误消息。
- [ ] **API Contracts / SSE Contracts**:
  - SSE 中的 `warning/progress/error/final` 事件必须具备可被前端解析的稳定结构；其中 `error` payload 必须等价于对外错误模型。
  - 若引入新的事件类型或字段：必须同步更新 `docs/contracts/api-and-events-draft.md` 并保持向后兼容。
- [ ] **Error Model**:
  - 对外错误响应与 SSE `error` 事件必须包含：`code`/`message`/`requestId`/`retryable`/`details?`。
  - `message` 必须为英文。
- [ ] **Audit & Observability**:
  - 重试全过程必须可审计（每次 attempt 与最终结果）。
  - 日志/审计不得包含敏感参数原文；仅允许脱敏摘要。
- [ ] **RBAC & Data Isolation（不得退化）**:
  - 本任务的包装层变更不得绕过既有 RBAC/数据域隔离/脱敏逻辑；任何跨域访问仍需返回 `AUTH_ERROR`/`FORBIDDEN` 并审计。
- [ ] **SSE Events**:
  - 可恢复错误：允许重试/降级，但必须对用户可见（`warning`/`progress`）。
  - 不可恢复错误：必须输出结构化 `error` 后再输出 `final`。

# Verification Plan (整体验收)
- Automated Tests:
  - Unit: `pytest -q`
  - Smoke: `backend/scripts/tool_timeout_retry_smoke_test.py`
- Expected Coverage:
  - 超时错误映射稳定且 `retryable` 正确。
  - Postgres statement_timeout / QueryCanceled（pgcode/sqlstate=`57014`）必须映射到 `UPSTREAM_TIMEOUT`。
  - `details` 禁止泄露 SQL、SQL 参数、连接串等敏感信息（仅允许脱敏摘要字段）。
  - 重试次数上限严格为 3 次（含边界：0/1/3/4）。
  - SSE 可观察到重试过程，并且最终错误为结构化模型。

# Quality Checklist（自检）
- [x] Umbrella 阶段是否明确 **禁止写代码**（NO CODE IMPLEMENTATION）？
- [x] 是否明确 Schema 单一事实源（后端 Pydantic / 前端 Zod）与契约对齐位置？
- [x] 是否明确结构化错误模型字段（`code/message/requestId/retryable/details?`）且 `message` 英文？
- [x] 是否明确 SSE 错误事件规则：`error` 后 `final`（不可恢复）？
- [x] 是否明确审计/可观测字段：`requestId/toolName/stepId/attempt/maxAttempts/durationMs/errorCode/retryable`？
- [x] 是否明确配置外部化与校验要求（环境变量 > `.env.local`）？
- [x] 是否强调真实集成测试不可 skip（配置缺失/真实依赖不可用 => 测试失败）？

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 10.1 - 工具超时与错误映射（`UPSTREAM_TIMEOUT`/`UPSTREAM_UNAVAILABLE`）

```markdown
# Context
你正在执行子任务：10.1 - 工具超时与错误映射。
角色：**高级开发工程师**。
目标是为所有工具调用建立一致的超时与错误映射规则，并保证结构化错误对齐 contracts。

# Critical Rules
- **Schema First**: 工具参数、对外错误响应、审计事件必须以 Pydantic 模型为单一事实源。
- **结构化错误**: 超时/不可用必须映射到稳定错误码。
- **message 英文**。
- **配置外部化（强制）**: timeout 必须外部化并校验。
- **RBAC & Audit**: 工具调用错误映射必须保证审计字段完整，并包含 `requestId/toolName/stepId`（如有）。
- **Read-Only Default**: 本任务不得引入任何写操作路径。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R8.3）
- TDD: docs/design.md（6.1/6.3/6.4）
- tasks: docs/tasks.md（10.1）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse）

# Target Files (must be verified by repository search)
- backend/**：工具调用包装层（timeout 与错误映射的权威实现位置）
- backend/**：结构化错误模型与错误码枚举（对齐 contracts）
- backend/scripts/tool_timeout_retry_smoke_test.py（冒烟测试）

# Execution Plan
1) 定义“工具超时”边界
- 统一 timeout 的配置来源与优先级（环境变量 > `.env.local`）。
- 禁止硬编码 timeout 秒数。

2) 统一错误映射
- 超时映射到 `UPSTREAM_TIMEOUT`（通常 `retryable=true`）。
- 连接失败/上游不可用映射到 `UPSTREAM_UNAVAILABLE`（`retryable` 依据具体异常语义）。
- Postgres statement_timeout / QueryCanceled：pgcode/sqlstate=`57014` 必须映射到 `UPSTREAM_TIMEOUT`。
- `details` 仅允许放：`toolName`、`timeoutMs`、`attempt`、`maxAttempts`、`durationMs` 等，不得包含敏感参数。

3) 审计字段要求
- 至少包含：`requestId`、`toolName`、`stepId`（如有）、`durationMs`、`errorCode`、`retryable`。

# Verification
- **Unit**: `pytest -q` 覆盖：超时映射与 `retryable`。
- **Smoke**: `backend/scripts/tool_timeout_retry_smoke_test.py`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 10.2 - 重试与降级：次数、退避、审计与 SSE 可视化

```markdown
# Context
你正在执行子任务：10.2 - 重试与降级：次数、退避、审计与 SSE 可视化。
角色：**高级开发工程师**。
目标是实现工具调用的统一重试策略（最多 3 次）与可配置退避，并在 SSE 与审计中完整呈现重试过程。

# Critical Rules
- **重试最多 3 次**（按任务约束）。
- **审计**: 记录每次重试与最终结果。
- **SSE**: 重试过程必须输出可解析事件。
- **Schema First**: 对外错误响应、SSE `error` payload、审计事件必须以 Pydantic 模型为单一事实源。
- **结构化错误**: `message` 必须为英文，并包含 `code/message/requestId/retryable/details?`。
- **RBAC & Audit**: 日志/审计必须脱敏，且字段包含 `requestId/toolName/stepId`（如有）。
- **Read-Only Default**: 本任务不得引入任何写操作路径。
- **真实集成测试（No Skip）**。

# References
- tasks: docs/tasks.md（10.2）
- TDD: docs/design.md（6.4）

# Target Files (must be verified by repository search)
- backend/**：工具调用重试策略实现位置
- backend/**：SSE 事件输出（progress/warning/error/final）
- backend/**：审计落库写入位置
- backend/scripts/tool_timeout_retry_smoke_test.py（冒烟测试）

# Execution Plan
1) 定义重试策略（不引入范围外行为）
- maxAttempts 固定为 3（但允许通过配置覆盖用于不同环境的压测；若允许覆盖，需在 prompt 中写明默认值与上限）。
- 退避策略：指数退避 + 可选 jitter；必须可配置（base/max）。
- 明确不可重试错误集合（如参数校验、权限错误、契约违反等）。

2) SSE 可视化
- 每次重试前输出 `progress` 或 `warning`，至少包含：`toolName`、`attempt`、`maxAttempts`、`reasonCode`（可选）。
- 若最终失败：输出结构化 `error`，随后输出 `final`。

3) 审计落库
- 每次 attempt 写审计一条（或一条聚合审计 + attempt 数组，按现有审计模型选择其一，但必须可追溯）。
- 最终结果写入最终状态（success/failure）与最终错误码。

# Verification
- **Unit**: `pytest -q` 覆盖：重试次数上限与事件输出顺序。
- **Smoke**: `backend/scripts/tool_timeout_retry_smoke_test.py`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 10.3 - SSE 事件契约对齐：重试/降级可视化 + 结构化错误 + 审计字段补齐

```markdown
# Context
你正在执行子任务：10.3 - SSE 事件契约对齐。
角色：**高级开发工程师**。
目标是在 SSE 流中用可解析事件向前端呈现重试/降级过程，并确保最终错误事件为结构化错误模型，同时审计字段完整。

# Critical Rules
- **Schema First**: SSE 事件 payload 与对外错误响应必须以 Pydantic 模型为单一事实源。
- **SSE 错误规则（强制）**: 发生错误必须尽快输出结构化 `error`（含 `code/message/requestId/retryable`），不可恢复错误必须紧跟 `final`。
- **可恢复错误（强制）**: 允许重试/降级，但必须输出 `warning/progress` 让用户可见。
- **结构化错误（强制）**: `message` 必须为英文。
- **审计（强制）**: 重试过程（含每次 attempt）必须可追溯。
- **RBAC & Audit**: 审计中必须脱敏参数，禁止写入敏感原文。
- **Read-Only Default**: 本任务不得引入任何写操作路径。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R6.3, R8.3）
- TDD: docs/design.md（3.5.x, 6.4, 7.2）
- tasks: docs/tasks.md（10.3）
- contracts: docs/contracts/api-and-events-draft.md（SSE events + ErrorResponse；以 2.1.0.1/2.1.0.2 为 SSE envelope/事件类型权威约束）

# Target Files (must be verified by repository search)
- backend/**：SSE 事件序列化与输出模块
- backend/**：结构化错误模型（ErrorResponse / AppError 等）
- backend/**：审计模型与写入路径
- backend/scripts/tool_timeout_retry_smoke_test.py（冒烟测试）

# Execution Plan
1) 明确事件序列与最小字段
- 重试过程：每次 retry 前输出 `progress` 或 `warning`（至少含 attempt/maxAttempts/toolName/requestId）。
- 失败：输出 `error`（结构化错误模型），随后输出 `final`。

2) 契约对齐与校验点
- 确保 `error` 事件 payload 能被前端按 contracts 解析。
- 确保 `requestId` 贯穿：HTTP 入站 -> 工具调用 -> SSE 事件 -> 审计。

3) 审计字段补齐
- 记录每次 attempt 的关键字段：`attempt/maxAttempts/durationMs/errorCode/retryable`。

# Verification
- **Unit**: `pytest -q` 覆盖：事件序列（含错误路径）、error payload 结构完整性、requestId 贯穿。
- **Smoke**: `backend/scripts/tool_timeout_retry_smoke_test.py` 覆盖：真实服务下可观察到重试事件与最终结构化错误。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（重试过程工具证据仍需保留）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
- [x] Doc References Updated
