# Task 15 - 智能交接班（F1.4）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 15 组任务：智能交接班（F1.4）：异常事件/未闭环报警/参数变更审计/遗留待办 的自动汇总。
你的角色是 **技术负责人/架构师**。
你的目标是定义交接班聚合输出结构、证据链与审计的强绑定、以及前端聚合页信息架构。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端 I/O/配置 Zod；后端 I/O/Evidence/审计 Pydantic。
- **Evidence-First**: 汇总中的关键条目必须可追溯（来源系统、时间范围、工具调用）。
- **RBAC + 审计 + requestId**: 聚合查询与展示必须受权限控制并审计。
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。
- **真实集成测试（No Skip）**: 后端与前端冒烟必须连接真实服务。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F1.4）
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.2、#11）
- tasks: `docs/tasks.md`（Task 15）

# Execution Plan
1) Task 15.1 - 后端：交接班聚合器（事件+审计+工单+待办）输出 evidence
2) Task 15.2 - 前端：交接班聚合页与可追溯展开
3) Task 15.3 - 冒烟：shift_handover_smoke_test（后端+前端）

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/shift_handover_smoke_test.py && node web/scripts/shift_handover_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 15.1 - 后端：交接班聚合器（Pydantic 输出 + Evidence）

```markdown
# Context
你正在执行子任务：15.1 - 后端交接班聚合器。
你的目标是聚合异常事件/未闭环报警/参数变更审计/遗留待办，并输出结构化结果与 Evidence。

# Critical Rules
- **Evidence-First**: 每个聚合条目必须能追溯 citations/time_range/toolCalls。
- **RBAC**: 按角色过滤条目与字段。

# References
- PRD: `docs/产品需求.md`（F1.4）
- tasks: `docs/tasks.md`（Task 15）

# Execution Plan
1) 定义输出模型。
2) 聚合查询（只读）并组装 Evidence。

# Verification
- 冒烟：`backend/scripts/shift_handover_smoke_test.py`。

# Output Requirement
- 输出代码与测试。
```

### Task 15.2 - 前端：交接班聚合页与证据展开

```markdown
# Context
你正在执行子任务：15.2 - 前端交接班页。
你的目标是实现聚合页与条目展开（证据链、审计来源、时间范围）。

# Critical Rules
- **Schema 单一事实源**: 前端用 Zod 校验后端返回。
- **Evidence-First**: 缺证据要有降级提示。

# References
- tasks: `docs/tasks.md`（Task 15）

# Execution Plan
1) 定义 Zod schema。
2) 实现页面与交互。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 15.3 - 冒烟：shift_handover_smoke_test（真实后端）

```markdown
# Context
你正在执行子任务：15.3 - 交接班冒烟。
你的目标是实现后端与前端冒烟脚本，验证真实链路可用与证据可追溯。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 15）

# Execution Plan
1) 后端脚本：发起真实请求断言结构。
2) 前端脚本：构建后运行断言 UI 关键元素存在。

# Verification
- 两个冒烟脚本通过。

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
