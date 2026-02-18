# Task 20 - L3 事件模型与时序对齐（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 20 组任务：L3 事件模型与时序对齐：生产事件（开炉/停机/报警等）与 OT 时序数据锚点对齐策略。
你的角色是 **技术负责人/架构师**。
你的目标是定义事件模型、对齐规则（窗口/锚点）、对齐结果的 Evidence 表达方式与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 事件与对齐输出对外契约必须 Pydantic；前端展示用 Zod。
- **Evidence-First**: 分析必须显式声明对齐规则与时间窗口，并写入 evidence。
- **结构化错误**: message 英文。
- **RBAC + 审计 + requestId**: 事件与对齐结果访问要鉴权并审计。
- **配置外部化**: 对齐窗口、阈值、数据源连接配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实数据源（Postgres + OT 时序服务若已接入）；缺配置必须失败。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#45-46、#122）
- TDD: `docs/技术设计文档-最佳实践版.md`（#14.3）
- tasks: `docs/tasks.md`（Task 20）

# Execution Plan
1) Task 20.1 - 数据层：事件表与对齐规则存储
2) Task 20.2 - 对齐算法实现（锚点事件/窗口）与输出模型
3) Task 20.3 - Evidence：对齐规则与窗口声明
4) Task 20.4 - 冒烟：event_alignment_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/event_alignment_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 20.1 - 事件表与对齐规则：迁移/建表

```markdown
# Context
你正在执行子任务：20.1 - 事件表与对齐规则。
你的目标是建立生产事件表与对齐规则配置（窗口/锚点）。

# Critical Rules
- **真实集成测试（No Skip）**: 必须真实 Postgres。

# References
- tasks: `docs/tasks.md`（Task 20）

# Execution Plan
1) 定义事件字段（event_type、timestamp、equipment_id、severity）。
2) 定义对齐规则字段。

# Verification
- 冒烟查询可用。

# Output Requirement
- 输出迁移/SQL、测试。
```

### Task 20.2 - 对齐逻辑：输出对齐结果（Pydantic）

```markdown
# Context
你正在执行子任务：20.2 - 对齐逻辑。
你的目标是实现对齐计算，并输出结构化对齐结果。

# Critical Rules
- **Schema 单一事实源**: 输出模型 Pydantic。
- **结构化错误**: message 英文。

# References
- PRD: `docs/产品需求.md`（时间对齐风险）
- tasks: `docs/tasks.md`（Task 20）

# Execution Plan
1) 定义输入/输出模型。
2) 实现锚点/窗口对齐。

# Verification
- 单元测试：边界窗口、缺事件。

# Output Requirement
- 输出代码与测试。
```

### Task 20.3 - Evidence：对齐规则与时间窗口声明（不可省略）

```markdown
# Context
你正在执行子任务：20.3 - Evidence 对齐声明。
你的目标是确保任何分析输出都携带对齐规则与窗口信息，并写入 evidence。

# Critical Rules
- **Evidence-First**: 对齐规则必须可追溯。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#14.3）
- tasks: `docs/tasks.md`（Task 20）

# Execution Plan
1) 在 evidence 中加入 alignment_rule 字段或 uncertainties。
2) 缺声明则降级 warning。

# Verification
- 单元测试：缺对齐声明降级。

# Output Requirement
- 输出代码与测试。
```

### Task 20.4 - 冒烟：event_alignment_smoke_test.py

```markdown
# Context
你正在执行子任务：20.4 - 对齐冒烟。
你的目标是实现冒烟脚本验证真实链路：事件->对齐->evidence。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 20）

# Execution Plan
1) seed 事件并执行对齐。
2) 断言对齐结果与 evidence 字段。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（对齐规则/窗口）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
