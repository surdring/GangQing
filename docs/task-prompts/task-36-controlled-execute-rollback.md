# Task 36 - 受控执行与回滚（F4.4）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 36 组任务：受控执行与回滚（F4.4）：安全网关、幂等键、执行状态机、回滚点记录、熔断。
你的角色是 **技术负责人/架构师**。
你的目标是定义执行引擎边界、安全网关接口、幂等策略、回滚点模型与 kill switch 验收。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default**: 未审批前不得执行。
- **写操作链路（硬约束）**: 草案 -> 审批/多签 -> 受控执行 -> 回滚点 -> 审计。
- **Schema 单一事实源**: 前端执行 UI I/O/配置用 Zod；后端执行 I/O/审计用 Pydantic。
- **RBAC + 审计 + requestId**。
- **结构化错误**: message 英文。
- **配置外部化**: 网关地址、超时、重试、熔断阈值配置化。
- **真实集成测试（No Skip）**。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F4.4）
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.3）
- tasks: `docs/tasks.md`（Task 36）

# Execution Plan
1) Task 36.1 - 执行状态机与幂等键
2) Task 36.2 - 安全网关与 kill switch
3) Task 36.3 - 回滚点记录与审计
4) Task 36.4 - 冒烟：action_execute_and_rollback_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/action_execute_and_rollback_smoke_test.py`

# Output Requirement
输出规划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 36.1 - 后端：执行状态机（持久化/可恢复）+ 幂等

```markdown
# Context
你正在执行子任务：36.1 - 执行状态机与幂等。
你的目标是实现执行记录持久化、可恢复状态机与幂等键，防止重复执行。

# Critical Rules
- **写操作链路**: 仅在审批通过后允许执行。
- **结构化错误**: message 英文。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 36）

# Execution Plan
1) 定义执行记录模型。
2) 实现幂等检查。

# Verification
- 单元：重复请求不重复执行。

# Output Requirement
- 输出代码与测试。
```

### Task 36.2 - 安全网关 + kill switch（配置化）

```markdown
# Context
你正在执行子任务：36.2 - 安全网关与熔断。
你的目标是实现安全网关调用、熔断与 kill switch。

# Critical Rules
- **配置外部化**。
- **RBAC + 审计**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 36）

# Execution Plan
1) 定义网关调用接口。
2) 实现熔断与开关。

# Verification
- 单元：kill switch -> 拒绝。

# Output Requirement
- 输出代码与测试。
```

### Task 36.3 - 回滚点记录与全审计

```markdown
# Context
你正在执行子任务：36.3 - 回滚点与审计。
你的目标是记录每次执行的回滚点，并把执行过程全审计。

# Critical Rules
- **审计**。
- **Evidence-First**: 执行与回滚也要可追溯（来源、变更摘要、影响评估）。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 36）

# Execution Plan
1) 定义回滚点模型。
2) 写入审计。

# Verification
- 单元：回滚点存在。

# Output Requirement
- 输出代码与测试。
```

### Task 36.4 - 冒烟：执行 + 回滚

```markdown
# Context
你正在执行子任务：36.4 - 执行与回滚冒烟。
你的目标是验证真实链路：审批通过->执行->回滚（或模拟回滚）。

# Critical Rules
- **真实集成测试（No Skip）**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 36）

# Execution Plan
1) 准备审批通过的草案。
2) 调用 execute 并断言状态。
3) 调用 rollback 并断言。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
