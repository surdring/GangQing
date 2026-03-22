# T46 前端 SSE 客户端 FSM 执行蓝图

本计划在不改变现有 `useChatSseStream` 对外 API（仅 `isProcessing/sendMessage/cancelActiveRequest`）的前提下，为 SSE 连接管理、事件解析、断线重连、超时与重试、取消传播与 UI 状态表达制定可实现且可验证的蓝图。

## 0. 权威约束与结论（Single Source of Truth）

- **权威契约**：`docs/contracts/api-and-events-draft.md`（6.1 SSE Envelope、事件序列、6.1.6 取消端点）。
- **强制不变式（必须满足）**
  - **Envelope 扁平结构**：顶层 `type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`。
  - **事件序列**：`meta` 必须为首事件（期望 `sequence=1`）；`final` 必须为最后事件；错误链路 `error` 后紧跟 `final(status=error)`。
  - **错误同构**：`type=error` 的 `payload` 必须为 `ErrorResponseSchema`（`code/message(英文)/details?/retryable/requestId`）。
  - **取消传播**：客户端取消必须调用 `POST /api/v1/chat/stream/cancel`（请求体仅 `requestId`），并在服务端可验证“取消生效后不得再出现新的 `tool.call`”。
  - **TypeScript Strict**：不引入 `any`；未知类型使用 `unknown + Zod`。
  - **No Code Implementation（本阶段）**：仅输出蓝图与验收策略。

## 1. 现状盘点（只读结果）

### 1.1 现有 Hook（`web/hooks/useChatSseStream.ts`）能力

- **已具备**
  - `fetch(POST /api/v1/chat/stream)` 读取 `ReadableStream`，按 `\n\n` 分帧解析 `data:`。
  - 对每条 `data` 执行 `JSON.parse`，并用 `SseEnvelopeSchema.safeParse` 做 runtime 校验。
  - 对 `sequence` 做严格单调递增校验；乱序/跳号视为契约违约并上报结构化错误。
  - 基于 `SseReconnectConfig` 做有限次数重试（指数退避 + jitter + maxAttempts）。
  - `cancelActiveRequest` 会：`abort()` + 调用 `POST /api/v1/chat/stream/cancel`。
- **当前缺口（与任务 In-scope 对齐）**
  - **FSM 语义不显式**：只有 `isProcessing`，UI 无法区分 `connecting/streaming/retrying/timeout/canceled/completed/error`。
  - **超时策略缺失**：尚未定义 connect/first-progress/idle 三类超时阈值与可测试行为。
  - **meta 能力位未被消费**：`cancellationSupported` 未用于决定是否调用 cancel 端点；未把“能力声明缺失/不一致”纳入错误路径。
  - **final(status=cancelled/error/success) 语义未被用于收敛状态**：目前 `final` 一律触发 `onFinal`，但缺少对 `payload.status` 的分流（UI/可观测）。

### 1.2 Schema（`web/schemas/sseEnvelope.ts`）

- 已存在并覆盖最小集合（含 `meta/progress/tool.call/tool.result/message.delta/evidence.update/warning/error/final`）。
- `SseEvidenceUpdatePayloadSchema` 已实现 mode 级约束（append/update 必须有 evidences；reference 必须有 evidenceIds）。

### 1.3 UI 现状（`web/components/ChatInterface.tsx` / `ChatMessage.tsx`）

- UI 仅在 `stream.isProcessing` 时显示“thinking”。
- 目前无“重试中/超时/已取消/可重试错误”的显式交互。
- **约束确认（来自你的选择 B）**：本任务不改变 `useChatSseStream` 对外签名；因此 UI 状态表达将通过“现有回调 + message/actions 注入 + 错误消息/阶段提示”完成，而不是新增对外 `streamStatus`。

## 2. FSM 蓝图（内部状态机，不改变对外 API）

> 说明：FSM 是 Hook 内部实现与可观测收敛规则；对外仍维持 `isProcessing` 与现有 callbacks。UI 的“可见状态”通过现有回调产生的消息/动作来表达。

### 2.1 状态集合（内部枚举）

- `idle`
- `connecting`
- `streaming`
- `retrying`
- `completed`
- `error`
- `canceled`
- `timeout`

### 2.2 事件集合（驱动 FSM 的输入）

- **用户动作**
  - `USER_SEND(message, requestId)`
  - `USER_CANCEL(requestId)`
  - `USER_RETRY(requestId)`（由 UI Action 触发，最终映射到再次调用 `sendMessage`；本任务仅规划，不实现代码）
- **网络/读流事件**
  - `HTTP_OK_STREAM_READY`
  - `HTTP_NON_2XX(ErrorResponse?)`
  - `STREAM_CHUNK_RECEIVED`
  - `STREAM_DONE`
  - `STREAM_ABORTED`
  - `STREAM_ERROR`
