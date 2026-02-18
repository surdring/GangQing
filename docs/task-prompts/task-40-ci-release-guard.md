# Task 40 - 生产级发布与回归门禁：CI + 版本化发布 + 回滚策略（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 40 组任务：生产级发布与回归门禁：CI 触发（契约/单元/冒烟/Golden Dataset）+ 版本化发布 + 回滚策略。
你的角色是 **技术负责人/架构师**。
你的目标是定义 CI 门禁流水线、契约一致性检查、版本一致性策略与回滚方案。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源**: 契约校验必须以 Zod/Pydantic 为单一事实源落地，并与 `docs/contracts/api-and-events-draft.md` 对齐。
- **Evidence-First**: 发布门禁需验证 evidence 字段不缺失（关键链路）。
- **Read-Only Default**: 任何写能力发布必须经过审批链策略验证与 kill switch。
- **RBAC + 审计 + requestId**: 回归必须覆盖越权/审计。
- **结构化错误**: message 英文。
- **真实集成测试（No Skip）**: CI 必须跑真实服务的冒烟与回归（按项目策略配置集成环境）；缺配置必须失败。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#37-39）
- TDD: `docs/技术设计文档-最佳实践版.md`（#13、#14）
- tasks: `docs/tasks.md`（Task 40）

# Execution Plan
1) Task 40.1 - CI：契约校验（docs/contracts + OpenAPI + schema）
2) Task 40.2 - CI：单元测试 + 冒烟测试（后端/前端）
3) Task 40.3 - CI：Golden Dataset 回归
4) Task 40.4 - 版本化发布与回滚策略

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/full_pipeline_smoke_test.py && node web/scripts/full_pipeline_ui_smoke_test.mjs`

# Output Requirement
输出规划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 40.1 - 契约门禁：docs/contracts 与 schema 一致性校验

```markdown
# Context
你正在执行子任务：40.1 - 契约一致性校验。
你的目标是把契约文档与实际 schema（Zod/Pydantic）绑定到 CI，防止契约漂移。

# Critical Rules
- **Schema 单一事实源**。
- **结构化错误**: 校验失败输出英文信息。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 40）

# Execution Plan
1) 定义契约校验命令。
2) 在 CI 中执行。

# Verification
- CI 失败时给出清晰英文错误。

# Output Requirement
- 输出 CI 配置与校验脚本。
```

### Task 40.2 - CI：单元 + 冒烟（真实服务）

```markdown
# Context
你正在执行子任务：40.2 - 测试门禁。
你的目标是在 CI 中跑单元测试与真实服务冒烟测试，覆盖成功与失败链路。

# Critical Rules
- **真实集成测试（No Skip）**。
- **结构化错误**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 40）

# Execution Plan
1) 后端：pytest + 冒烟脚本。
2) 前端：npm test + build + 冒烟脚本。

# Verification
- CI 通过。

# Output Requirement
- 输出 CI 配置。
```

### Task 40.3 - CI：Golden Dataset 回归

```markdown
# Context
你正在执行子任务：40.3 - Golden Dataset 回归门禁。
你的目标是在 CI 中运行 Golden Dataset 回归并设置阈值门禁。

# Critical Rules
- **真实集成测试（No Skip）**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 40）

# Execution Plan
1) 运行回归脚本。
2) 解析报表并门禁。

# Verification
- 不达标 CI 必须失败。

# Output Requirement
- 输出 CI 配置与阈值配置。
```

### Task 40.4 - 版本化发布与回滚策略

```markdown
# Context
你正在执行子任务：40.4 - 版本与回滚。
你的目标是实现版本一致性校验（文档/契约/口径/数据集）与回滚策略。

# Critical Rules
- **RBAC + 审计**: 版本变更可追溯。
- **结构化错误**: message 英文。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 40）

# Execution Plan
1) 定义版本号策略。
2) 定义回滚流程。

# Verification
- 版本不一致 CI 失败。

# Output Requirement
- 输出文档/CI 配置变更。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
