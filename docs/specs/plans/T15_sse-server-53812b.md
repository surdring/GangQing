# T15 — SSE 服务端输出（进度 / 消息增量 / 证据增量 / 结构化错误 / 结束事件）执行蓝图

本计划将对齐 GangQing L1 的 SSE 流式输出契约，补齐最小事件集合与强制序列规则，并用“真实服务冒烟 + 单元测试”可验证地覆盖错误与取消传播。

## 0. 任务范围与硬约束（复述为验收口径）

- **仅规划**：本文件只描述“怎么做/改哪些文件/如何验收”，不包含任何实现代码。
- **端点**：权威端点为 `POST /api/v1/chat/stream`（响应 `Content-Type: text/event-stream`）。
- **Schema First**：SSE 事件必须可被前端分段渲染，且需与 `docs/contracts/api-and-events-draft.md` 一致；对外错误模型为 `ErrorResponse`，与 REST 错误同构。
- **Read-Only Default**：SSE 链路不得触发写操作执行（仅允许草案/建议/只读工具调用）。
- **Structured Errors**：
  - 当 `type=error` 时，`payload` 必须是 `ErrorResponse(code/message/details?/retryable/requestId)`。
  - **不可恢复错误**必须输出 `error -> final(status=error)`，并在 `final` 后不再输出任何事件。
  - `ErrorResponse.message` 必须为**英文**。
- **Request Context**：每条 SSE 事件必须携带 `requestId/tenantId/projectId/sequence/timestamp`（`sessionId` 可选）；`sequence` 在单连接内必须严格单调递增。
- **Cancellation**：客户端断开/取消必须向下传播；至少可验证：
  - 服务端停止继续输出 SSE
  - 服务端停止后续工具调用/推理（不再产生新的工具 attempt/模型生成）
- **Explicit Cancel（强制）**：在**连接未断开**时必须支持“显式 cancel 请求”，并在原 SSE 连接内输出 `final(payload.status=cancelled)`，且 `final` 后不得再输出任何事件。
- **Real Integration / No Skip**：冒烟测试必须连接真实服务；缺配置/依赖不可用必须失败，不得 skip。

## 1. 关键决策（已确认）

- **端点定稿**：使用 `POST /api/v1/chat/stream` 作为唯一权威 SSE 端点。
- **SSE `event:` 行策略**：以 contracts 为准：服务端**可以输出** `event:` 行用于兼容/调试，但**客户端与测试必须只以 JSON 的 `type` 字段为准**。
- **SSE Envelope 结构形态**：以现有实现为准，采用“**扁平顶层字段**”事件结构：
  - 顶层：`type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`
  - 不采用 `type + envelope + payload` 的嵌套结构
  - 因此需要在 `docs/contracts/api-and-events-draft.md` 中把 6.1.2 的结构描述修订为扁平结构，确保单一事实源
- **显式取消通道**：新增 REST 端点 `POST /api/v1/chat/stream/cancel`，以 `requestId` 取消对应的进行中 SSE 连接，并由服务端在该 SSE 连接内输出 `final(status=cancelled)`。

## 2. 现状盘点（代码与测试入口）

### 2.1 服务端现状

- SSE 路由原型已存在：`backend/gangqing/api/chat.py`（`@router.post("/chat/stream")`，由 app 统一挂载到 `/api/v1` 前缀）。
- SSE Pydantic 模型已存在：`backend/gangqing/schemas/sse.py`
  - 已覆盖：`meta/progress/warning/tool.call/tool.result/error/final`
  - **缺口**：最小集合中必须的 `message.delta` 与 `evidence.update`（当前未定义）。
- 取消检测已存在：通过 `request.is_disconnected()` 的 watcher 任务 + `should_cancel` 回调传入工具线程。

### 2.2 前端/契约现状（用于联调一致性）

- 前端 Zod SSE schema 已存在：`web/schemas/sseEnvelope.ts`
  - 已覆盖：`meta/progress/warning/tool.call/tool.result/error/final`，以及若干非最小集合事件（如 `intent.result`、`routing.decision`）。
  - **缺口**：`message.delta`、`evidence.update`。
- `backend/scripts/sse_smoke_test.py` 已存在：
  - 会启动真实 uvicorn + 跑 alembic upgrade + 造最小数据
  - 验证 meta 首、final 末、错误路径包含 error + final(status=error)
  - **缺口**：未验证 sequence 单调递增、未验证 error payload 的英文 message/字段完整性、未验证 message.delta/evidence.update。
