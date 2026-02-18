# Task 9 - 建立审计日志（不可抵赖方向）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 9 组任务：建立审计日志（不可抵赖方向）：查询/工具调用/响应摘要/错误 的全覆盖落库与检索。
你的角色是 **技术负责人/架构师**。
你的目标是定义审计事件 schema、落库与检索 API、脱敏策略与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出任何实现代码。
- **Schema 单一事实源**:
  - 前端对外 I/O/配置用 Zod。
  - 后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic。
- **RBAC + 审计 + requestId 贯穿**: 所有查询/工具调用/响应摘要/错误必须落审计；`requestId` 必须贯穿（HTTP -> SSE -> 工具 -> 审计）。
- **Evidence-First**: 审计事件需要关联 evidence 引用/摘要（不含敏感原文）。
- **结构化错误**: 对外错误必须包含 `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **配置外部化**: 数据库连接与审计开关必须配置化并校验。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实 Postgres；配置缺失/服务不可用必须失败并输出英文错误。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#100、F1.4）
- TDD: `docs/技术设计文档-最佳实践版.md`（#11）
- tasks: `docs/tasks.md`（Task 9）

# Execution Plan
1) Task 9.1 - 审计事件 Pydantic schema 与最小字段集
- `requestId/sessionId/userId/role/timestamp/intent/toolsUsed/dataScope/resultStatus/error?`。

2) Task 9.2 - 落库管线与脱敏策略
- 参数摘要脱敏；禁止写入敏感原文。

3) Task 9.3 - 审计查询 API（RBAC 限制）
- 按角色限制可检索范围。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/audit_log_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 9.1 - 定义审计事件模型（Pydantic）与落库表结构

```markdown
# Context
你正在执行子任务：9.1 - 审计事件模型与表结构。
你的目标是定义审计事件 Pydantic 模型与 Postgres 表结构，确保字段满足不可抵赖方向的最小集合。

# Critical Rules
- **Schema 单一事实源**: 审计事件必须 Pydantic。
- **RBAC + requestId**: 审计记录必须能按 requestId 追溯。
- **脱敏**: 参数摘要必须脱敏（禁止敏感字段直写）。
- **真实集成测试（No Skip）**: 必须在真实 Postgres 上建表/迁移。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#11.2）
- tasks: `docs/tasks.md`（Task 9）

# Execution Plan
1) 定义模型字段与约束（可选字段与索引策略）。
2) 建表并添加必要索引（requestId、timestamp）。

# Verification
- 冒烟：插入并可按 requestId 查询。

# Output Requirement
- 输出迁移/SQL、模型与测试。
```

### Task 9.2 - 审计写入管线：覆盖 query/tool_call/response/error

```markdown
# Context
你正在执行子任务：9.2 - 审计写入管线。
你的目标是把审计写入点接入到 HTTP 入站、工具调用、SSE 终态输出与错误处理路径。

# Critical Rules
- **RBAC + 审计**: 所有关键动作必须落审计。
- **结构化错误**: 错误审计必须保留 `code/message(英文)/requestId`。

# References
- tasks: `docs/tasks.md`（Task 9）

# Execution Plan
1) 定义审计事件类型枚举（query/tool_call/response/error）。
2) 在关键路径写入审计（参数脱敏、结果摘要）。

# Verification
- 单元：审计事件生成字段完整。
- 冒烟：走一次 SSE 对话链路，审计表有记录。

# Output Requirement
- 输出代码与测试。
```

### Task 9.3 - 审计查询 API（RBAC 限制）

```markdown
# Context
你正在执行子任务：9.3 - 审计查询 API。
你的目标是提供审计查询接口，并按 RBAC 限制查询范围。

# Critical Rules
- **RBAC**: 无权限必须返回结构化错误。
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。

# References
- PRD: `docs/产品需求.md`（审计与留痕）
- TDD: `docs/技术设计文档-最佳实践版.md`（#11）
- tasks: `docs/tasks.md`（Task 9）

# Execution Plan
1) 定义查询入参/出参 Pydantic 模型。
2) 实现过滤与分页。

# Verification
- 单元：越权失败、正常查询成功。
- 冒烟：`backend/scripts/audit_log_smoke_test.py`。

# Output Requirement
- 输出代码、OpenAPI 更新与测试。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（审计关联 evidence 摘要）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
