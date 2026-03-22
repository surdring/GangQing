### Task 15 - SSE 服务端输出：进度/消息增量/证据增量/结构化错误/结束事件完整序列（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 15 号任务：SSE 服务端输出：进度/消息增量/证据增量/结构化错误/结束事件完整序列。
你的角色是 **技术负责人/架构师**。
你的目标是制定 Task 15 的详细执行计划，并明确：
- SSE 端点与协议约束
- 事件序列与字段契约（可被前端分段渲染）
- 结构化错误在流中的输出规则
- 客户端取消/断开连接的取消传播与可验证策略
- 单元测试与冒烟测试的验收口径（真实服务、不可 skip）

# Critical Rules
- **NO CODE IMPLEMENTATION**: 在此阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 只输出“怎么做/分几步/改哪些文件/验收怎么验”。
- **Streaming（强制）**: 长耗时必须使用 SSE；事件必须可被前端分段渲染。
- **Schema First（强制）**:
  - 对外 SSE 事件契约必须与 `docs/contracts/api-and-events-draft.md` 一致。
  - 对外错误模型必须为 `ErrorResponse`，且与 REST 错误同构。
- **Read-Only Default（强制）**: 默认只读；任何写操作能力不在 L1 范围内，且不得通过对话/SSE 链路直接触发执行（仅允许输出草案/建议）。
- **Structured Errors（强制）**:
  - SSE 中 `type=error` 时，`payload` 必须为 `ErrorResponse`（`code/message/details?/retryable/requestId`）。
  - 不可恢复错误必须输出：`error` -> `final(status=error)`，且 `final` 后不得再输出任何事件。
  - `message` 字段（ErrorResponse.message）必须为英文。
- **Request Context（强制）**:
  - SSE 事件必须携带 `requestId/tenantId/projectId/sequence/timestamp`。
  - `sequence` 在同一 SSE 连接内必须单调递增。
- **Cancellation（强制）**: 客户端断开/取消必须向下传播，至少可验证：服务端停止继续输出 + 停止后续工具调用/推理。
- **Real Integration（No Skip）**: 所有冒烟测试必须连接真实服务；配置缺失或依赖不可用必须失败。

# References
- PRD: docs/requirements.md（R6.1/R6.2/R6.3）
- TDD: docs/design.md（3.5.1/3.5.2/3.5.3/6.4）
- tasks: docs/tasks.md（任务 15）
- contracts: docs/contracts/api-and-events-draft.md（6.1 SSE；2 ErrorResponse）

# Execution Plan
1) Task 15.1（SSE endpoint 与事件 Envelope/事件类型/序列约束对齐）
- Goal: 明确 SSE 端点、`Content-Type`、序列化规则（`data:` 单行 JSON）、以及事件 `type/envelope/payload` 结构。
- Constraints:
  - `meta` 必须为首事件
  - `final` 必须为最后一个事件
  - 事件类型通过 JSON 字段 `type` 判定（不依赖 SSE `event:` 行）
  - `envelope.sequence` 单调递增

2) Task 15.2（结构化错误在流中的输出：`error` + `final`）
- Goal: 明确不同错误来源的映射策略（校验错误/RBAC/上游超时/契约违背/内部错误），以及 `retryable` 规则。
- Constraints:
  - `error.payload` 同构 `ErrorResponse`
  - 不可恢复错误必须 `error -> final(status=error)`，并终止后续输出

3) Task 15.3（取消传播：客户端断开/取消的服务端停止策略与可验证验收）
- Goal: 明确服务端取消信号来源、传播路径、以及如何通过测试证明“停止输出/停止后续工具调用”。
- Constraints:
  - 不以“睡眠等待/猜测”验收；必须有可自动化断言

# Deliverables Definition
- [ ] **API Contract Alignment**: 明确 `POST /api/v1/chat/stream` 端点与最小事件类型集合（`meta/progress/tool.call/tool.result/message.delta/evidence.update/warning/error/final`）。
- [ ] **Event Envelope Rules**: 明确 `type + envelope + payload` 结构与字段约束（含 `sequence` 单调递增、`meta` 首事件、`final` 最后事件）。
- [ ] **Error Model**: 明确 `ErrorResponse` 字段、错误码枚举与 `retryable` 规则；对外 `message` 英文。
- [ ] **Cancellation Semantics**: 明确客户端断开/取消时的服务端行为与可验证策略。
- [ ] **Observability**: requestId 贯穿与关键日志/审计字段（至少 `requestId/sessionId/toolName/stepId`）。
- [ ] **Test Plan**: 单元测试断言点 + 冒烟测试链路（真实服务，不可 skip）。

