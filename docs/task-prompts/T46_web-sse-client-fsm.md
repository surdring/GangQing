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
- PRD: docs/requirements.md（R13.2/R6.3）
- TDD: docs/design.md（3.5）
- tasks: docs/tasks.md（任务 46）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 46.1（SSE 客户端 FSM：状态与事件）
2) Task 46.2（重连/超时/重试策略）
3) Task 46.3（取消传播与 UI）

# Verification
- Unit: `npm -C web test`
- Smoke: `npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`

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
- tasks: docs/tasks.md（46.1）

# Execution Plan
1) 定义事件 schema 与解析器。
2) 实现 FSM 与状态转换。

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

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（FSM 需处理 evidence.update）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？（前端需透传 requestId）
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
