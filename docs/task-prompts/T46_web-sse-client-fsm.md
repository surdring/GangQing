### Task 46 - （L1）前端 SSE 客户端状态机：loading/error/cancel/retry/timeout 与取消向下传播（Umbrella）

```markdown
# Context
你正在执行第 46 号任务：前端 SSE 客户端状态机。
角色：**技术负责人/架构师**。
目标是规划 SSE 连接管理、事件解析、断线重连、超时与重试、取消传播，以及 UI 状态表达（loading/error/cancel/retry）。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **TypeScript Strict（强制）**: 禁止 `any`。
- **Schema 单一事实源**: 前端 SSE 事件用 Zod 校验。
- **结构化错误（强制）**: `code/message(英文)/details?/retryable/requestId` 必须可解析。
- **取消传播（强制）**: 客户端取消必须通知后端并中断后续输出（按后端协议）。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R6.1/R6.3/R13.2）
- TDD: docs/design.md（2.10.1、3.5、6.4）
- contracts（权威）：docs/contracts/api-and-events-draft.md（6.1 SSE Envelope、事件序列、`POST /api/v1/chat/stream/cancel`）
- tasks: docs/tasks.md（任务 46）

# Scope (In/Out)
In:
- SSE 客户端连接与事件消费的有限状态机（FSM），覆盖 `idle/connecting/streaming/completed/error/canceled/retrying/timeout`（命名可不同，但语义必须覆盖）。
- SSE 事件运行时契约校验（Zod），校验失败的错误路径与可观测信息收敛。
- 重连/超时/重试策略（指数退避 + 上限 + UI 可感知）。
- 取消传播：前端主动断开 SSE + 调用显式取消端点（如后端能力声明 `cancellationSupported=true`）。
- UI 状态表达：loading/error/cancel/retry/timeout 的可见提示与交互。

Out:
- 不在本任务实现后端 SSE 事件协议或取消端点（但必须以 contracts 草案为权威，确保前端对齐并可联调验收）。
- 不在本任务引入新的 UI 框架/全局状态管理重构（仅在现有组件/Hook 范围内落地）。

# Key Invariants (必须遵守)
- SSE 对外事件以 contracts 草案为权威：**扁平 envelope**（`type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`），不得依赖 `event:` 行。
- `meta` 必须为首事件；`final` 必须为最后一个事件；错误必须 `error` 后紧跟 `final(status=error)`。
- 任何可展示给用户的错误文案可中文，但对外结构化错误 `message` 字段必须为英文（便于日志检索）。
- 取消传播必须可自动化验证：至少能证明“取消后服务端停止继续输出/停止后续工具调用”。

# Execution Plan
1) Task 46.1（SSE 客户端 FSM：状态与事件）
2) Task 46.2（重连/超时/重试策略）
3) Task 46.3（取消传播与 UI）

# Deliverables Definition (交付物定义)
- [ ] **Directory / Files**（必须列出新增/修改文件）
  - Web SSE Hook / FSM：`web/hooks/useChatSseStream.ts`（或拆分为 `web/hooks/sse/*`，以实际落盘为准）
  - SSE 事件 Zod Schema：`web/schemas/*`（如 `web/schemas/sseEvent.ts`；以实际落盘为准）
  - Error/Evidence Schema：复用并扩展 `web/schemas/errorResponse.ts`、`web/schemas/evidence.ts`
  - UI 交互：`web/components/ChatInterface.tsx`、`web/components/ChatMessage.tsx`（若需要展示 retry/cancel/timeout 状态）
- [ ] **SSE Event Contracts (Zod)**
  - 事件最小集合：`meta/progress/tool.call/tool.result/message.delta/evidence.update/warning/error/final`
  - 必填字段：`type/timestamp/requestId/tenantId/projectId/sequence/payload`
  - 校验失败策略：进入 `error`（或等价）并提供可定位信息（包含 `requestId` 如可获取）。
- [ ] **Cancellation Contract**
  - 显式取消端点：`POST /api/v1/chat/stream/cancel`（请求体仅 `requestId`）
  - 客户端行为：先触发本地 FSM `canceled`，再主动断开 SSE，并在能力允许时调用 cancel 端点。
- [ ] **Timeout/Retry Policy**
  - connect timeout / first-progress timeout / idle timeout（明确阈值来源：配置常量或可注入参数；禁止硬编码魔法数字散落）
  - retry：指数退避 + 最大次数；超过上限进入 `error` 并可手动 retry。
- [ ] **Observability**
  - `requestId` 贯穿：SSE 事件解析与 UI 状态必须绑定 `requestId`，便于审计/排障。

# Verification
- Unit: `npm -C web test`
- Smoke: `npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`
- 约束：冒烟必须连真实后端与真实依赖；缺少配置或服务不可用必须失败（不得 skip）。

# 联调检查清单（客户端 FSM）
- [ ] FSM 状态是否至少覆盖并可观测：`idle`/`connecting`/`streaming`/`completed`/`error`/`canceled`/`retrying`/`timeout`（命名可不同，但语义必须覆盖）？
- [ ] 每条 SSE 事件是否都经过 Zod runtime 校验：
  - [ ] 校验成功 => 驱动状态更新与 UI 渲染
  - [ ] 校验失败 => 进入 `error` 状态（或等价状态），并保留可定位信息（含 `requestId` 若可获取）
- [ ] 是否支持并正确处理最小事件序列：`progress` -> `tool.call` -> `tool.result` -> `message.delta`(>=1) -> `final`？
- [ ] 收到 `final` 后：
  - [ ] 是否停止继续消费事件/停止追加渲染？
  - [ ] 是否进入稳定的 `completed` 状态，避免重复触发完成回调？
- [ ] 收到 `error` 事件后：
  - [ ] 是否能解析结构化错误字段：`code/message(英文)/details?/retryable/requestId`？
  - [ ] 是否依据 `retryable` 决定是否进入 `retrying` 状态并展示“重试”入口？
- [ ] 超时策略是否明确且可测试：
  - [ ] 连接建立超时（connect timeout）
  - [ ] 首包/首个 `progress` 超时（first-byte/first-progress timeout）
  - [ ] 长时间无事件超时（idle timeout）
- [ ] 重连策略是否明确且有上限（避免无限重连导致资源耗尽），并且 UI 可感知（重连中/重连失败）？
- [ ] 取消传播是否端到端一致：
  - [ ] 前端点击取消 => FSM 进入 `canceled`（或等价）
  - [ ] 前端是否主动关闭 SSE 连接
  - [ ] 是否调用后端的“取消/中断”机制（按契约约定），并在 E2E 冒烟中可验证后端确实停止继续推理/工具调用
- [ ] `backend/scripts/web_sse_e2e_smoke_test.py` 是否覆盖：
  - [ ] 正常链路最小事件序列解析
  - [ ] 错误链路结构化 `error` 解析（含英文 `message`）
  - [ ] 取消链路（若后端已提供取消能力）：取消后无继续输出

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 46.1 - SSE 客户端：事件解析 + FSM（loading/error/cancel/retry/timeout）

```markdown
# Context
你正在执行子任务：46.1 - SSE 客户端：事件解析 + FSM。

# Critical Rules
- **Zod 校验事件**。
- **错误必须结构化可解析**。

# References
- PRD: docs/requirements.md（R6.1/R6.3/R13.2）
- TDD: docs/design.md（2.10.1、3.5）
- contracts（权威）：docs/contracts/api-and-events-draft.md（6.1.2/6.1.3/6.1.4）
- tasks: docs/tasks.md（46.1）

# Target Files
- `web/hooks/useChatSseStream.ts`
- `web/schemas/errorResponse.ts`
- `web/schemas/evidence.ts`
- `web/components/ChatInterface.tsx`（如需将 FSM 状态映射到 UI）
- （若新增）`web/schemas/sseEvent.ts`、`web/hooks/sse/fsm.ts`

# Execution Plan
1) 定义事件 schema 与解析器。
2) 实现 FSM 与状态转换。

# Implementation Notes (约束要点)
- SSE 事件 envelope 必须按 contracts 草案的扁平结构解析：`type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`。
- 必须支持最小事件序列：`meta` -> `progress` -> `tool.call` -> `tool.result` -> `message.delta`(>=1) -> `final`。
- 解析 `error` 事件时：`payload` 必须可解析为 `ErrorResponse`；`message` 字段必须英文。
- 解析 `warning` 事件时：`payload.message` 必须英文；用于驱动降级 UI（例如 Evidence 缺失）。
- 解析 `evidence.update` 事件时：必须更新 Context Panel 的 Evidence 列表；并处理 `mode=append|update|reference` 三种模式。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 46.2 - SSE 客户端：重连/超时/重试策略（指数退避 + 上限 + UI 可感知）

```markdown
# Context
你正在执行子任务：46.2 - SSE 客户端：重连/超时/重试策略。
你的目标是让前端在断线、无事件、可重试错误等场景下表现稳定、可观测且可自动化验收。

# Critical Rules
- **TypeScript Strict（强制）**：禁止 `any`。
- **No Infinite Retry**：必须有上限；避免资源耗尽。
- **Structured Errors**：重试决策必须基于可解析字段（例如 `ErrorResponse.retryable`）。
- **No Skip**：测试缺配置/依赖不可用必须失败。

# References
- PRD: docs/requirements.md（R6.1/R6.3/R13.2/R14.1）
- TDD: docs/design.md（2.2.2、2.10.1、6.4）
- contracts（权威）：docs/contracts/api-and-events-draft.md（6.1 事件序列、error/final 规则）
- tasks: docs/tasks.md（46.2）

# Target Files
- `web/hooks/useChatSseStream.ts`
- （若拆分）`web/hooks/sse/retryPolicy.ts`、`web/hooks/sse/timeouts.ts`、`web/hooks/sse/backoff.ts`
- `web/components/ChatInterface.tsx`（重连中/重试入口的 UI）

# Execution Plan (具体步骤)
1) 明确并实现超时类型
- connect timeout：连接建立超过阈值
- first-progress timeout：连接后在阈值内未收到 `progress`（或未收到任意业务事件，按契约选择）
- idle timeout：长时间无事件（心跳缺失场景）

2) 明确并实现重试策略
- 指数退避（backoff）与抖动（jitter）
- 最大重试次数（maxAttempts）与总时长上限（如适用）
- retryable 判定：优先依据 `error.payload.retryable`；对网络断开等“无结构化 error”场景，按连接错误类型映射为可重试或不可重试

3) UI 可感知
- retrying/timeout 状态必须可见：显示“重连中/重试中/重试失败”
- 提供手动 retry 入口（当自动重试耗尽或错误不可重试时）

# Verification (验收标准)
- **Automated Tests (Unit)**: `npm -C web test`
  - 至少覆盖：
    - 可重试错误（`retryable=true`）进入 retrying 并在成功后回到 streaming/completed
    - 不可重试错误（`retryable=false`）直接进入 error 并停止自动重试
    - connect/idle/first-progress timeout 触发 timeout 状态并停止消费
- **Smoke (Real Integration)**: `backend/scripts/web_sse_e2e_smoke_test.py`
  - 覆盖至少 1 个失败链路：例如后端返回结构化 `error`（含英文 `message`）并验证前端能稳定收尾（`final` 后停止）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Task 46.3 - SSE 客户端：取消传播（断开 SSE + 显式 cancel API）与 UI 交互

```markdown
# Context
你正在执行子任务：46.3 - SSE 客户端：取消传播与 UI。
你的目标是实现端到端一致的“用户取消”语义，并确保后端能观测到取消，从而停止推理/停止后续工具调用。

# Critical Rules
- **Read-Only Default**：本任务不涉及任何写操作能力。
- **Cancellation Propagation（强制）**：前端取消必须向下传播（断开 SSE + 调用取消端点，按能力声明）。
- **Isolation（强制）**：取消请求必须在同一 `tenantId/projectId` 作用域内，避免跨域取消。
- **Auditable**：取消行为必须可通过 requestId 关联审计与排障。

# References
- PRD: docs/requirements.md（R6.3/R13.2）
- TDD: docs/design.md（2.2.2、2.10.1、6.4）
- contracts（权威）：docs/contracts/api-and-events-draft.md（6.1.6 `POST /api/v1/chat/stream/cancel`）
- tasks: docs/tasks.md（46.3）

# Target Files
- `web/hooks/useChatSseStream.ts`
- `web/components/ChatInterface.tsx`
- `web/schemas/errorResponse.ts`（用于取消端点的结构化错误解析，若前端统一复用）

# Execution Plan (具体步骤)
1) 设计并实现取消触发点
- 用户点击“停止生成/取消”按钮
- 离开页面/组件卸载（需要可靠清理）

2) 取消传播策略（按 contracts 与能力声明）
- 立即：FSM 进入 `canceled`（或等价）并停止追加渲染
- 立即：主动关闭 SSE 连接（EventSource/ReadableStream abort）
- 若 `meta.payload.capabilities.cancellationSupported=true`：调用 `POST /api/v1/chat/stream/cancel`，请求体仅包含 `requestId`

3) UI 行为
- cancel 后必须展示“已取消”且不再出现新的 `message.delta`
- 若 cancel API 失败：展示可解析错误（对外 `message` 英文，但 UI 可中文提示），并保证不会恢复流式输出

# Verification (验收标准)
- **Automated Tests (Unit)**: `npm -C web test`
  - 至少覆盖：
    - cancel 触发后 FSM 进入 canceled，且 `final`/后续事件不再驱动渲染
    - cancel API 返回结构化错误时的错误收敛（包含 `code/message/requestId/retryable`）
- **Smoke (Real Integration)**: `backend/scripts/web_sse_e2e_smoke_test.py`
  - 覆盖取消链路：取消后后端不再继续输出（至少可通过日志/事件序列证明）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（FSM 需处理 evidence.update）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？（前端需透传 requestId）
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？