- `backend/scripts/chat_stream_retry_smoke_test.py` 已存在：
  - 使用 `event:` 行解析事件（当前脚本会读取 `event:` + `data:`）
  - 断言重试产生多次 `tool.call`，并出现 `warning` 与最终 `error`

## 3. Task 15 目标状态（对外协议与字段契约）

> 以 `docs/contracts/api-and-events-draft.md` 的“最小事件集合”与“序列规则”为准，但事件结构采用扁平顶层字段。

### 3.1 扁平事件通用字段（每条事件必有）

- `type: string`（事件类型）
- `timestamp: string`（UTC ISO 8601；服务端内部可用 datetime，但对外序列化必须是字符串）
- `requestId: string`
- `tenantId: string`
- `projectId: string`
- `sessionId?: string | null`
- `sequence: number`（单连接内严格递增，且 `meta` 必须为 `sequence=1`）
- `payload: object`（随 type 变化）

### 3.2 最小事件类型集合（验收必需）

- `meta`（首事件）
- `progress`
- `tool.call`
- `tool.result`
- `message.delta`（assistant 文本增量）
- `evidence.update`（证据链增量）
- `warning`
- `error`（不可恢复错误）
- `final`（末事件）

### 3.3 强制事件序列规则（验收必需）

- **首事件**必须为 `meta` 且 `sequence=1`。
- **末事件**必须为 `final`，且 `final` 后不得再输出任何事件。
- **不可恢复错误**：必须尽快输出 `error`，并紧跟 `final(payload.status=error)`。
- `sequence`：严格单调递增（不重复、不倒退；是否允许“跳号”以仓库约定为准——建议不跳号，以便客户端做丢包检测更可靠）。

### 3.4 结构化错误输出规则（流内）

- `type=error`：`payload` 必须为 `ErrorResponse`。
- `type=tool.result` 且 `payload.status=failure`：`payload.error` 必须为 `ErrorResponse`。
- `ErrorResponse.message` 必须英文；`details` 只能是结构化摘要（禁止敏感信息）。

### 3.5 取消/断连语义（可验证口径）

- 触发条件：
  - 客户端主动断开 SSE（socket close / HTTP client cancel）
  - 或前端触发“停止生成”导致连接终止
- 显式 cancel（连接未断开）：
  - 客户端调用 `POST /api/v1/chat/stream/cancel`，传入目标 `requestId`（同租户/项目隔离上下文 + RBAC 校验）。
  - 服务端收到 cancel 后必须：
    - 立刻停止后续工具调用/推理（取消向下传播）
    - 在**原 SSE 连接**内尽快输出 `final(payload.status=cancelled)`
    - 确保 `final` 后不再输出任何事件（包含 progress/warning/tool/message/evidence 等）
- 服务端行为：
  - 发现断连后：
    - 立即停止向 response 写入任何新 chunk（避免 BrokenPipe 循环）
    - 向下传播取消信号：
      - 推理/编排层：停止继续生成 `message.delta`
      - 工具层：停止发起后续 tool attempt；若工具支持 `should_cancel`，必须尽快中止
  - 结束事件策略：
    - **断连场景**：连接断开后无法保证事件送达，因此验收以“停止计算/停止下游”作为硬指标，不强制要求客户端收到 `final(cancelled)`。
    - **显式 cancel 场景**：连接未断开时必须保证输出 `final(status=cancelled)`。

## 4. 需要修改/新增的文件清单（仅列举，不写代码）

### 4.1 契约文档（单一事实源收敛）

- `docs/contracts/api-and-events-draft.md`
  - **修订 6.1.2**：将 SSE 事件结构从 `type + envelope + payload` 改为“扁平顶层字段”描述，且补充“payload 禁止重复上下文字段”的等价约束表述。
  - **补齐/对齐最小事件 payload 字段**：
    - `message.delta.payload.delta`
    - `evidence.update.payload.mode/evidence?/evidenceId?`
  - **补齐显式取消端点契约**：新增 `POST /api/v1/chat/stream/cancel`（请求/响应/错误码/权限）。
    - 请求体：至少包含 `requestId`（被取消的流的 requestId）。
    - 约束：必须做 RBAC + `tenantId/projectId` 隔离校验；取消跨隔离的 requestId 必须返回 `FORBIDDEN` 或 `AUTH_ERROR`（以现有鉴权策略为准，但必须稳定映射到 `ErrorResponse`）。
    - 响应：建议返回 `{"status":"ok"}` 或等价最小结构；失败返回 `ErrorResponse`（英文 message）。
  - **明确 progress/warning 的 message 语言策略**：
    - ErrorResponse.message 英文（强制）
    - progress/warning 的 message 允许中文（contracts 当前允许），但建议保留英文可检索字段（至少 `code`）。

