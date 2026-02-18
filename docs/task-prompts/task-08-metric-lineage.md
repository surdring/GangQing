# Task 8 - 建设指标口径仓库（Metric Lineage）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 8 组任务：建设指标口径仓库（Metric Lineage）：版本化、责任人、变更记录、definition_uri。
你的角色是 **技术负责人/架构师**。
你的目标是定义指标口径的数据模型、版本策略、查询 API 形态，以及回答中强制引用 lineage_version 的规则。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 指标口径对外 I/O 必须 Pydantic；前端展示/配置必须 Zod。
- **Evidence-First**: 回答中涉及指标必须引用 `lineage_version` 或 `definition_uri`，并能追溯数据源与时间范围。
- **RBAC + 审计 + requestId**: 口径查询也要做权限检查并审计。
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。
- **真实集成测试（No Skip）**: 冒烟测试连接真实 Postgres 与真实服务。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#43-47、#121）
- TDD: `docs/技术设计文档-最佳实践版.md`（#5.2）
- tasks: `docs/tasks.md`（Task 8）

# Execution Plan
1) Task 8.1 - 数据层：metric_lineage 表与版本化字段
- Deliverables: 指标名、版本、公式/定义 URI、责任人、变更记录。

2) Task 8.2 - API：查询指标定义与版本
- Deliverables: REST endpoint（或工具接口）返回结构化口径对象。

3) Task 8.3 - 编排层规则：回答强制引用 lineage_version
- Deliverables: 若缺口径信息，降级为不确定项并输出 warning。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/metric_lineage_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 8.1 - 数据层：metric_lineage 版本化模型与迁移

```markdown
# Context
你正在执行子任务：8.1 - metric_lineage 表。
你的目标是建立口径仓库表结构，支持版本化与变更记录。

# Critical Rules
- **Evidence-First**: 口径记录必须能被 Evidence 引用（lineage_version/definition_uri）。
- **真实集成测试（No Skip）**: 迁移必须跑真实 Postgres。

# References
- PRD: `docs/产品需求.md`（#46）
- TDD: `docs/技术设计文档-最佳实践版.md`（#8.3、#5.2）
- tasks: `docs/tasks.md`（Task 8）

# Execution Plan
1) 定义表字段：metric_name、lineage_version、definition_uri/formula_id、owner、change_log、created_at。
2) 增加唯一约束与查询索引。

# Verification
- 冒烟脚本可查询到某个指标的最新版本。

# Output Requirement
- 输出迁移/SQL、配置与测试。
```

### Task 8.2 - API/工具：查询指标口径定义与版本

```markdown
# Context
你正在执行子任务：8.2 - 查询指标口径 API。
你的目标是提供查询接口返回结构化口径对象，并确保 RBAC 与审计。

# Critical Rules
- **Schema 单一事实源**: 对外响应必须 Pydantic。
- **结构化错误**: 错误 message 英文。
- **RBAC + 审计**: 访问必须记录审计。

# References
- tasks: `docs/tasks.md`（Task 8）

# Execution Plan
1) 定义 response Pydantic 模型。
2) 实现查询与权限过滤。
3) 写入审计记录（requestId 关联）。

# Verification
- 单元测试：存在/不存在、越权。

# Output Requirement
- 输出代码与测试。
```

### Task 8.3 - 编排层：回答强制引用 lineage_version（缺失则降级）

```markdown
# Context
你正在执行子任务：8.3 - lineage 引用规则。
你的目标是让编排层在生成答案时强制附带 lineage_version；缺失时输出 warning 并降级。

# Critical Rules
- **Evidence-First**: 指标结论必须绑定口径版本。
- **不可验证降级**: 口径缺失不得输出确定性指标结论。

# References
- PRD: `docs/产品需求.md`（口径不一致风险）
- TDD: `docs/技术设计文档-最佳实践版.md`（#5.2）
- tasks: `docs/tasks.md`（Task 8）

# Execution Plan
1) 在 answer assembly 阶段检查 lineage_version。
2) 缺失：输出 warning 并提示用户补充/选择口径版本。

# Verification
- 单元测试：有口径/缺口径两条路径。

# Output Requirement
- 输出代码与测试。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（lineage_version/definition_uri）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
