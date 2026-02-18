# Task 6 - 实现 L1 只读查询工具（Postgres）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 6 组任务：实现 L1 只读查询工具（Postgres）：模板化查询 + 字段白名单 + 参数校验 + 脱敏 + 审计。
你的角色是 **技术负责人/架构师**。
你的目标是定义 Postgres 工具的边界（只读/模板化）、RBAC 与脱敏策略、Evidence 输出要求与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Read-Only Default（工具层强制）**: 仅允许 `SELECT`；禁止模型自由拼接 SQL。
- **Schema 单一事实源**: 工具参数与输出（含 Evidence）必须 Pydantic。
- **Evidence-First**: 工具返回必须包含 Evidence Citation + Tool Call Trace；数值结论必须可追溯。
- **RBAC + 脱敏 + 审计**: 按角色限制字段/数据域；审计记录 query/tool_call/result/error/dataScope。
- **结构化错误**: 对外错误字段齐全且 message 英文。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实 Postgres。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F1.1、F1.3）
- TDD: `docs/技术设计文档-最佳实践版.md`（#7、#7.2、#11）
- tasks: `docs/tasks.md`（Task 6）

# Execution Plan
1) Task 6.1 - 工具参数 schema 与查询模板库
- Deliverables: 参数模型、模板枚举、字段白名单。

2) Task 6.2 - RBAC 与脱敏
- Decisions: 角色->字段/域策略；默认最小权限。

3) Task 6.3 - Evidence 输出与审计
- Deliverables: citation/time_range/filters(excluded)/extracted_at/tool trace。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/postgres_tool_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 6.1 - 工具参数 Pydantic schema + 查询模板化（禁止自由 SQL）

```markdown
# Context
你正在执行子任务：6.1 - 工具参数 schema + 查询模板化。
你的目标是定义工具参数模型与模板库，确保模型无法注入自由 SQL。

# Critical Rules
- **Schema 单一事实源**: 工具参数必须 Pydantic 校验。
- **Read-Only Default**: 只允许模板化 SELECT。
- **结构化错误**: 参数校验失败必须返回结构化错误（message 英文）。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#7.2）
- tasks: `docs/tasks.md`（Task 6）

# Execution Plan
1) 定义工具参数模型（时间范围、设备/产线等维度、指标列表）。
2) 定义模板枚举与模板->SQL 映射（服务端固定）。
3) 实现字段白名单机制。

# Verification
- 单元测试：参数校验、模板选择、越权字段被拒。

# Output Requirement
- 输出代码与测试。
```

### Task 6.2 - RBAC + 字段级脱敏 + 数据域限制

```markdown
# Context
你正在执行子任务：6.2 - RBAC + 脱敏。
你的目标是按角色限制可查询字段与数据域，并对敏感字段脱敏。

# Critical Rules
- **RBAC**: 越权必须失败并审计。
- **脱敏**: 默认脱敏，按权限可展开（后续前端配合）。

# References
- PRD: `docs/产品需求.md`（#97-104）
- TDD: `docs/技术设计文档-最佳实践版.md`（#10.3）
- tasks: `docs/tasks.md`（Task 6）

# Execution Plan
1) 定义角色模型与权限点。
2) 在工具执行前进行权限检查。
3) 输出过滤：敏感字段脱敏或移除。

# Verification
- 单元测试：不同角色访问差异；越权错误结构化。

# Output Requirement
- 输出代码与测试。
```

### Task 6.3 - 工具返回：Evidence Citation + Tool Call Trace + 审计落库

```markdown
# Context
你正在执行子任务：6.3 - Evidence 与审计。
你的目标是让工具返回结构包含摘要 + Evidence Citation + Tool Call Trace，并落审计记录。

# Critical Rules
- **Evidence-First**: citation 必须包含数据源、time_range、filters(脱敏)、lineage_version（如适用）。
- **审计**: 记录 requestId、query 摘要、tool_call 参数摘要、结果状态。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#5、#11）
- tasks: `docs/tasks.md`（Task 6）

# Execution Plan
1) 定义工具返回 Pydantic 模型。
2) 组装 Evidence 与 tool trace。
3) 写入审计表（若 Task 9 尚未完成，可先写最小审计落地接口/表结构，后续对齐）。

# Verification
- 冒烟：`backend/scripts/postgres_tool_smoke_test.py` 走通并验证 evidence 字段。

# Output Requirement
- 输出代码、测试与冒烟脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
