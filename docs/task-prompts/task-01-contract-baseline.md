# Task 1 - 建立项目级对外契约基线（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 1 组任务：建立项目级对外契约基线：SSE 事件模型 + 统一错误模型 + Evidence schema（权威单一事实源）。
你的角色是 **技术负责人/架构师**。
你的目标是制定任务组 1 的详细执行计划，并定义技术规范、契约边界与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 在此阶段禁止输出任何具体函数实现或业务代码。
- **PLANNING ONLY**: 只输出“怎么做/分几步/改哪些文件/契约长什么样/如何验收”，不要写实现细节。
- **Schema 单一事实源**:
  - 前端：对外 I/O、SSE 事件、配置必须使用 **Zod** 作为单一事实源（schema -> type）。
  - 后端：对外 I/O、工具参数、Evidence、审计事件必须使用 **Pydantic** 作为单一事实源。
- **Evidence-First（证据链优先）**: 数值结论与关键建议必须可追溯：数据源、时间范围、口径版本（lineage_version/definition_uri）、工具调用轨迹、数据质量；不可验证必须降级为“仅展示数据与来源/不确定项”。
- **Read-Only Default**: 未显式授权与审批前不得执行任何写操作；写操作仅允许“草案 -> 审批/多签 -> 受控执行 -> 回滚点 -> 审计”。
- **RBAC + 审计 + requestId 贯穿**: 所有接口/工具必须做权限检查并记录审计；`requestId` 必须贯穿（HTTP 入站 -> Agent 编排 -> 工具调用 -> 对外响应）。
- **结构化错误（对外）**: 必须包含 `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **流式输出（SSE 优先）**: 长耗时场景优先 SSE；流内错误也必须是结构化可解析错误事件。
- **配置外部化**: URL/端口/超时/重试/API Key 不得硬编码；必须通过统一配置加载并校验。
- **真实集成测试（No Skip）**:
  - 测试必须连接真实服务；配置缺失或服务不可用必须失败并给出英文错误信息。
  - 禁止使用 mock/stub 替代外部服务连接层（单元测试允许依赖注入 fake，但必须保留真实错误语义）。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 1）
- contracts (authoritative): `docs/contracts/api-and-events-draft.md`
- api docs: `docs/api/openapi.yaml`

# Execution Plan
1) Task 1.1 - 定义 SSE 事件协议的权威 schema（后端 Pydantic / 前端 Zod 对齐）
- Goal: 明确事件类型、统一字段、payload 结构与兼容策略。
- Deliverables:
  - `docs/contracts/api-and-events-draft.md` 补齐/修订：事件类型枚举、每类事件 payload 字段、必填/可选字段、错误事件 schema。
  - 前端与后端 schema 的“单一事实源策略”说明：以文档契约为准，分别落地 Zod/Pydantic 并做一致性检查（在后续子任务实现）。

2) Task 1.2 - 定义统一错误模型（REST 响应 + SSE error 事件）
- Goal: 稳定错误码、英文 message、可解析 details，保证 `requestId` 贯穿。
- Key Decisions:
  - 错误码枚举来源与扩展规则（对齐 TDD 附录 B 建议）。
  - retryable 判定标准与上游错误映射策略。

3) Task 1.3 - 定义 Evidence schema（Claims/Citations/Lineage/ToolCalls/Uncertainty）
- Goal: 证据链字段标准化，绑定“数值不可幻觉”门禁。
- Deliverables:
  - `docs/contracts/api-and-events-draft.md` 中 Evidence 段落：字段说明、约束（time_range 必填等）、最小示例（禁止实现代码）。

4) Task 1.4 - OpenAPI 对齐与对话入口声明
- Goal: `docs/api/openapi.yaml` 声明对话入口（含 SSE）与错误响应模型引用。

# Verification
- Unit Tests (后续子任务落地): `pytest -q`
- Smoke Tests (后续子任务落地): 启动服务后运行 `backend/scripts/sse_smoke_test.py`
- Contract Review:
  - SSE 事件字段齐全：`requestId/sessionId/timestamp/type/payload`。
  - `error` 事件 payload 与 REST 错误响应字段一致。
  - Evidence 字段覆盖：数据源、时间范围、口径版本、工具轨迹、不确定项。

# Output Requirement
请输出一份详细的 Markdown 执行计划，包含上述所有章节。
再次强调：**不要写任何实现代码**。
```

## Sub-task Prompts

### Task 1.1 - 补齐对外契约文档：SSE 事件模型

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：1.1 - 补齐对外契约文档：SSE 事件模型。
你的角色是 **高级开发工程师**。
你的目标是把 SSE 事件模型作为权威契约补齐到文档中，并保证后续可由 Zod/Pydantic 落地一致实现。

