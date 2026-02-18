# Task 12 - 前端对话与 SSE 客户端状态机（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 12 组任务：前端对话与 SSE 客户端状态机（loading/error/cancel/retry/timeout）。
你的角色是 **技术负责人/架构师**。
你的目标是定义前端 SSE 客户端契约解析、状态机、取消传播与错误展示策略，并保证与后端契约一致。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**:
  - 前端：对外 I/O、SSE 事件、配置必须用 Zod。
  - 后端：对外 I/O/工具参数/Evidence/审计事件必须用 Pydantic。
- **流式输出（SSE）**: 必须支持分段渲染 `message.delta`、阶段 `progress`、结构化 `error`。
- **结构化错误**: 解析并展示 `code/message(英文)/details?/retryable/requestId`；UI 可中文，但结构化字段不变。
- **RBAC + 审计 + requestId**: 前端必须在日志/上报中带 requestId（若后端提供）。
- **配置外部化**: API base URL/超时/重试次数不得硬编码，需配置化并 Zod 校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实后端 SSE；不可用/缺配置必须失败并输出英文错误。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#112-114）
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.1、#4.2）
- tasks: `docs/tasks.md`（Task 12）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) Task 12.1 - Zod 定义 SSE 事件 schema 并实现解析器
2) Task 12.2 - SSE 连接管理与状态机（loading/error/cancel/retry/timeout）
3) Task 12.3 - E2E 冒烟脚本（真实后端）

# Verification
- Unit: `npm test`
- Smoke: `npm run build && node web/scripts/sse_e2e_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 12.1 - Zod：SSE 事件 schema + 解析器（严格校验）

```markdown
# Context
你正在执行子任务：12.1 - SSE 事件 schema 与解析器。
你的目标是用 Zod 定义事件 envelope 与 payload，并在前端解析时严格校验，遇到不符合契约的事件要产生结构化错误展示（保留 requestId）。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: SSE 事件必须 Zod。
- **结构化错误**: 解析失败要映射为结构化错误对象（message 英文）。

# References
- contracts: `docs/contracts/api-and-events-draft.md`
- tasks: `docs/tasks.md`（Task 12）

# Execution Plan
1) 定义 Zod schema（事件类型联合）。
2) 实现解析器并返回类型安全事件。

# Verification
- 单元测试：覆盖正常事件、未知 type、字段缺失、error 事件。

# Output Requirement
- 输出代码与测试。
```

### Task 12.2 - SSE 状态机：连接/重连/取消/超时/重试

```markdown
# Context
你正在执行子任务：12.2 - SSE 状态机。
你的目标是实现连接管理：开始/进行中/完成/错误/取消/超时，支持断线重连与取消向后端传播（若协议支持）。

# Critical Rules
- **流式输出**: UI 可分段渲染。
- **结构化错误**: 错误必须可解析并展示 requestId。
- **配置外部化**: 超时/重试次数配置化并 Zod 校验。

# References
- PRD: `docs/产品需求.md`
- tasks: `docs/tasks.md`（Task 12）

# Execution Plan
1) 定义状态机与事件驱动更新。
2) 实现取消与超时。

# Verification
- 单元测试：取消、超时、重连。

# Output Requirement
- 输出代码与测试。
```

### Task 12.3 - 冒烟：sse_e2e_smoke_test.mjs（真实后端）

```markdown
# Context
你正在执行子任务：12.3 - SSE E2E 冒烟。
你的目标是实现 `web/scripts/sse_e2e_smoke_test.mjs`，对真实后端发起 SSE 对话请求并断言事件序列与结构化错误。

# Critical Rules
- **真实集成测试（No Skip）**: 缺少后端地址或后端不可用，测试必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 12）

# Execution Plan
1) 从环境变量读取后端地址。
2) 发起 SSE 请求并收集事件。
3) 断言至少包含 progress/message.delta/final（错误链路断言 error）。

# Verification
- `npm run build` 通过且冒烟脚本通过。

# Output Requirement
- 输出脚本与相关配置加载代码。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？（结构化错误对象 message 英文）
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（通过解析 evidence.update 支持）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
