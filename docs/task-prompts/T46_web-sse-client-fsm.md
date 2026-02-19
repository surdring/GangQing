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
输出修改文件完整内容 + 测试命令。
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
