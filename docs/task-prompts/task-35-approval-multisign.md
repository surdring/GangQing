# Task 35 - 审批与多签（F4.3）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 35 组任务：审批与多签（F4.3）：审批链配置、权限与职责分离、审批审计。
你的角色是 **技术负责人/架构师**。
你的目标是定义审批流程状态机、审批链配置模型、职责分离与审计策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源**: 前端审批 UI I/O/配置用 Zod；后端审批事件/审计用 Pydantic。
- **Read-Only Default**: 审批通过前不得执行任何写操作。
- **RBAC + 审计 + requestId**: 审批动作必须鉴权、审计、可追溯。
- **结构化错误**: message 英文。
- **配置外部化**: 审批链配置外部化并校验。
- **真实集成测试（No Skip）**。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F4.3）
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.3）
- tasks: `docs/tasks.md`（Task 35）

# Execution Plan
1) Task 35.1 - 后端：审批流程引擎（提交/同意/拒绝/追问）+ 多签
2) Task 35.2 - 前端：审批面板与审批链可视化
3) Task 35.3 - 审计：审批动作与职责分离字段
4) Task 35.4 - 冒烟：approval_flow_smoke_test.py + approval_ui_smoke_test.mjs

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/approval_flow_smoke_test.py && node web/scripts/approval_ui_smoke_test.mjs`

# Output Requirement
输出规划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 35.1 - 后端：审批流程状态机与多签（Pydantic）

```markdown
# Context
你正在执行子任务：35.1 - 审批流程引擎。
你的目标是实现最小流程：提交/同意/拒绝/追问，支持多角色多签，并保证职责分离。

# Critical Rules
- **Read-Only Default**: 仅记录审批，不执行。
- **RBAC + 审计**: 每个审批动作必须鉴权并审计。
- **结构化错误**: message 英文。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 35）

# Execution Plan
1) 定义审批对象与状态机。
2) 定义多签规则与冲突处理。

# Verification
- 单元：状态机转移、越权。

# Output Requirement
- 输出代码与测试。
```

### Task 35.2 - 前端：审批面板与审批链可视化（Zod）

```markdown
# Context
你正在执行子任务：35.2 - 审批 UI。
你的目标是实现审批待办列表、审批链展示与操作入口。

# Critical Rules
- **TypeScript Strict**。
- **Schema 单一事实源**: 前端 I/O 用 Zod。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 35）

# Execution Plan
1) 定义审批对象 schema。
2) 实现 UI 与错误展示（结构化错误）。

# Verification
- `npm test`。

# Output Requirement
- 输出代码与测试。
```

### Task 35.3 - 审计：审批动作与职责分离

```markdown
# Context
你正在执行子任务：35.3 - 审批审计。
你的目标是把审批动作写入审计日志，包含 action、actor、role、decision、requestId。

# Critical Rules
- **RBAC + 审计 + requestId**。
- **脱敏**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 35）

# Execution Plan
1) 扩展审计事件类型。
2) 写入落库。

# Verification
- 单元：字段存在。

# Output Requirement
- 输出代码与测试。
```

### Task 35.4 - 冒烟：审批流 + UI

```markdown
# Context
你正在执行子任务：35.4 - 审批冒烟。
你的目标是验证真实链路：草案提交->审批->状态更新->UI 展示。

# Critical Rules
- **真实集成测试（No Skip）**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 35）

# Execution Plan
1) 后端冒烟跑状态机。
2) 前端冒烟验证 UI。

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
