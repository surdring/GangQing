### Task 1 - 建立项目级对外契约基线（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 1 号任务：建立项目级对外契约基线：SSE 事件模型 + 统一错误模型 + Evidence schema（权威单一事实源）。
你的角色是 **技术负责人/架构师**。
你的目标是制定该任务的详细执行计划与约束口径，确保后续子任务能以“契约先行”的方式落地，并能被单元测试与冒烟测试验证。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 本阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 只输出规划、契约形态、文件修改范围、验证策略与风险控制。
- **Schema 单一事实源**:
  - 前端对外 I/O、SSE 事件、配置：**Zod**。
  - 后端对外 I/O、工具参数、Evidence、审计事件：**Pydantic**。
- **Evidence-First**: 数值结论与关键建议必须可追溯（数据源、时间范围、口径版本/`lineage_version`、工具调用、数据质量）。不可验证必须降级为“仅展示数据与来源/不确定项”。
- **Read-Only Default**: 未显式授权与审批前不得执行写操作；写操作仅允许“草案 -> 审批/多签 -> 受控执行 -> 回滚点 -> 审计”。
- **RBAC + 审计 + requestId 贯穿**: 所有接口/工具必须权限检查并记录审计；`requestId` 必须贯穿 HTTP 入站 -> Agent 编排 -> 工具调用 -> 对外响应。
- **结构化错误**: 对外错误必须包含 `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **流式输出**: 长耗时场景优先 SSE；事件中的错误也必须是结构化错误模型。
- **配置外部化**: URL/端口/超时/重试/API Key 禁止硬编码；必须通过统一配置加载并校验。
- **真实集成测试（No Skip）**:
  - 测试必须连接真实服务；配置缺失或服务不可用必须失败并给出英文错误信息。
  - 禁止用 mock/stub 替代外部服务连接层（单元测试允许依赖注入 fake，但必须保留真实错误语义）。

# References
- PRD: docs/requirements.md
- TDD: docs/design.md
- tasks: docs/tasks.md（任务 1）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml
- api docs: docs/api/semantic-api.md
- api docs: docs/api/data-api.md

# Execution Plan
1) Task 1.1（收敛 SSE 事件模型）
- Goal: 统一 SSE 事件类型、字段、序列化规则、错误事件与结束事件。
- Deliverables: 更新 `docs/contracts/api-and-events-draft.md` 中 SSE 事件章节；更新 `docs/api/openapi.yaml` 的 SSE 说明。

2) Task 1.2（统一错误模型与错误码枚举）
- Goal: 将 REST 与 SSE 的错误形态收敛为同一 `ErrorResponse/AppError`；确保 `message` 英文且可检索。
- Deliverables: 更新 `docs/contracts/api-and-events-draft.md` 错误模型与错误码；在 `docs/api/*.md` 引用并对齐。

3) Task 1.3（Evidence schema 最小集合与约束）
- Goal: 明确 Evidence 字段、必填项、可选项、降级语义（`validation` / `confidence` / `dataQualityScore`）。
- Deliverables: 更新 `docs/contracts/api-and-events-draft.md` Evidence 章节；要求前后端展示与校验都以此为准。

4) Task 1.4（契约测试与验收口径）
- Goal: 明确单元测试与冒烟测试要断言的契约点；定义“契约漂移”的阻断策略。
- Deliverables: 在任务 1 的 Sub-task Prompts 中明确测试范围；确保 `pytest -q` 与 `backend/scripts/sse_smoke_test.py` 可作为验收依据。

# Verification
- 单元测试（必须可自动化）：
  - `pytest -q` 覆盖：错误模型序列化、SSE 事件 schema、Evidence 最小字段与降级语义。
- 冒烟测试（必须连真实服务）：
  - 启动后端后运行 `backend/scripts/sse_smoke_test.py`，验证 SSE 事件序列与结构化错误事件。

# Output Requirement
输出一份 Markdown 执行蓝图，覆盖：SSE 事件模型、统一错误模型、Evidence schema、对应的文件修改范围、以及单元/冒烟测试的验收口径。
禁止输出任何实现代码。
```

---

### Task 1.1 - 收敛 SSE 事件模型

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：1.1 - 收敛 SSE 事件模型。
你的角色是 **高级开发工程师**。
你的目标是把 SSE 事件模型作为对外契约的一部分补齐到权威文档，并确保后续实现与测试能以此为准。

# Critical Rules
- **Schema 单一事实源**:
  - 前端对外 I/O、SSE 事件、配置：Zod。
  - 后端对外 I/O、工具参数、Evidence、审计事件：Pydantic。
- **结构化错误**: SSE 的 `error` 事件 payload 必须包含 `code/message/requestId/retryable/details?` 且 `message` 必须英文。
- **RBAC + 审计 + requestId 贯穿**: SSE `meta` 或首事件必须包含 `requestId/sessionId`；错误与审计可按 `requestId` 关联。
- **真实集成测试（No Skip）**: `backend/scripts/sse_smoke_test.py` 需要连真实服务，失败不得跳过。

# References
- PRD: docs/requirements.md（R6.1/R6.2/R6.3）
- TDD: docs/design.md（3.5.x、6.4）
- tasks: docs/tasks.md（1.1）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# Execution Plan
1) 更新 `docs/contracts/api-and-events-draft.md`：
- 明确 SSE endpoint、事件类型最小集合（`meta/progress/tool.call/tool.result/message.delta/evidence.update/warning/error/final` 或与现有草案对齐）。
- 明确每个事件的通用字段（至少 `requestId`；适用时 `sessionId`/`timestamp`/`type`/`payload`）。

2) 更新 `docs/api/openapi.yaml`：
- 增补对话 SSE 端点说明与事件样例（仅契约描述，不引入实现细节）。

3) 补齐与前端渲染相关的契约点：
- 分段渲染要求（`message.delta`）、证据增量（`evidence.update`）、错误即时可见（`error`）。

# Verification
- **Unit**: `pytest -q` 需要包含对 SSE 事件 schema 的断言（至少字段存在性与错误 payload 结构）。
- **Smoke**: 启动服务后运行 `backend/scripts/sse_smoke_test.py`，断言事件序列与 `error` 可解析。

# Output Requirement
- 交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
  - 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
  - 关键片段：仅粘贴与 SSE 契约相关的最小必要片段（例如 envelope 字段表、`type` 枚举、`error/final` 事件约束、事件序列验收点）。
  - 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 1.2 - 统一错误模型与错误码枚举

```markdown
# Context
你正在执行子任务：1.2 - 统一错误模型与错误码枚举。
目标是让 REST 与 SSE 错误都使用同一个结构化模型，并能被前端稳定解析与日志检索。

# Critical Rules
- **结构化错误**: 对外错误必须包含 `code/message/details?/retryable/requestId`。
- **message 必须英文**。
- **Schema 单一事实源**: 后端 Pydantic / 前端 Zod；对外输出前必须通过 schema 断言。
- **RBAC + 审计 + requestId 贯穿**: 错误必须携带 `requestId` 并可与审计事件按 `requestId` 聚合。
- **真实集成测试（No Skip）**: 契约相关断言必须在真实服务冒烟中出现（例如触发一次 `AUTH_ERROR` 或 `FORBIDDEN`）。

# References
- PRD: docs/requirements.md（R6.3/R1.2/R11.1）
- TDD: docs/design.md（6.1/6.4）
- tasks: docs/tasks.md（1.2）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/semantic-api.md
- api docs: docs/api/data-api.md

# Execution Plan
1) 更新 `docs/contracts/api-and-events-draft.md`：
- 明确错误模型字段、错误码枚举最小集合与语义。
- 明确 REST 错误响应与 SSE `error` 事件 payload 完全同构。

2) 更新 `docs/api/*.md`：
- 在文档中引用统一错误模型；避免出现与 contracts 不一致的字段/命名。

# Verification
- **Unit**: `pytest -q` 断言错误模型序列化/反序列化一致。
- **Smoke**: `backend/scripts/sse_smoke_test.py` 或相关脚本中触发一次结构化错误，并能被解析。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与统一错误模型/错误码/REST+SSE 同构约束相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 1.3 - Evidence schema 最小集合与约束

```markdown
# Context
你正在执行子任务：1.3 - Evidence schema 最小集合与约束。
目标是定义 Evidence 的最小字段集合、可追溯语义与降级规则，并成为前后端实现的权威来源。

# Critical Rules
- **Evidence-First**: 数值结论必须关联 Evidence；缺证据必须降级并提示不确定。
- **Schema 单一事实源**: 后端 Evidence 用 Pydantic；前端展示/事件解析用 Zod。
- **结构化错误**: 与 Evidence 缺失相关的错误/降级必须使用结构化字段（例如 `EVIDENCE_MISSING`/`warning` 事件）。
- **RBAC + 脱敏**: Evidence 展示默认脱敏；脱敏策略必须可审计。

# References
- PRD: docs/requirements.md（R2.2/R6.2/R10.2/R14.4）
- TDD: docs/design.md（3.3/5.1）
- tasks: docs/tasks.md（1.3）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 更新 `docs/contracts/api-and-events-draft.md` Evidence 章节：
- 明确 Evidence 字段（`evidenceId/sourceSystem/sourceLocator/timeRange/toolCallId?/lineageVersion?/dataQualityScore?/confidence/validation/redactions?`）。
- 明确证据缺失/不一致/越界的 `validation` 语义与降级要求。

2) 明确与 SSE `evidence.update` 的对应关系：
- `evidence.update` 的 payload 必须能承载 Evidence 增量或引用。

# Verification
- **Unit**: `pytest -q` 断言 Evidence schema 的必填字段与降级语义。
- **Smoke**: `backend/scripts/sse_smoke_test.py` 验证至少出现一次 `evidence.update`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与 Evidence schema 最小字段集合、降级语义、以及与 SSE `evidence.update` 对应关系相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检，必须逐项标注）
- [x] 是否所有错误 `message` 都是英文？（本提示词中对错误 message 的要求已明确为英文）
- [x] 是否包含结构化错误模型字段？（`code/message/details?/retryable/requestId`）
- [x] 是否包含证据链要求与字段？（Evidence 最小字段与降级语义）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（已包含 Read-Only Default 规则）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（已包含）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？（已包含）
- [x] 是否包含真实集成测试且不可 skip 的要求？（已包含）
