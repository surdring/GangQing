# Task 4 - 实现意图识别与策略路由（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 4 组任务：实现意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）。
你的角色是 **技术负责人/架构师**。
你的目标是定义意图分类 schema、路由策略、默认只读与高风险拦截、以及 SSE 中的过程事件输出规范。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端对外 I/O/配置用 Zod；后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic。
- **Read-Only Default**: 默认只读；任何写意图必须进入 `ACTION_PREPARE`，`ACTION_EXECUTE` 默认禁用或需审批链。
- **RBAC + 审计 + requestId 贯穿**: 意图识别结果与路由决策必须可审计。
- **结构化错误**: 对外错误必须包含 `code/message(英文)/details?/retryable/requestId`。
- **流式输出（SSE）**: 必须输出 `progress`（意图识别阶段）与 `warning`（降级/不确定项）。
- **真实集成测试（No Skip）**: 冒烟测试需启动真实服务并走完整 SSE 链路。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#3、功能模块）
- TDD: `docs/技术设计文档-最佳实践版.md`（#6）
- tasks: `docs/tasks.md`（Task 4）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) Task 4.1 - 定义意图分类输出 schema
- Deliverables: Pydantic 意图模型（含置信度/不确定项），并确保能映射到 SSE `progress`/`warning`。

2) Task 4.2 - 路由规则与只读默认策略
- Decisions:
  - 不明确请求一律降级为 `QUERY/ANALYZE`。
  - 写意图触发强拦截与 HITL 预留。

3) Task 4.3 - SSE 事件输出规范
- Deliverables: 意图识别阶段的 `progress` 事件与路由决策 `warning` 事件策略。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/intent_routing_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 4.1 - 意图分类 schema 与结果校验

```markdown
# Context
你正在执行子任务：4.1 - 意图分类 schema。
你的目标是用 Pydantic 定义意图分类结果模型，并在运行时校验模型输出，失败时降级。

# Critical Rules
- **Schema 单一事实源**: 意图模型必须 Pydantic 定义并校验。
- **Read-Only Default**: 分类不确定时不得进入写路径。
- **结构化错误**: 校验失败必须映射为结构化错误（message 英文）。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#6.1）
- tasks: `docs/tasks.md`（Task 4）

# Execution Plan
1) 定义 `IntentType` 枚举与输出模型（含 confidence/uncertainties）。
2) 在编排层对模型输出做校验；失败重试或降级为 `QUERY`。

# Verification
- 单元测试覆盖：正常分类、不确定、校验失败、降级。

# Output Requirement
- 输出代码与测试。
```

### Task 4.2 - 路由规则与高风险拦截（只读默认）

```markdown
# Context
你正在执行子任务：4.2 - 路由规则与高风险拦截。
你的目标是实现意图到执行策略的路由：只读默认、写意图强拦截、HITL 预留。

# Critical Rules
- **Read-Only Default**: `ACTION_EXECUTE` 默认禁用。
- **RBAC + 审计**: 路由决策必须记录审计（含 requestId、intent）。

# References
- PRD: `docs/产品需求.md`（F4.*）
- TDD: `docs/技术设计文档-最佳实践版.md`（#6.2）
- tasks: `docs/tasks.md`（Task 4）

# Execution Plan
1) 定义路由表与策略（允许的 intent -> handler）。
2) 对写意图：返回结构化错误或进入 `ACTION_PREPARE`（仅生成草案）。
3) 输出 SSE `warning` 解释降级原因（不含敏感信息）。

# Verification
- 单元：越权写意图被阻断并审计。

# Output Requirement
- 输出代码与测试。
```

### Task 4.3 - SSE 过程事件：progress 与 warning

```markdown
# Context
你正在执行子任务：4.3 - SSE 过程事件输出。
你的目标是把意图识别阶段与降级信息通过 SSE `progress`/`warning` 事件输出，便于前端分段渲染。

# Critical Rules
- **流式输出（SSE）**: 事件必须可解析且字段与契约一致。
- **结构化错误**: SSE `error` 事件必须结构化。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#4.2）
- tasks: `docs/tasks.md`（Task 4）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) 在意图识别开始/结束输出 `progress`。
2) 在降级或不确定项时输出 `warning`（含原因与建议下一步）。
3) 更新/补齐相关契约测试。

# Verification
- 冒烟测试：`backend/scripts/intent_routing_smoke_test.py` 验证事件序列与字段。

# Output Requirement
- 输出代码与测试。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局硬约束写入）
- [x] 是否包含只读默认与审批链要求（写意图拦截）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