- **协议事件（来自 SSE envelope.type）**
  - `SSE_META`
  - `SSE_PROGRESS`
  - `SSE_TOOL_CALL`
  - `SSE_TOOL_RESULT`
  - `SSE_MESSAGE_DELTA`
  - `SSE_EVIDENCE_UPDATE`
  - `SSE_WARNING`
  - `SSE_ERROR(ErrorResponse)`
  - `SSE_FINAL(status)`
- **本地守护事件**
  - `TIMEOUT_CONNECT`
  - `TIMEOUT_FIRST_PROGRESS`
  - `TIMEOUT_IDLE`
  - `CONTRACT_VIOLATION(JSON_PARSE | ZOD | SEQUENCE | INVARIANT_ORDER)`

### 2.3 关键转移规则（摘要）

- `idle --USER_SEND--> connecting`
- `connecting --HTTP_OK_STREAM_READY--> streaming`（但仍要求 `meta` 为首事件，否则 `CONTRACT_VIOLATION`）
- `streaming --SSE_FINAL(success)--> completed`
- `streaming --SSE_ERROR--> error` 且要求后续必须观察到 `SSE_FINAL(error)`；若未观察到也要收敛到 `error` 并记录原因。
- `connecting/streaming --USER_CANCEL--> canceled`（并执行取消传播动作，见第 4 节）
- `connecting/streaming --TIMEOUT_*--> timeout`（是否自动重试取决于策略，见第 3 节）
- `connecting/streaming --STREAM_ERROR--> retrying`（若 attempt 未耗尽）
- `retrying --backoff_elapsed--> connecting`（同 requestId，同 message，attempt+1）
- `retrying --attempt_exhausted--> error`

### 2.4 不变式检查（FSM 内建断言）

- **I1: meta-first**：第一条可解析 envelope 必须为 `type=meta`，否则 `CONTRACT_VIOLATION`。
- **I2: final-last**：观察到 `final` 后必须停止消费/停止触发 UI 回调；后续任何事件视为 `CONTRACT_VIOLATION`（或至少记录严重告警并忽略）。
- **I3: error->final(error)**：观察到 `error` 后必须期望下一条事件是 `final(status=error)`；若未满足则记录 `CONTRACT_VIOLATION`。
- **I4: sequence-monotonic**：同连接内 `sequence` 必须严格 +1。

## 3. 超时 / 重试策略（可配置、可测试、UI 可感知）

> 本节的阈值**不得硬编码散落**；应通过配置常量或可注入参数集中管理（本任务仅规划参数来源，不落实现）。

### 3.1 超时分类

- **connect timeout**：从 `USER_SEND` 到 `HTTP_OK_STREAM_READY` 的上限。
- **first-progress timeout**：从 `HTTP_OK_STREAM_READY` 到首个业务进展事件（建议：首个 `meta` 之后的 `progress` 或任一非 meta 的业务事件）上限。
- **idle timeout**：处于 `streaming` 时，连续无任何事件（含 `progress/warning/message.delta/evidence.update/tool.*`）的上限。

### 3.2 超时触发后的行为

- connect/first-progress/idle 超时触发 `timeout`。
- 若尚有剩余重试次数：进入 `retrying` 并执行指数退避。
- 若重试耗尽：进入 `error` 并给 UI 提供“手动重试”入口（通过 `message.actions` 或追加一条 assistant message 提示）。

### 3.3 重试（指数退避 + jitter + 上限）

- 复用现有 `SseReconnectConfig`：`baseDelayMs/maxDelayMs/maxAttempts`。
- 规则：`delay = min(maxDelayMs, baseDelayMs * 2^k + jitter)`。
- **禁止无限重连**：`maxAttempts` 到达必须收敛为 `error`。

## 4. 取消传播（端到端一致，可自动化验证）

### 4.1 客户端取消动作（顺序约束）

- **先**本地收敛：FSM 进入 `canceled`（UI 立即停止“thinking”并停止追加渲染）。
- **再**断开读流：终止 reader / abort fetch，停止后续 frame 处理。
- **再**显式取消端点：调用 `POST /api/v1/chat/stream/cancel`，请求体 `{ requestId }`。

### 4.2 能力位（meta.capabilities）

- `cancellationSupported=true`：执行 4.1 全流程。
- `cancellationSupported=false`：仍应本地收敛 + 断开读流；是否调用 cancel 端点必须明确策略（建议不调用，并在可观测日志中记录“server cancellation not supported”）。
- 若 `meta` 缺失/能力字段缺失：视为契约违约（`CONTRACT_VIOLATION`）。

### 4.3 可验证口径（与 contracts 对齐）

- 取消信号生效后：E2E 必须证明服务端不再发起新的 `tool.call`。
- 若 SSE 连接仍存活：服务端应输出 `final(status=cancelled)`；若连接断开，不强制客户端收到 final。

## 5. 事件解析与 Zod 校验（运行时契约）

### 5.1 解析管线（必须步骤）

- `frame`（`\n\n` 分隔） -> `extractSseData(frame)`（只取 `data:` 行） -> `JSON.parse` -> `SseEnvelopeSchema.safeParse`。

### 5.2 校验失败的统一收敛

