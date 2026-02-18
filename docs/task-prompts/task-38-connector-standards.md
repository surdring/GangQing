# Task 38 - 工具链扩展：ERP/MES/DCS/LIMS 连接器规范化接入（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 38 组任务：工具链扩展：ERP/MES/DCS/LIMS 连接器规范化接入（统一参数校验、超时重试、脱敏、审计、Evidence）。
你的角色是 **技术负责人/架构师**。
你的目标是定义连接器模板、能力矩阵、错误映射、Evidence 输出规范与观测指标。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源**: 后端工具参数与输出必须 Pydantic；前端 I/O/配置用 Zod。
- **Evidence-First**: 每个连接器返回必须 evidence 化（数据源/时间范围/工具轨迹/质量）。
- **Read-Only Default**: 默认只读；写连接器需走草案-审批-执行链路。
- **RBAC + 审计 + requestId**。
- **结构化错误**: message 英文。
- **配置外部化**: 连接器 base URL/超时/重试/鉴权配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实外部系统（或真实集成环境）；缺配置必须失败。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#34-35）
- TDD: `docs/技术设计文档-最佳实践版.md`（#7.1）
- tasks: `docs/tasks.md`（Task 38）

# Execution Plan
1) Task 38.1 - 连接器模板：参数校验/超时/重试/脱敏/审计
2) Task 38.2 - 能力矩阵与观测字段（耗时/失败率/重试统计）
3) Task 38.3 - 统一错误码映射（UPSTREAM_*）与 retryable
4) Task 38.4 - 冒烟：connectors_integration_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/connectors_integration_smoke_test.py`

# Output Requirement
输出规划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 38.1 - 连接器模板：Pydantic 参数校验 + 超时重试 + 脱敏 + 审计

```markdown
# Context
你正在执行子任务：38.1 - 连接器模板。
你的目标是实现可复用连接器基类/模板，统一参数校验、超时重试、脱敏与审计。

# Critical Rules
- **Schema 单一事实源**。
- **结构化错误**。
- **RBAC + 审计**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 38）

# Execution Plan
1) 定义基类接口。
2) 统一错误映射。

# Verification
- 单元：超时/重试/脱敏。

# Output Requirement
- 输出代码与测试。
```

### Task 38.2 - 观测：连接器耗时/失败率/重试统计

```markdown
# Context
你正在执行子任务：38.2 - 连接器观测。
你的目标是记录每次连接器调用的耗时、失败率与重试次数，并关联 requestId。

# Critical Rules
- **可观测性**。
- **脱敏**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 38）

# Execution Plan
1) 定义 metrics/span。
2) 打点。

# Verification
- 单元：字段存在。

# Output Requirement
- 输出代码与测试。
```

### Task 38.3 - UPSTREAM 错误映射：retryable 与 details

```markdown
# Context
你正在执行子任务：38.3 - 错误映射。
你的目标是把外部系统错误映射为 `UPSTREAM_*` 错误码，并明确 retryable。

# Critical Rules
- **结构化错误**: message 英文。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 38）

# Execution Plan
1) 定义错误码枚举。
2) 实现映射。

# Verification
- 单元：映射覆盖。

# Output Requirement
- 输出代码与测试。
```

### Task 38.4 - 冒烟：connectors_integration_smoke_test.py

```markdown
# Context
你正在执行子任务：38.4 - 连接器集成冒烟。
你的目标是连接真实外部系统（或真实集成环境）跑通一次查询并输出 evidence。

# Critical Rules
- **真实集成测试（No Skip）**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 38）

# Execution Plan
1) 探活外部系统。
2) 发起查询并断言 evidence。

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
