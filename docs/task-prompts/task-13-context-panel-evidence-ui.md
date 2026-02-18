# Task 13 - 前端 Context Panel：Evidence 可视化（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 13 组任务：前端 Context Panel：Evidence 可视化（Claims→Citations→Lineage→ToolCalls）与“证据缺失/降级态”表达。
你的角色是 **技术负责人/架构师**。
你的目标是规划 Evidence UI 信息架构、状态设计（缺失/不可验证/降级）、与 SSE evidence.update 的联动方式。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端 Evidence 展示数据必须 Zod；后端 Evidence 必须 Pydantic。
- **Evidence-First**: 只展示可追溯证据；禁止展示不可映射引用。
- **不可验证降级**: 必须有明确 UI 表达（证据缺失/不可验证/降级模式）。
- **结构化错误**: SSE error 事件必须可解析并展示 requestId。
- **真实集成测试（No Skip）**: 前端冒烟必须连接真实后端 SSE（或至少真实契约事件流）。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F1.3、#9.2.1）
- TDD: `docs/技术设计文档-最佳实践版.md`（#5）
- tasks: `docs/tasks.md`（Task 13）

# Execution Plan
1) Task 13.1 - Zod：Evidence UI 数据结构与渲染模型
2) Task 13.2 - ContextPanel.tsx：Claims/Citations/Lineage/ToolCalls 展示
3) Task 13.3 - 缺失/降级态 UI 与交互（提示与追问入口）
4) Task 13.4 - 冒烟：context_panel_smoke_test.mjs

# Verification
- Unit: `npm test`
- Smoke: `npm run build && node web/scripts/context_panel_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 13.1 - Zod：Evidence/UI schema（与后端契约对齐）

```markdown
# Context
你正在执行子任务：13.1 - Evidence UI schema。
你的目标是为 Context Panel 定义 Zod schema（claims/citations/lineage/toolCalls/uncertainties），并与后端 Pydantic Evidence 对齐。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: 前端用 Zod。

# References
- contracts: `docs/contracts/api-and-events-draft.md`
- tasks: `docs/tasks.md`（Task 13）

# Execution Plan
1) 定义 Zod schema 并导出类型。
2) 在 SSE evidence.update 解析处复用 schema。

# Verification
- 单元测试：schema 解析成功/失败路径。

# Output Requirement
- 输出代码与测试。
```

### Task 13.2 - 实现 ContextPanel：证据链可视化

```markdown
# Context
你正在执行子任务：13.2 - ContextPanel 可视化。
你的目标是修改 `web/components/ContextPanel.tsx` 展示证据链：引用胶囊、时间范围、口径版本、工具调用轨迹。

# Critical Rules
- **Evidence-First**: 只展示可追溯字段。
- **脱敏**: filters/参数摘要默认脱敏。

# References
- PRD: `docs/产品需求.md`（9.2.1）
- tasks: `docs/tasks.md`（Task 13）

# Execution Plan
1) UI 信息架构：Claims 列表 -> Citation 明细 -> Lineage/ToolCalls。
2) 交互：点击引用展开详情。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 13.3 - 证据缺失/不可验证/降级态表达

```markdown
# Context
你正在执行子任务：13.3 - 降级态 UI。
你的目标是实现明确的降级态与提示文案（UI 可中文），并支持用户追问“缺少什么证据/如何补齐”。

# Critical Rules
- **不可验证降级**: 必须显式呈现，不得伪装为确定性结论。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#5.3）
- tasks: `docs/tasks.md`（Task 13）

# Execution Plan
1) 定义缺失状态模型。
2) UI 显示：缺失原因、建议下一步。

# Verification
- 单元测试：渲染缺失状态。

# Output Requirement
- 输出代码与测试。
```

### Task 13.4 - 冒烟：context_panel_smoke_test.mjs

```markdown
# Context
你正在执行子任务：13.4 - Context Panel 冒烟。
你的目标是实现 `web/scripts/context_panel_smoke_test.mjs`，在构建产物上对 Evidence 渲染进行最小断言。

# Critical Rules
- **真实集成测试（No Skip）**: 若依赖后端数据，必须连接真实后端；缺配置必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 13）

# Execution Plan
1) 读取后端地址或测试数据来源配置。
2) 触发一次对话并断言 evidence 结构在 UI 可渲染。

# Verification
- `npm run build && node web/scripts/context_panel_smoke_test.mjs` 通过。

# Output Requirement
- 输出脚本与相关代码。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？（结构化错误字段）
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
