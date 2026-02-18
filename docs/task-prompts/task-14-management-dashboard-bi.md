# Task 14 - 管理驾驶舱：自然语言 BI 输出卡片（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 14 组任务：管理驾驶舱：自然语言 BI 输出卡片（瀑布图/趋势图）与指标对比能力（F1.1）。
你的角色是 **技术负责人/架构师**。
你的目标是定义 BI 卡片的结构化输出契约、前后端分工、Evidence/lineage 强绑定规则与验收方案。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端卡片数据/配置用 Zod；后端分析输出/证据链/审计用 Pydantic。
- **Evidence-First**: 卡片中的关键数值必须有 citations + time_range + lineage_version。
- **结构化错误**: 失败必须输出结构化错误（message 英文），SSE 中也同样。
- **真实集成测试（No Skip）**: 后端与前端冒烟必须连接真实服务与真实 DB。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F1.1、#195-205）
- TDD: `docs/技术设计文档-最佳实践版.md`（#5、#8、#4）
- tasks: `docs/tasks.md`（Task 14）

# Execution Plan
1) Task 14.1 - 后端：分析型查询模板与聚合口径（引用 lineage_version）
2) Task 14.2 - 前端：瀑布图/趋势图组件与卡片渲染
3) Task 14.3 - 契约：卡片 schema（Zod/Pydantic 对齐）与 SSE 输出

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/bi_query_smoke_test.py && node web/scripts/bi_ui_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 14.1 - 后端：BI 查询模板与结构化卡片输出（Pydantic）

```markdown
# Context
你正在执行子任务：14.1 - 后端 BI 查询。
你的目标是实现分析型查询模板与结构化卡片输出，并强制引用 lineage_version。

# Critical Rules
- **Schema 单一事实源**: 输出模型必须 Pydantic。
- **Evidence-First**: 卡片数值必须绑定 evidence。
- **Read-Only Default**: 查询只读。

# References
- PRD: `docs/产品需求.md`（F1.1）
- tasks: `docs/tasks.md`（Task 14）

# Execution Plan
1) 定义卡片输出模型（指标、维度、序列、图表类型）。
2) 实现查询模板与聚合。
3) 组装 Evidence。

# Verification
- 单元测试：口径引用存在；缺失降级 warning。
- 冒烟：`backend/scripts/bi_query_smoke_test.py`。

# Output Requirement
- 输出代码与测试。
```

### Task 14.2 - 前端：瀑布图/趋势图组件与卡片渲染（Zod）

```markdown
# Context
你正在执行子任务：14.2 - 前端 BI UI。
你的目标是实现 BI 卡片渲染与图表组件，并通过 Zod 校验后端卡片数据。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: 前端卡片数据 schema 必须 Zod。

# References
- tasks: `docs/tasks.md`（Task 14）

# Execution Plan
1) 定义 Zod 卡片 schema。
2) 实现瀑布图/趋势图组件。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 14.3 - 冒烟：bi_ui_smoke_test.mjs（真实后端）

```markdown
# Context
你正在执行子任务：14.3 - BI UI 冒烟。
你的目标是实现 `web/scripts/bi_ui_smoke_test.mjs`，连接真实后端获取卡片并断言 UI 可渲染。

# Critical Rules
- **真实集成测试（No Skip）**: 缺少后端配置或服务不可用必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 14）

# Execution Plan
1) 发起真实请求拿到卡片。
2) 验证卡片 schema 与 Evidence 引用存在。

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
