# Task 10 - 安全基座：RBAC + 脱敏 + 输出过滤（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 10 组任务：安全基座：RBAC（角色→工具→数据域→字段）+ 字段级脱敏策略 + 输出过滤。
你的角色是 **技术负责人/架构师**。
你的目标是定义权限模型、字段/数据域策略、注入防护与输出过滤基线，并明确审计与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端对外 I/O/配置 Zod；后端对外 I/O/工具参数/Evidence/审计事件 Pydantic。
- **RBAC + 审计 + requestId 贯穿**: 所有接口与工具必须权限检查并审计，贯穿 requestId。
- **数据脱敏（强制）**: 敏感字段按角色脱敏；默认最小权限。
- **输出过滤**: 防止敏感信息与系统指令泄露特征；防注入。
- **结构化错误**: 越权必须返回结构化错误（message 英文）。
- **真实集成测试（No Skip）**: 冒烟测试必须跑真实服务与真实 DB。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#97-104）
- TDD: `docs/技术设计文档-最佳实践版.md`（#3.1、#10）
- tasks: `docs/tasks.md`（Task 10）

# Execution Plan
1) Task 10.1 - 权限模型：角色->工具->数据域->字段
2) Task 10.2 - 字段级脱敏策略（后端输出 + Evidence 展示默认脱敏）
3) Task 10.3 - 防注入与输出过滤（输入分区、工具参数校验、输出过滤）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/rbac_and_masking_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 10.1 - RBAC 中间件与权限模型（工具白名单）

```markdown
# Context
你正在执行子任务：10.1 - RBAC 中间件与权限模型。
你的目标是实现角色与权限点，并在 API 与工具调用入口统一拦截。

# Critical Rules
- **RBAC + 审计**: 越权必须失败并记录审计。
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#3.1、#10.2）
- tasks: `docs/tasks.md`（Task 10）

# Execution Plan
1) 定义角色枚举与权限映射。
2) 在路由与工具调用层做拦截。

# Verification
- 单元：越权拒绝 + 审计落库。

# Output Requirement
- 输出代码与测试。
```

### Task 10.2 - 字段级脱敏与 Evidence 默认脱敏展示策略

```markdown
# Context
你正在执行子任务：10.2 - 字段级脱敏。
你的目标是对敏感字段进行脱敏/剔除，并确保 Evidence 与 tool.result 不泄露敏感字段。

# Critical Rules
- **数据脱敏**: 默认脱敏；按角色解锁。
- **Evidence-First**: filters 等字段只能输出脱敏摘要。

# References
- PRD: `docs/产品需求.md`（数据泄露风险）
- TDD: `docs/技术设计文档-最佳实践版.md`（#10.3）
- tasks: `docs/tasks.md`（Task 10）

# Execution Plan
1) 定义脱敏策略配置（按字段/角色）。
2) 在工具输出与 SSE 事件输出前执行过滤。

# Verification
- 单元：不同角色输出差异；敏感字段不出现。

# Output Requirement
- 输出代码与测试。
```

### Task 10.3 - 防注入：输入分区、工具参数校验、输出过滤

```markdown
# Context
你正在执行子任务：10.3 - 防注入与输出过滤。
你的目标是实现输入分区策略与输出过滤器，降低提示词注入与间接注入风险。

# Critical Rules
- **安全分区**: 系统指令/用户输入/工具结果/外部内容逻辑隔离。
- **工具参数校验**: 服务端 Pydantic 校验。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#10.1、#10.2）
- tasks: `docs/tasks.md`（Task 10）

# Execution Plan
1) 定义输入结构分区与清洗规则。
2) 定义输出过滤规则（敏感信息、系统提示词泄露特征）。

# Verification
- 冒烟：`backend/scripts/rbac_and_masking_smoke_test.py` 覆盖越权与过滤路径。

# Output Requirement
- 输出代码与测试。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（Evidence 默认脱敏）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