# Critical Rules
- **Schema 单一事实源**: 前端对外 I/O/配置用 Zod；后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic。
- **结构化错误**: `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **流式输出（SSE）**: 事件必须可分段渲染；事件中错误也必须结构化可解析。
- **RBAC + 审计 + requestId 贯穿**: 事件与接口均必须显式包含 `requestId`。
- **真实集成测试（No Skip）**: 后续实现必须跑真实服务；本子任务若新增校验脚本，也必须在配置缺失时失败并输出英文错误。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`（#4.2）
- tasks: `docs/tasks.md`（Task 1）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) 定义统一 SSE 事件 envelope 字段与约束（必填/可选）。
2) 枚举事件类型：`progress`/`message.delta`/`tool.call`/`tool.result`/`evidence.update`/`warning`/`error`/`final`。
3) 为每类事件定义 payload schema（字段、类型、约束、脱敏要求）。
4) 明确兼容策略：新增字段向后兼容、事件类型扩展规则。

# Verification
- 文档自检：
  - 每个事件都定义了 `payload` 结构。
  - `error` 事件引用统一错误模型字段。
  - `evidence.update` 明确引用 Evidence schema。

# Output Requirement
- 只修改文档：更新 `docs/contracts/api-and-events-draft.md`。
- 不要写任何业务实现代码。
```

### Task 1.2 - 补齐统一错误模型与错误码枚举

```markdown
# Context
你正在执行子任务：1.2 - 补齐统一错误模型与错误码枚举。
你的目标是让 REST 与 SSE 错误共享同一结构化错误模型，并在契约文档中列出错误码与语义。

# Critical Rules
- **结构化错误**: 对外错误必须包含 `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **message 必须英文**: 所有错误 message 必须为英文字符串。
- **RBAC + 审计 + requestId 贯穿**: 错误里必须包含 `requestId`，便于审计与排障。
- **Schema 单一事实源**: 错误模型必须能被后端 Pydantic 与前端 Zod 直接落地。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#4.3、附录 B）
- tasks: `docs/tasks.md`（Task 1）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) 在契约文档中定义 Error schema（字段定义、示例、脱敏原则）。
2) 整理错误码枚举（至少包含 TDD 建议项），并为每个 code 写清楚触发条件与 retryable 预期。
3) 标注错误与 SSE 事件的映射规则（`error` 事件 payload）。

# Verification
- 文档中存在完整错误码表。
- 每条错误码都有英文 message 示例与 details 约束。

# Output Requirement
- 只修改 `docs/contracts/api-and-events-draft.md`。
```

### Task 1.3 - 补齐 Evidence schema 与“数值不可幻觉”约束

```markdown
# Context
你正在执行子任务：1.3 - 补齐 Evidence schema 与门禁约束。
你的目标是把 Evidence 作为对外契约的一部分，确保前端 Context Panel 与后端输出一致可追溯。

# Critical Rules
- **Evidence-First**: 数值结论必须可追溯（数据源/时间范围/口径版本/工具调用/数据质量）。
- **不可验证降级**: 不满足绑定规则必须输出 `warning` 并在最终回答中表达不确定项。
- **Schema 单一事实源**: Evidence 字段必须能被 Pydantic/Zod 落地。

# References
- PRD: `docs/产品需求.md`（F1.3）
- TDD: `docs/技术设计文档-最佳实践版.md`（#5）
- tasks: `docs/tasks.md`（Task 1）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) 定义 Evidence 顶层结构与最小字段集。
2) 定义 Claims/Citations/Lineage/ToolCalls/Uncertainty 子结构字段。
3) 写清楚约束：time_range 必填、lineage_version 引用规则、脱敏策略、数据质量字段。

# Verification
- 文档中 Evidence 字段齐全且约束明确。

# Output Requirement
- 只修改 `docs/contracts/api-and-events-draft.md`。
```

### Task 1.4 - 对齐 OpenAPI：对话入口与错误响应声明

```markdown
# Context
你正在执行子任务：1.4 - 对齐 OpenAPI。
你的目标是在 `docs/api/openapi.yaml` 中声明对话入口与错误响应模型，确保契约可被工具/前端消费。

# Critical Rules
- **Schema 单一事实源**: OpenAPI 必须引用权威契约字段（errors/evidence/sse events）。
- **结构化错误**: 必须声明统一错误响应字段。
- **RBAC + requestId**: 必须声明请求/响应携带 `requestId`（header 或 body，按现有约定）。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#4）
- tasks: `docs/tasks.md`（Task 1）
- contracts: `docs/contracts/api-and-events-draft.md`
- api docs: `docs/api/openapi.yaml`

# Execution Plan
1) 定位对话入口定义位置，补齐请求/响应与错误响应 schema。
2) 明确 SSE 输出：若 OpenAPI 无法原生描述 SSE 事件流，至少在描述与 schema 组件中提供事件结构引用。

# Verification
- OpenAPI 校验通过（语法与引用）。

# Output Requirement
- 修改 `docs/api/openapi.yaml`。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？（在错误模型约束中明确要求英文）
- [x] 是否包含结构化错误模型字段？（`code/message/details?/retryable/requestId`）
- [x] 是否包含证据链要求与字段？（Claims/Citations/Lineage/ToolCalls/Uncertainty）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（作为硬约束写入，尽管本任务偏契约）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