- JSON parse 失败：
  - 产出 `ErrorResponse(code=CONTRACT_VIOLATION, message="SSE event JSON parse failed", retryable=false, requestId=...)` 并触发 `onError`。
  - FSM 进入 `error`（若仍有 attempt 可进入 retrying，但必须明确是否允许对 contract violation 自动重试；默认不自动重试）。
- Zod 校验失败 / meta-first / final-last / sequence 违约：
  - 统一映射为 `CONTRACT_VIOLATION`。
  - `details` 至少包含：`eventType/receivedSequence/expectedSequence/sessionId`（不得包含敏感信息）。

### 5.3 结构化错误要求（英文 message）

- **对外结构化错误的 `message` 必须英文**（contracts 强制）。
- UI 可以中文提示，但应基于 `code/retryable` 做本地映射，不应篡改 `ErrorResponse.message`。

## 6. UI 状态表达（不改 Hook API 的前提下）

> 由于不允许新增 `streamStatus`，UI 状态表达采用“现有回调驱动 UI”策略。

### 6.1 loading / connecting / streaming

- `isProcessing=true` 显示 thinking（现状保留）。
- `progress` 事件用于提示阶段（建议 UI 不把 `progress.message` 直接拼到 assistant content；应作为独立的“阶段提示”区域或消息 meta；本任务仅规划）。

### 6.2 retrying / timeout

- 自动重试期间：通过追加一条轻量的 assistant message 或使用 `progress(stage="retrying")` 的方式让用户可感知（契约层建议 message 英文，但 UI 可本地化展示）。
- 超过重试上限：进入错误态，展示“重试”按钮（通过 `message.actions` 机制或在 ChatInterface 层增加按钮；本任务仅定义交互与验收口径）。

### 6.3 canceled

- 用户点击取消：UI 立即停止 thinking，并提示“已取消”。
- 若后端仍输出 `final(status=cancelled)` 且连接存活：UI 可显示“已取消（服务端确认）”。

### 6.4 error

- `error.retryable=true`：UI 应展示“重试”入口。
- `error.code in {AUTH_ERROR, FORBIDDEN}`：UI 显示对应中文提示，并触发登录态处理（ChatInterface 已处理 AUTH_ERROR 清 token）。

## 7. Verification（必须真实集成测试，No Skip）

### 7.1 Unit（`npm -C web test`）覆盖点（无 mock 外部服务）

> 单元测试允许注入“fake reader/fake fetch”以模拟真实行为（仅限单元层），但必须覆盖真实协议语义与错误路径。

- **U1: 事件 Zod 校验成功路径**：最小序列 `meta -> progress -> message.delta -> final(success)` 能正确驱动回调。
- **U2: JSON parse 失败**：产生 `CONTRACT_VIOLATION`（英文 message），且包含 `requestId`。
- **U3: Zod 校验失败**：产生 `CONTRACT_VIOLATION`。
- **U4: meta-first 违约**：第一条不是 meta 必须失败。
- **U5: sequence 单调违约**：跳号/乱序必须失败，details 包含 expected/received。
- **U6: error->final 约束**：error 后未紧跟 final(error) 视为契约异常（至少记录并收敛为 error）。
- **U7: cancel 行为**：触发取消后必须停止继续消费（后续 chunk 不再驱动回调）。

### 7.2 Smoke / E2E（`npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`）覆盖点

- **S1: 成功链路**：连接真实后端，验证能收到并解析最小事件序列，最终 `final(success)`。
- **S2: 错误链路**：触发一次后端可控失败（例如权限不足/参数校验失败），验证 `error.payload` 可按 `ErrorResponseSchema` 解析，且 `message` 为英文。
- **S3: 取消链路（强制）**：
  - 发起流式请求后调用取消端点。
  - 验证：取消后服务端不再出现新的 `tool.call`（按 contracts 可验证口径）。
  - 若连接仍存活：应观察到 `final(status=cancelled)`。

## 8. 交付物（文件清单：预期修改范围）

- `web/hooks/useChatSseStream.ts`（内部 FSM/超时/重试/取消传播策略落地；对外 API 不变）
- `web/schemas/sseEnvelope.ts`（如需补齐 `final.payload`、`warning`、或扩充 events 的严格约束；优先保持与 contracts 一致）
- `web/components/ChatInterface.tsx` / `web/components/ChatMessage.tsx`（仅在需要时增加 retry/cancel/timeout 的可见交互，不做框架级重构）
- `backend/scripts/web_sse_e2e_smoke_test.py`（若缺失则补齐；必须真实后端）

## 9. 待你确认的关键点（不涉及代码）

- **是否要求严格 meta=sequence 1**：contracts 写明 meta 必须为首事件且期望 `sequence=1`；当前前端只检查单调 +1，不强制起始为 1。蓝图建议强制为 1 以增强可验收性。
- **progress.message 的语言策略**：contracts 中 `progress.payload.message` 在 6.1.4 写“允许中文”，但早先章节也强调英文可检索。建议：progress 可中文（面向用户），error/warning message 必须英文（面向日志/契约）。
