# Task 39 - 数据基础设施演进：时序数据接入与冷热分层（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 39 组任务：数据基础设施演进：工业数据湖/时序数据接入与冷热分层（为 L3/L4 提供支撑）。
你的角色是 **技术负责人/架构师**。
你的目标是定义时序数据存储与查询策略、权限域与血缘、以及与事件模型对齐的证据链表达。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源**。
- **Evidence-First**: 时序数据查询必须可追溯（来源、时间范围、对齐规则、质量）。
- **RBAC + 审计 + requestId**。
- **结构化错误**: message 英文。
- **配置外部化**: 时序服务地址/超时/重试配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实时序服务；缺配置必须失败。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#40-46）
- TDD: `docs/技术设计文档-最佳实践版.md`（#14.3）
- tasks: `docs/tasks.md`（Task 39）

# Execution Plan
1) Task 39.1 - 接入：时序数据连接器（只读）与查询模板
2) Task 39.2 - 冷热分层策略与血缘记录（lineage_version）
3) Task 39.3 - 冒烟：timeseries_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/timeseries_smoke_test.py`

# Output Requirement
输出规划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 39.1 - 时序数据连接器：参数校验/超时/脱敏

```markdown
# Context
你正在执行子任务：39.1 - 时序连接器。
你的目标是实现只读时序查询连接器，支持参数校验、超时、脱敏与 evidence。

# Critical Rules
- **Read-Only Default**。
- **Schema 单一事实源**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 39）

# Execution Plan
1) 定义参数模型。
2) 查询模板化。

# Verification
- 单元：超时映射。

# Output Requirement
- 输出代码与测试。
```

### Task 39.2 - 血缘与权限域：time_range + lineage_version

```markdown
# Context
你正在执行子任务：39.2 - 血缘与权限。
你的目标是记录时序数据来源与血缘版本，并在 evidence 中输出。

# Critical Rules
- **Evidence-First**。
- **RBAC**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 39）

# Execution Plan
1) 定义 lineage 记录。
2) 输出 evidence。

# Verification
- 单元：字段存在。

# Output Requirement
- 输出代码与测试。
```

### Task 39.3 - 冒烟：timeseries_smoke_test.py

```markdown
# Context
你正在执行子任务：39.3 - 时序冒烟。
你的目标是连接真实时序服务跑通查询并断言 evidence。

# Critical Rules
- **真实集成测试（No Skip）**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 39）

# Execution Plan
1) 探活时序服务。
2) 发起查询。

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
