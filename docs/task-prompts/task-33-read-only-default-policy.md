# Task 33 - L4 策略基座：Read-Only Default 制度化落地（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 33 组任务：L4 策略基座：Read-Only Default 的制度化落地 + 写操作意图的强拦截与 HITL 预留。
你的角色是 **技术负责人/架构师**。
你的目标是定义写意图治理（prepare/approve/execute）、默认禁用执行、HITL 预留点、以及审计与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**:
  - 前端对外 I/O/配置用 Zod。
  - 后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic。
- **Read-Only Default（硬约束）**: 未显式授权与审批前不得执行写操作；写操作只允许“草案 -> 审批/多签 -> 受控执行 -> 回滚点 -> 审计”。
- **RBAC + 审计 + requestId 贯穿（硬约束）**: 所有写意图与拦截必须审计；`requestId` 必须贯穿（HTTP -> 编排 -> 工具 -> 对外响应）。
- **结构化错误（硬约束）**: 对外错误必须包含 `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **流式输出（硬约束）**: 长耗时场景优先 SSE；拦截/拒绝也应以结构化事件输出。
- **配置外部化（硬约束）**: 写操作开关/kill-switch/审批配置不得硬编码，必须配置化并校验。
- **真实集成测试（No Skip，硬约束）**: 冒烟测试必须连接真实服务；缺配置或服务不可用必须失败并输出英文错误。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F4.1）
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.3、#6.2）
- tasks: `docs/tasks.md`（Task 33）

# Execution Plan
1) Task 33.1 - 编排层：写意图强拦截与 `ACTION_PREPARE` 强制路由
2) Task 33.2 - 配置与 Kill Switch：执行路径默认禁用
3) Task 33.3 - 审计：写意图与拦截原因落库
4) Task 33.4 - 冒烟：read_only_default_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/read_only_default_smoke_test.py`

# Output Requirement
输出详细执行计划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 33.1 - 路由：写意图必须进入 ACTION_PREPARE（禁止直接执行）

```markdown
# Context
你正在执行子任务：33.1 - 写意图路由与强拦截。
你的目标是确保 `ACTION_EXECUTE` 默认禁用，所有写意图只能进入 `ACTION_PREPARE` 或被拒绝，并输出结构化拦截信息。

# Critical Rules
- **Read-Only Default**: 禁止任何未审批写操作。
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。
- **RBAC + 审计 + requestId**: 记录意图、用户、角色与拦截原因。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 33）

# Execution Plan
1) 定义写意图识别规则与路由表。
2) 对 `ACTION_EXECUTE`：返回结构化错误（或进入 HITL）。
3) 输出 SSE `warning/error` 解释拒绝原因。

# Verification
- 单元测试：写意图被拦截；审计落库。

# Output Requirement
- 输出代码与测试。
```

### Task 33.2 - 配置与 Kill Switch：执行路径默认禁用

```markdown
# Context
你正在执行子任务：33.2 - 执行路径默认禁用。
你的目标是实现可配置的执行开关/kill switch，并在关闭时拒绝任何执行请求。

# Critical Rules
- **配置外部化**: 开关必须来自环境变量/配置，并做校验。
- **结构化错误**: message 英文。
- **审计**: 命中 kill switch 必须审计。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 33）

# Execution Plan
1) 定义配置 schema。
2) 在执行入口拦截。

# Verification
- 单元测试：开关关闭 -> 拒绝。

# Output Requirement
- 输出代码与测试。
```

### Task 33.3 - 审计：写意图/拦截/审批预留字段

```markdown
# Context
你正在执行子任务：33.3 - 写意图审计。
你的目标是扩展审计事件覆盖写意图：intent、目标对象摘要、风险等级、拦截原因。

# Critical Rules
- **RBAC + 审计 + requestId**: 字段齐全。
- **脱敏**: 参数摘要脱敏。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 33）

# Execution Plan
1) 定义审计事件模型扩展。
2) 在拦截与 prepare 阶段写入审计。

# Verification
- 单元测试：审计记录包含 requestId/intent。

# Output Requirement
- 输出代码与测试。
```

### Task 33.4 - 冒烟：read_only_default_smoke_test.py

```markdown
# Context
你正在执行子任务：33.4 - Read-Only Default 冒烟。
你的目标是启动真实服务后，验证：写意图被拦截/路由到 prepare，且 SSE 事件与审计记录存在。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并英文报错。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 33）

# Execution Plan
1) 发起写意图请求。
2) 断言返回结构化错误或 prepare。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（写意图也要 evidence/审计摘要，按适用性）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