# Verification Plan
- **Unit Tests**: `pytest -q`
- **Smoke Tests**: `backend/scripts/sse_smoke_test.py`

# 联调检查清单（服务端视角）
- [ ] SSE endpoint 是否与契约一致：`POST /api/v1/chat/stream`？
- [ ] 每条 SSE `data:` 是否为单行 JSON（禁止多行 JSON）？
- [ ] 事件类型是否以 JSON 字段 `type` 判定（不依赖 SSE `event:` 行）？
- [ ] 是否严格遵循 `type + envelope + payload`，且 **不在 payload 重复上下文字段**？
- [ ] `meta` 是否为首事件（`sequence=1`）？
- [ ] `final` 是否为最后一个事件，且 `final` 后不再输出任何事件？
- [ ] `envelope` 是否包含并只包含（以契约为准）：
  - [ ] `timestamp`
  - [ ] `requestId`
  - [ ] `tenantId`
  - [ ] `projectId`
  - [ ] `sessionId?`
  - [ ] `sequence`
- [ ] `sequence` 是否在同一 SSE 连接内严格单调递增（不得重复/倒退）？
- [ ] 事件类型是否覆盖最小集合：
  - [ ] `meta`
  - [ ] `progress`
  - [ ] `tool.call`
  - [ ] `tool.result`
  - [ ] `message.delta`
  - [ ] `evidence.update`
  - [ ] `warning`
  - [ ] `error`
  - [ ] `final`
- [ ] 最小成功事件序列是否可稳定复现：`meta` -> `progress` -> `tool.call` -> `tool.result` -> `message.delta`(>=1) -> `final(status=success)`？
- [ ] `message.delta` 是否保证“增量”语义（前端可逐段追加渲染，而非重复全量）？
- [ ] `evidence.update` 是否满足“增量更新”语义（可多次发送；前端可合并更新而非覆盖丢失）？
- [ ] `error` payload 是否为结构化错误（ErrorResponse），且包含：
  - [ ] `code`
  - [ ] `message`（英文）
  - [ ] `requestId`
  - [ ] `retryable`
  - [ ] `details?`（仅结构化上下文，禁止敏感信息）
- [ ] 不可恢复错误路径是否严格输出：`error` -> `final(status=error)`，且 `final` 后不再输出任何事件？
- [ ] `final.payload.status` 是否仅允许 `success|error|cancelled`（禁止输出 `done` 等冗余字段）？
- [ ] 客户端断开/取消时：
  - [ ] 后端是否停止继续写入 SSE（避免 BrokenPipe 循环）？
  - [ ] 是否停止后续工具调用/推理（至少可验证）？
- [ ] `backend/scripts/sse_smoke_test.py` 是否验证了：
  - [ ] 正常链路的最小事件序列
  - [ ] 至少 1 条错误链路（校验结构化 `error` 字段 + 英文 message）
  - [ ] `requestId` 贯穿

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 15.1 - SSE 事件序列：progress/tool/message/evidence/final

```markdown
# Context
你正在执行子任务：15.1 - SSE 事件序列：progress/tool/message/evidence/final。
目标是实现服务端 SSE 输出并严格遵守 contracts 的事件字段与序列。

# Critical Rules
- **Schema First**: 事件必须与 `docs/contracts/api-and-events-draft.md#6.1` 对齐。
- **NO MOCK FOR SMOKE**: 冒烟测试必须连接真实服务。
- **Event Sequence（强制）**:
  - `meta` 必须为首事件
  - `final` 必须为最后一个事件
  - `sequence` 必须单调递增
- **Parsing Rule（强制）**: 客户端与测试必须以 JSON 字段 `type` 判定事件类型。
- **Request Context（强制）**: `requestId/tenantId/projectId/sequence/timestamp` 必须在 `envelope` 中出现且可用。

# References
- tasks: docs/tasks.md（15.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 定义/对齐事件结构与字段约束
- 明确 `type + envelope + payload` 结构。
- 明确 `envelope` 必填字段与可选字段。

2) 输出最小成功序列
- `meta` -> `progress` -> `tool.call` -> `tool.result` -> `message.delta`(>=1) -> `final(status=success)`。

