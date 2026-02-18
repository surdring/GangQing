# Task 16 - 异常主动推送（F1.2 / ALERT 意图）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 16 组任务：异常主动推送（F1.2 / ALERT 意图）：阈值/规则引擎 + 通知通道 + 审计。
你的角色是 **技术负责人/架构师**。
你的目标是定义预警规则引擎的边界、通知通道（Web/SSE）、证据链与审计要求、以及验收方案。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端通知事件/配置 Zod；后端规则/事件/审计 Pydantic。
- **Evidence-First**: 预警必须附带证据链（触发数据源、时间窗口、阈值口径版本、工具调用）。
- **RBAC + 审计 + requestId**: 推送与订阅必须鉴权并审计。
- **结构化错误**: 推送失败/规则执行失败必须结构化（message 英文）。
- **流式输出**: 优先 SSE 输出 alert 事件或通过通知中心拉取。
- **配置外部化**: 阈值/规则配置不得硬编码；需校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实后端与真实数据源（Postgres）。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F1.2）
- TDD: `docs/技术设计文档-最佳实践版.md`（#6、#11）
- tasks: `docs/tasks.md`（Task 16）

# Execution Plan
1) Task 16.1 - 后端：预警规则模型与执行器（阈值/窗口）
2) Task 16.2 - 通知通道：Web 通知中心/SSE 推送
3) Task 16.3 - 前端：通知中心 UI 与一键打开证据链
4) Task 16.4 - 冒烟：alert_push_smoke_test（后端+前端）

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/alert_push_smoke_test.py && node web/scripts/alert_ui_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 16.1 - 后端：预警规则引擎（Pydantic 配置 + Evidence）

```markdown
# Context
你正在执行子任务：16.1 - 预警规则引擎。
你的目标是实现规则模型（阈值/窗口/适用范围）与执行器，并输出可追溯 Evidence。

# Critical Rules
- **配置外部化**: 规则配置来源必须外部化并校验。
- **Evidence-First**: 必须输出触发证据（数据源、时间窗口、阈值版本）。

# References
- PRD: `docs/产品需求.md`（F1.2）
- tasks: `docs/tasks.md`（Task 16）

# Execution Plan
1) 定义规则模型与存储（表或配置）。
2) 执行器定期/按事件触发。

# Verification
- 单元测试：规则触发/不触发。

# Output Requirement
- 输出代码与测试。
```

### Task 16.2 - 通知通道：SSE/Web 通知与结构化错误

```markdown
# Context
你正在执行子任务：16.2 - 通知通道。
你的目标是实现推送与订阅机制（优先 SSE），并保证错误事件结构化。

# Critical Rules
- **流式输出**: SSE 事件必须契约化。
- **结构化错误**: `code/message(英文)/requestId/...`。

# References
- contracts: `docs/contracts/api-and-events-draft.md`
- tasks: `docs/tasks.md`（Task 16）

# Execution Plan
1) 定义 alert 事件类型与 payload。
2) 实现推送与失败重试策略（如适用）。

# Verification
- 冒烟：后端脚本能收到推送。

# Output Requirement
- 输出代码与测试。
```

### Task 16.3 - 前端：通知中心与证据链联动

```markdown
# Context
你正在执行子任务：16.3 - 前端通知中心。
你的目标是实现通知列表、未读状态、一键打开证据链。

# Critical Rules
- **Schema 单一事实源**: 通知事件 schema 用 Zod。
- **Evidence-First**: 每条通知必须可展开 evidence。

# References
- tasks: `docs/tasks.md`（Task 16）

# Execution Plan
1) Zod schema + UI 组件。
2) 与 Context Panel 联动打开。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 16.4 - 冒烟：alert_push_smoke_test.py / alert_ui_smoke_test.mjs

```markdown
# Context
你正在执行子任务：16.4 - 预警推送冒烟。
你的目标是实现后端与前端冒烟脚本，验证真实规则触发->推送->UI 展示->证据链打开。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置或服务不可用必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 16）

# Execution Plan
1) 后端冒烟：写入触发数据（若允许，仅用于测试数据表；否则通过 seed 数据触发），执行规则并断言推送。
2) 前端冒烟：连接后端并验证 UI 渲染。

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
