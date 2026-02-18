# Task 34 - 写操作草案（F4.2）：草案生成（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 34 组任务：写操作草案（F4.2）：排产/工单/领料/采购 的草案生成（可编辑、可解释、可审计）。
你的角色是 **技术负责人/架构师**。
你的目标是定义草案对象模型、编辑与差异对比能力、Evidence 强绑定与审计策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源**: 前端草案编辑 I/O/配置用 Zod；后端草案对象/工具参数/Evidence/审计用 Pydantic。
- **Read-Only Default**: 仅生成草案，不得执行写入外部系统。
- **Evidence-First**: 草案必须包含约束、目标函数、影响评估与 evidence；不可验证必须降级并提示不确定项。
- **RBAC + 审计 + requestId**: 草案创建/编辑/提交必须审计。
- **结构化错误**: message 英文。
- **真实集成测试（No Skip）**: 冒烟必须连接真实服务与真实数据库。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F4.2）
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.3）
- tasks: `docs/tasks.md`（Task 34）

# Execution Plan
1) Task 34.1 - 后端：草案模型与存储（版本/差异/状态）
2) Task 34.2 - 前端：草案编辑器与差异对比（甘特图或列表）
3) Task 34.3 - Evidence：约束/目标/影响评估字段
4) Task 34.4 - 冒烟：action_prepare_smoke_test.py + draft_ui_smoke_test.mjs

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/action_prepare_smoke_test.py && node web/scripts/draft_ui_smoke_test.mjs`

# Output Requirement
输出执行计划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 34.1 - 后端：草案对象模型与持久化（Pydantic）

```markdown
# Context
你正在执行子任务：34.1 - 草案对象模型与存储。
你的目标是实现草案数据模型、状态机（draft/submitted/approved/rejected）、版本与差异记录。

# Critical Rules
- **Read-Only Default**: 仅草案写入本系统存储，不得写入外部系统。
- **Schema 单一事实源**: 模型 Pydantic。
- **审计**: 创建/更新必须审计。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 34）

# Execution Plan
1) 定义草案表与模型。
2) 定义差异存储结构。

# Verification
- 单元测试：状态机与版本。

# Output Requirement
- 输出代码与测试。
```

### Task 34.2 - 前端：草案编辑器与差异对比（Zod）

```markdown
# Context
你正在执行子任务：34.2 - 草案编辑器。
你的目标是实现草案可编辑 UI、差异对比与提交审批入口。

# Critical Rules
- **TypeScript Strict**。
- **Schema 单一事实源**: 前端草案 I/O 用 Zod。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 34）

# Execution Plan
1) 定义草案 schema。
2) 实现编辑与差异展示。

# Verification
- `npm test`。

# Output Requirement
- 输出代码与测试。
```

### Task 34.3 - Evidence：草案约束/目标函数/影响评估可追溯

```markdown
# Context
你正在执行子任务：34.3 - 草案 Evidence。
你的目标是把草案中的关键决策依据输出到 evidence（数据源、时间范围、口径版本、约束清单）。

# Critical Rules
- **Evidence-First**。
- **不可验证降级**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 34）

# Execution Plan
1) 定义 evidence 扩展字段。
2) 组装 citations。

# Verification
- 单元测试：缺证据降级。

# Output Requirement
- 输出代码与测试。
```

### Task 34.4 - 冒烟：草案生成与 UI 渲染

```markdown
# Context
你正在执行子任务：34.4 - 草案冒烟。
你的目标是验证真实链路：生成草案->可编辑->提交审批（仅提交，不执行）。

# Critical Rules
- **真实集成测试（No Skip）**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 34）

# Execution Plan
1) 后端冒烟脚本创建草案。
2) 前端冒烟脚本验证渲染与编辑。

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