### 4.2 后端 SSE schema 与编码/序列化

- `backend/gangqing/schemas/sse.py`
  - 新增 `message.delta` 与 `evidence.update` 的 Pydantic 模型（Schema First）。
  - 明确 `sequence` 为正整数、严格递增；必要时在构造器/emit 层集中管理。
- `backend/gangqing/api/chat.py`
  - SSE 输出必须覆盖最小集合：至少在成功路径中稳定出现：
    - `meta` -> `progress` -> `tool.call` -> `tool.result` -> `message.delta`(>=1) -> `final(success)`
    - 若拿到 Evidence：输出 `evidence.update`（>=1）
  - 错误路径必须稳定复现：`meta` -> ... -> `error` -> `final(error)` 并终止。
  - 取消传播：断连后必须停止 watcher/工具线程、停止 drain 队列，且不再 emit 新事件。
  - 事件 `data:` 必须单行 JSON（当前实现 `json.dumps` 输出单行，需保持）。
- `backend/gangqing/api/chat_cancel.py`（或合并到现有模块，按现有路由分层为准）
  - 新增 `POST /chat/stream/cancel`（挂载到 `/api/v1` 前缀后为 `/api/v1/chat/stream/cancel`）。
  - 关键行为：根据 `requestId` 定位并触发对应 SSE 连接的 cancel token，使该连接输出 `final(status=cancelled)`。
  - 安全：必须依赖注入 `RequestContext`；要求 capability（建议新增 `chat:conversation:cancel` 或复用 `chat:conversation:stream`，以 RBAC 配置为准）。

### 4.3 测试与脚本（真实服务，不可 skip）

- `backend/scripts/sse_smoke_test.py`
  - 增强断言：
    - `sequence` 单调递增
    - `requestId` 贯穿
    - 错误事件 `error.payload` 完整字段 + `message` 英文
    - 成功路径出现 `message.delta`（>=1）
    - 若成功路径出现 `evidence.update`，验证其为增量语义（mode 与 evidence/evidenceId 的对应关系）
- `backend/scripts/chat_stream_retry_smoke_test.py`
  - 使其不依赖 `event:` 行（或至少在解析层“以 JSON.type 为准”），与 contracts 6.1.1 对齐。
- **新增** `backend/scripts/sse_cancel_smoke_test.py`（建议）
  - 目的：用自动化方式证明“显式 cancel -> final(cancelled)”与“断连取消向下传播”。
  - 验收断言（建议）：
    - 显式 cancel：
      - 客户端先发起 SSE 请求并开始读事件（至少读到 `meta` 或 `progress`）
      - 另起一个 HTTP 请求调用 `POST /api/v1/chat/stream/cancel`（携带相同 tenant/project + auth），取消该 SSE 的 `requestId`
      - 断言 SSE 流最终收到 `final(payload.status=cancelled)`，且 `final` 后无任何额外事件
    - 断连取消：
      - 客户端在收到 `tool.call` 或某个 `progress(stage=tooling)` 后主动断开连接
      - 服务端在合理时间窗口内停止产生新 tool attempt（通过读取服务端 stdout 中的结构化日志关键字段或通过审计表/指标验证）
    - 该脚本必须连接真实 FastAPI + 真实 Postgres；缺配置直接失败。
- `backend/tests/`（单元测试）
  - 新增/增强：SSE 事件 schema 校验、错误映射规则、sequence 生成器纯逻辑（允许依赖注入 fake clock/fake emitter，但不得 mock 外部服务做“集成通过”）。

## 5. 单元测试验收口径（pytest -q）

> 单元测试聚焦“纯逻辑/校验/序列规则/错误同构”，不替代真实集成冒烟。

必须覆盖的断言点（最少集合，建议都写成可断言的 JSON schema 校验）：

- **Schema 合法性**：
  - `SseMetaEvent/SseProgressEvent/SseToolCallEvent/SseToolResultEvent/SseWarningEvent/SseErrorEvent/SseFinalEvent`
  - `message.delta` 与 `evidence.update`
