# Task 32 - GUI/LUI 融合：圈选提问与证据定位高亮（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 32 组任务：GUI/LUI 融合：圈选提问（图表/报表圈选）与屏显指引（从证据定位到 UI 高亮）。
你的角色是 **技术负责人/架构师**。
你的目标是定义圈选上下文的契约、后端绑定 evidence 的策略、以及前端高亮定位交互。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 圈选上下文对外 I/O 前端用 Zod，后端用 Pydantic。
- **Evidence-First**: 圈选上下文必须绑定到 evidence citations（图表来源、时间范围、口径版本）。
- **结构化错误**: message 英文。
- **RBAC + 审计 + requestId**: 圈选上下文提交与展示必须鉴权并审计。
- **真实集成测试（No Skip）**: 冒烟必须连接真实后端并验证圈选->提问->证据高亮。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#112-114）
- tasks: `docs/tasks.md`（Task 32）

# Execution Plan
1) Task 32.1 - 前端：圈选交互与上下文提交（Zod）
2) Task 32.2 - 后端：接收圈选上下文并绑定 evidence
3) Task 32.3 - 前端：证据定位高亮（从 citations 到 UI element）
4) Task 32.4 - 冒烟：selection_query_smoke_test.mjs

# Verification
- Unit: `npm test && pytest -q`
- Smoke: `node web/scripts/selection_query_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 32.1 - 前端：圈选上下文模型与提交

```markdown
# Context
你正在执行子任务：32.1 - 圈选交互。
你的目标是实现圈选交互（图表区间/点位）并提交结构化上下文。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: 上下文 schema 用 Zod。

# References
- tasks: `docs/tasks.md`（Task 32）

# Execution Plan
1) 定义 selection schema。
2) 实现 UI 圈选与提交。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 32.2 - 后端：圈选上下文接收（Pydantic）与 evidence 绑定

```markdown
# Context
你正在执行子任务：32.2 - 后端圈选上下文接收。
你的目标是接收圈选上下文并把它写入 evidence citations（来源图表/报表、时间范围）。

# Critical Rules
- **Schema 单一事实源**: 请求/响应 Pydantic。
- **Evidence-First**: 必须绑定 citations。

# References
- tasks: `docs/tasks.md`（Task 32）

# Execution Plan
1) 定义请求模型。
2) 绑定 evidence。

# Verification
- `pytest -q` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 32.3 - 前端：证据定位高亮（citations -> UI element）

```markdown
# Context
你正在执行子任务：32.3 - 证据定位高亮。
你的目标是根据 evidence citations 定位并高亮 UI 对应元素。

# Critical Rules
- **Evidence-First**: 只允许高亮可追溯引用。

# References
- tasks: `docs/tasks.md`（Task 32）

# Execution Plan
1) 定义 citation->UI anchor 的映射策略。
2) 实现高亮效果。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 32.4 - 冒烟：selection_query_smoke_test.mjs

```markdown
# Context
你正在执行子任务：32.4 - 圈选提问冒烟。
你的目标是验证构建产物中圈选->提问->高亮流程。

# Critical Rules
- **真实集成测试（No Skip）**: 缺后端配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 32）

# Execution Plan
1) 构建并运行脚本。
2) 断言关键 UI 元素。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（圈选上下文绑定 citations）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