3) 覆盖 `evidence.update` 增量事件（如适用）
- `mode=append|update` 时，`payload.evidence` 必须满足 Evidence 最小字段与字段级约束。

# Verification
- **Unit**: `pytest -q`（至少覆盖：meta 首事件、final 最后事件、sequence 单调递增、error 同构规则的序列化/校验）。
- **Smoke**: `backend/scripts/sse_smoke_test.py`（成功链路必须稳定复现）。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---
### Task 15.2 - SSE 错误处理：`error` + `final`

```markdown
# Context
你正在执行子任务：15.2 - SSE 错误处理：`error` + `final`。

# Critical Rules
- **错误必须尽快输出**。
- **payload 同构 ErrorResponse**。
- **English Message**: ErrorResponse.message 必须为英文。
- **Final After Error**: 不可恢复错误必须严格输出：`error` -> `final(status=error)`，且 `final` 后不得再输出任何事件。

# References
- tasks: docs/tasks.md（15.2）
- TDD: docs/design.md（6.4）
- contracts: docs/contracts/api-and-events-draft.md（2 ErrorResponse；6.1 SSE）

# Target Files (建议；以实现落盘为准)
- backend/gangqing/api/*（SSE 路由与异常捕获）
- backend/gangqing/app/*（统一错误映射/RequestContext）
- backend/scripts/sse_smoke_test.py（补齐错误链路断言，如当前未覆盖）

# Execution Plan
1) 统一异常捕获并在流中输出 `error`。
2) 对不可恢复错误输出 `final` 并终止。
3) 明确 `retryable` 判定规则并对齐错误码枚举。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/sse_smoke_test.py`（覆盖一次错误路径）。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 15.3 - SSE 取消传播：客户端断开/取消 -> 服务端停止输出与停止后续调用（可验证）

```markdown
# Context
你正在执行子任务：15.3 - SSE 取消传播：客户端断开/取消 -> 服务端停止输出与停止后续调用（可验证）。
目标是让“用户停止生成/断开连接”能向下传播，避免服务端继续推理/继续调用工具，并且该行为可以被自动化测试稳定验证。

# Critical Rules
- **Cancellation Supported（强制）**: `meta.payload.capabilities.cancellationSupported` 必须与实际行为一致。
- **No Zombie Work（强制）**: 客户端断开后，服务端不得继续长时间运行推理/工具调用。
- **可验证（强制）**: 必须通过自动化测试证明“停止输出 + 停止后续调用”，禁止仅靠日志或人工猜测验收。
- **Real Integration（No Skip）**: 冒烟测试必须连接真实服务；配置缺失必须失败。

# References
- tasks: docs/tasks.md（15.3）
- PRD: docs/requirements.md（R6.1/R6.3）
- TDD: docs/design.md（2.2.2/3.5.1）
- contracts: docs/contracts/api-and-events-draft.md（6.1.4 meta.capabilities.cancellationSupported；6.1.5 取消传播验收点；6.1.6 显式取消端点契约与取消语义）

# Target Files (建议；以实现落盘为准)
- backend/gangqing/api/*（SSE 路由）
- backend/gangqing/app/*（RequestContext/依赖注入）
- backend/gangqing/agent/*（编排/推理可取消）
- backend/gangqing/tools/*（工具调用可取消）
- backend/scripts/sse_smoke_test.py（补齐取消链路断言，如当前未覆盖）

# Execution Plan
1) 明确取消信号来源
- 客户端主动关闭连接（network disconnect / user cancel）。

2) 明确服务端传播路径
- SSE 写入层检测断开后立即停止写入。
- 编排层/推理层/工具层接收到取消信号后，停止后续步骤（至少能证明“不会继续发起新的 tool.call”）。

3) 定义可验证验收口径
- 成功断言建议包含：
  - 客户端在收到 `meta`/部分事件后主动断开。
  - 服务端不会再输出新事件（连接关闭后不再写入）。
  - 服务端不会再发起新的工具调用（至少可在审计/日志/内部计数器中验证，并由测试断言）。

# Verification
- **Unit**: `pytest -q`（覆盖：断开检测、取消标志传播、停止新 tool.call 的逻辑分支）。
- **Smoke**: `backend/scripts/sse_smoke_test.py`（覆盖：断开路径至少 1 次）。
- **Smoke**: `backend/scripts/sse_cancel_smoke_test.py`（覆盖：显式取消 + 断连取消路径各至少 1 次）。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（evidence.update）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
- [x] Doc References Updated