- **序列规则**：
  - `meta` 必须为首事件且 sequence=1
  - 任意事件 sequence 严格递增
  - `final` 必须为最后一条；在构造层保证不会在 final 后继续 emit
- **错误同构**：
  - `type=error.payload` 与 REST ErrorResponse 字段一致
  - `tool.result.status=failure` 时 `payload.error` 为 ErrorResponse
  - `ErrorResponse.message` 为英文（至少不包含中文字符；更严格可用“英文句子模板”约束）
- **取消传播（逻辑层）**：
  - 一旦 cancel flag 置位：不再允许 emit 新事件；工具 should_cancel 被调用并在逻辑上终止后续 attempt。
  - 显式 cancel 端点：
    - 校验 requestId 的基本格式与存在性（无效 => `VALIDATION_ERROR`）
    - 取消不存在/已完成的 requestId 的返回策略（需稳定且可测试）：
      - 推荐：返回 200 但 `{"status":"not_found"}`（避免泄露链路存在性），或返回 `NOT_FOUND`（两者二选一，contracts 中必须明确）
    - 跨租户/项目取消必须失败并返回结构化错误（`FORBIDDEN`/`AUTH_ERROR`）。

## 6. 冒烟测试验收口径（真实服务）

统一命令：

- `backend/scripts/sse_smoke_test.py`
  - 成功链路：包含最小事件序列且最终 `final(success)`
  - 失败链路：包含 `error` + `final(error)`
  - requestId 贯穿 + sequence 单调递增
- `backend/scripts/chat_stream_retry_smoke_test.py`
  - 验证重试可观测：多次 `tool.call` + `warning` + 最终错误路径
- `backend/scripts/sse_cancel_smoke_test.py`（新增后）
  - 验证显式 cancel 能收到 `final(status=cancelled)`（连接未断开）
  - 验证断连后服务端停止继续输出 & 停止后续工具调用/推理（可通过日志/审计/计数器取证）

约束：

- 缺少关键 env（如 DB/Bootstrap 用户等）必须失败。
- 依赖不可用（Postgres 无法连接、迁移失败、服务端起不来）必须失败。
- 不得使用 skip。

## 7. 里程碑拆分（对应你给的 15.1/15.2/15.3）

### 7.1 Task 15.1 — SSE endpoint 与最小事件集合/序列规则对齐

- 产出：
  - 后端 schema 补齐 `message.delta/evidence.update`
  - 服务端成功路径稳定输出最小序列
  - 文档 contracts 修订为扁平结构（单一事实源）
- 验收：增强后的 `sse_smoke_test.py` 成功通过

### 7.2 Task 15.2 — 结构化错误在流中的输出规则（error + final）

- 产出：
  - 明确错误来源映射：VALIDATION/AUTH/FORBIDDEN/UPSTREAM_TIMEOUT/CONTRACT_VIOLATION/INTERNAL_ERROR/GUARDRAIL_BLOCKED
  - `retryable` 策略与 error->final 终止规则
- 验收：
  - 单元测试覆盖 error payload 完整性与英文 message
  - `chat_stream_retry_smoke_test.py` 覆盖可恢复（warning）与最终不可恢复（error+final）

### 7.3 Task 15.3 — 取消传播（断连/取消 -> 停止输出与停止工具调用）

- 产出：
  - 取消信号来源与传播路径在代码结构上清晰：HTTP disconnect -> cancel flag -> tool/llm stop
  - 新增 cancel 冒烟脚本 + 单元测试断言
- 验收：
  - `sse_cancel_smoke_test.py` 可重复稳定通过（真实服务）

## 8. 风险点与注意事项（实现阶段必须处理）

- **契约漂移风险**：contracts 当前既有“扁平 envelope”描述（2.1.0.1）又有“envelope 对象”描述（6.1.2），必须在实现前完成收敛，否则前后端/测试会长期分裂。
- **event: 行依赖风险**：现有 `chat_stream_retry_smoke_test.py` 会读 `event:` 行；需按 contracts 改为“以 JSON.type 为准”。
- **progress/warning 文案语言冲突**：contracts 对 progress/warning 允许中文，但全局编码规范强调“错误 message 英文”。实现阶段需明确：
  - `ErrorResponse.message` 严格英文
  - progress/warning message 可中文，但必须可检索（code/结构化日志）
- **取消时 final(cancelled) 的可达性**：断连后无法再发送事件，验收应以“停止计算”作为硬指标，而不是强制一定收到 `final(cancelled)`。

