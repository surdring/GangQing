# Task 7 - 建立 Evidence 证据链引擎与“数值不可幻觉”门禁（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 7 组任务：建立 Evidence 证据链引擎（Claims/Citations/Lineage/ToolCalls/Uncertainty）与“数值不可幻觉”门禁。
你的角色是 **技术负责人/架构师**。
你的目标是规划 Evidence 引擎的核心规则、数据结构、与 SSE/前端 Context Panel 的联动方式，并定义验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Evidence-First**: 任何数值结论必须绑定 citation（含 time_range）与 lineage_version；不满足必须降级并输出 `warning`。
- **Schema 单一事实源**: Evidence 模型必须 Pydantic；前端展示数据结构必须 Zod。
- **结构化错误**: 对外错误结构化且 message 英文。
- **流式输出（SSE）**: Evidence 需要支持 `evidence.update` 增量事件。
- **RBAC + 审计 + requestId**: Evidence 生成过程与引用必须可审计且与 requestId 关联。
- **真实集成测试（No Skip）**: 冒烟测试必须跑真实服务与真实数据库。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F1.3）
- TDD: `docs/技术设计文档-最佳实践版.md`（#5、#5.3）
- tasks: `docs/tasks.md`（Task 7）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) Task 7.1 - Evidence 核心数据结构与校验
- Deliverables: Pydantic Evidence 模型（Claims/Citations/Lineage/ToolCalls/Uncertainty）。

2) Task 7.2 - “数值不可幻觉”门禁规则实现
- Deliverables: 校验器（claim 必须有 citations + time_range；指标必须有 lineage_version）。

3) Task 7.3 - SSE evidence.update 与前端可追问字段
- Deliverables: evidence.update 事件输出与字段脱敏策略。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/evidence_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 7.1 - Pydantic Evidence 模型与序列化校验

```markdown
# Context
你正在执行子任务：7.1 - Evidence 模型定义。
你的目标是实现 Evidence Pydantic 模型，并在对外输出前强制校验/序列化。

# Critical Rules
- **Schema 单一事实源**: Evidence 必须 Pydantic。
- **对外契约一致性**: 字段必须与 `docs/contracts/api-and-events-draft.md` 对齐。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#5.2）
- contracts: `docs/contracts/api-and-events-draft.md`
- tasks: `docs/tasks.md`（Task 7）

# Execution Plan
1) 定义 Claims/Citations/Lineage/ToolCalls/Uncertainty 模型。
2) 定义脱敏字段策略（例如 filters 仅保留非敏感摘要）。

# Verification
- 单元测试：序列化成功、缺字段失败返回结构化错误。

# Output Requirement
- 输出代码与测试。
```

### Task 7.2 - “数值不可幻觉”门禁：claim 必须绑定 citation/time_range/lineage

```markdown
# Context
你正在执行子任务：7.2 - 数值门禁规则。
你的目标是实现规则：任何数值 claim 必须绑定 citation（含 time_range）与 lineage_version（如指标计算）。不满足则降级。

# Critical Rules
- **Evidence-First**: 不可伪造 citation；不可验证必须降级输出 warning。
- **结构化错误/警告**: 降级原因必须可解析（SSE `warning` 事件或结构化字段）。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#5.3）
- tasks: `docs/tasks.md`（Task 7）

# Execution Plan
1) 定义校验器输入/输出。
2) 校验失败：
  - 对用户输出：删除确定性数值，改为不确定项描述。
  - 对 SSE：输出 `warning`。

# Verification
- 单元测试：缺 citation、缺 time_range、缺 lineage_version 的降级路径。

# Output Requirement
- 输出代码与测试。
```

### Task 7.3 - SSE：evidence.update 增量输出与前端可追问字段

```markdown
# Context
你正在执行子任务：7.3 - evidence.update 事件。
你的目标是把 Evidence 以增量方式通过 SSE 输出，并确保前端可展开追问字段（数据源/时间范围/口径版本/过滤条件摘要）。

# Critical Rules
- **流式输出（SSE）**: 事件 envelope 与 payload 必须与契约一致。
- **RBAC + 脱敏**: Evidence 展示默认脱敏。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#4.2、#5）
- contracts: `docs/contracts/api-and-events-draft.md`
- tasks: `docs/tasks.md`（Task 7）

# Execution Plan
1) 在编排过程中逐步输出 evidence.update。
2) 确保每次 update 都通过 Pydantic 校验。

# Verification
- 冒烟：`backend/scripts/evidence_smoke_test.py` 断言事件序列与 evidence 字段。

# Output Requirement
- 输出代码、契约测试与冒烟脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
