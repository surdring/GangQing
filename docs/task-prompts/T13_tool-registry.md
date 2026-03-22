### Task 13 - 编排层：工具链注册与 Function Calling（可控调用 + 可追溯证据）（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 13 号任务：编排层：工具链注册与 Function Calling（可控调用 + 可追溯证据）。
你的角色是 **技术负责人/架构师**。
你的目标是制定 Task 13 的详细执行计划，并定义技术规范与验收口径，覆盖：

- 工具注册机制（声明式注册/配置化启用）
- 可用工具集合门禁（角色 + 意图 + 数据域）
- SSE 事件输出（`tool.call` / `tool.result` / `error` / `final`）与序列约束
- 工具调用与 Evidence / 审计 / requestId 绑定

# Critical Rules
- **NO CODE IMPLEMENTATION**: 在此阶段禁止输出任何具体的函数实现或业务代码。
- **PLANNING ONLY**: 你的输出应聚焦于“怎么做、分几步、文件结构如何、接口长什么样、怎么验收”。
- **Technology Standards（强制）**:
  - 前端：对外 I/O、SSE 事件、配置使用 Zod 作为单一事实源（schema -> type）。
  - 后端：对外 I/O、工具参数、Evidence、审计事件使用 Pydantic 作为单一事实源。
  - 错误信息（`message`）必须为英文；对外错误必须结构化：`code` + `message` + `requestId` + `retryable` + `details?`。
  - **Evidence-First**: 数值结论/关键建议必须可追溯到证据链（数据源、时间范围、口径版本、工具调用、数据质量）。
  - **Read-Only Default**: 默认只读；任何写操作必须走“草案 -> 审批/多签 -> 受控执行 -> 回滚点 -> 审计”。
  - **RBAC & Audit**: 所有接口/工具必须做 RBAC 权限检查并记录审计事件，贯穿 `requestId`。
  - **Streaming**: 长耗时任务必须以 SSE 输出阶段进度与可解析的结构化错误事件。
- **工具白名单（强制）**: 可用工具集合必须由“角色 + 意图 + 数据域”决定，禁止模型自由调用任意工具。
- **契约一致性（强制）**:
  - `tool.call` / `tool.result` / `error` / `final` 事件字段必须与 `docs/contracts/api-and-events-draft.md` 对齐。
  - 工具输出必须做契约校验；不符合契约必须返回 `CONTRACT_VIOLATION` 并记录审计。
- **审计与脱敏（强制）**: 审计中记录 `toolName`、参数摘要（脱敏）、耗时、状态、`requestId`、`stepId`（如有）。

# References
- PRD: docs/requirements.md（R15.3）
- TDD: docs/design.md（2.5.3/3.5.1）
- 架构方案: docs/GangQing 自研 AI Copilot 核心组件技术方案(架构设计版).md
- tasks: docs/tasks.md（任务 13）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan (执行蓝图)

1) Tool Registry（Task 13.1）- 工具注册：配置化工具目录与元数据
- Goal:
  - 建立“工具注册表（registry）”作为编排层唯一可信来源，支持枚举工具、能力边界、参数 schema、超时/重试/脱敏策略等元信息。
- Key Decisions:
  - 注册方式：装饰器声明式注册（推荐）与配置化启用/禁用并存。
  - 元数据模型：Pydantic（后端）作为单一事实源；对外暴露（若有）需契约化。
  - 工具分类：只读工具优先；写操作工具在 L4 仅进入治理链路（不得直接执行）。
- Deliverables:
  - 工具元数据 Pydantic 模型（例如：工具名、描述、capabilities、参数模型、超时/重试、脱敏策略、是否只读等）。
  - 工具注册与发现机制（支持列出可用工具清单）。
  - 与审计、Evidence 绑定所需的最小字段定义（例如 `tool_call_id`、`evidence_refs`）。

2) Tool Call Streaming（Task 13.2）- SSE 事件：`tool.call` / `tool.result` + 审计 + Evidence
- Goal:
  - 在 SSE 流中输出工具调用生命周期事件，使前端可分段渲染，并可追溯到 Evidence 与审计记录。
- Dependencies:
  - 依赖 Task 13.1 的 `tool_call_id`/元数据；并确保工具元信息足以支撑脱敏摘要与 Evidence 引用。
- Key Decisions:
  - 事件序列：`tool.call` -> (`tool.result` | `error`) ->（不可恢复时）`final`。
  - 事件内容：args/result 仅允许摘要且必须脱敏；Evidence 以引用（IDs/locators）绑定。
  - sequence 单调递增，便于前端检测丢包/乱序。
- Deliverables:
  - SSE 事件 payload 与 contracts 对齐（尤其 `error` 与 ErrorResponse 同构）。
  - 工具调用耗时、状态、重试次数（如有）纳入审计与可观测。

3) Tool Gate（Task 13.3）- 门禁：allowed tools 计算与校验
- Goal:
  - 实现“可用工具集合”门禁：工具选择必须由 **角色 + 意图 + 数据域** 决定，服务端强制校验，禁止越权调用。
- Dependencies:
  - 依赖 Task 13.1 的工具元数据与注册表。
- Key Decisions:
  - 计算函数的输入：`RequestContext`（tenantId/projectId/requestId/user claims）+ intent + tool registry。
  - 决策输出：allowed tools 列表 + 拒绝原因（用于审计与可观测，但不泄露敏感策略细节）。
- Deliverables:
  - allowed tools 计算与校验逻辑（编排层与工具装饰器层均需可复用）。
  - 越权/跨域/不在白名单：统一映射为结构化错误（`FORBIDDEN` / `AUTH_ERROR` / `GUARDRAIL_BLOCKED`，以 contracts 为准）。
  - 审计事件字段：记录决策输入摘要与决策结果摘要（脱敏）。

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确新增/修改的目录树（注册表、工具装饰器/包装器、门禁策略、SSE 事件发射点）。
- [ ] **Environment Variables**: 明确工具启用/禁用、超时/重试、审计开关等配置项（必须外部化，不得硬编码）。
- [ ] **API/SSE Contracts**: 明确 `tool.call` / `tool.result` / `error` / `final` 的字段要求与约束，并声明以 `docs/contracts/api-and-events-draft.md` 为准。
- [ ] **Evidence Contract**: 明确 tool -> evidence 绑定字段（至少 evidence 引用、时间范围、来源定位信息），缺失时的降级策略。
- [ ] **Auth & RBAC**: 明确角色/权限点、拒绝策略（含跨域访问处理）与审计字段。
- [ ] **Error Model**: 错误码枚举与结构化错误响应/事件（英文 message）。
- [ ] **Observability & Audit**: `requestId` 贯穿方案、审计事件类型（tool.call/tool.result/error）与脱敏策略。

# Verification Plan (整体验收)
- Automated Tests（必须可自动化断言，且不可 skip）：
  - Unit: `pytest -q` 覆盖：
    - allowed tools 计算（角色/意图/数据域）与拒绝路径。
    - 工具参数 Pydantic 校验失败 -> `VALIDATION_ERROR` 映射。
    - `tool.call`/`tool.result`/`error`/`final` 事件序列与必填字段。
  - Smoke: `backend/scripts/tool_registry_smoke_test.py` 覆盖：
    - 启动真实服务后发起一次真实查询，观察 SSE 流包含 tool 事件与 evidence 引用。
    - 触发一次失败路径（例如权限不足/参数校验失败），观察结构化 `error` + `final`。

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 13.1 - 工具注册：配置化工具目录与元数据

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：13.1 - 工具注册：配置化工具目录与元数据。
你的角色是 **高级开发工程师**。
你的目标是编写代码，交付一个可被编排层消费的工具注册表，使系统能：

- 枚举工具清单（registry）
- 声明参数 schema（Pydantic）与能力边界（capabilities/只读属性）
- 为后续门禁、审计、Evidence、SSE tool 事件提供一致的元信息来源

# Critical Rules
- **Schema First**:
  - 工具参数必须用 Pydantic 模型校验。
  - 任何对外输出（API/SSE）必须与 `docs/contracts/api-and-events-draft.md` 对齐。
- **配置外部化**: 工具启用/禁用、超时、重试等必须通过配置（不得硬编码）。
- **RBAC & Audit**: 工具元信息必须包含权限边界所需字段；调用时必须记录审计（含参数摘要脱敏）。
- **Read-Only Default**: L1 阶段仅允许只读工具；写操作工具不得执行（最多产出草案/审批材料，L4 才允许）。
- **Structured Errors**: 所有对外错误 `message` 必须为英文，且必须结构化（`code/message/requestId/retryable/details?`）。

# References
- tasks: docs/tasks.md（13.1）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files
- backend/gangqing/tools/
- backend/gangqing/agent/
- backend/gangqing/api/
- backend/scripts/tool_registry_smoke_test.py（如需要补齐/增强覆盖）

# Execution Plan
1) 定义工具元数据模型（Pydantic）。
2) 实现注册与发现。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/tool_registry_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 13.2 - 工具调用事件输出：`tool.call`/`tool.result` + 结构化错误

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：13.2 - 工具调用事件输出：`tool.call`/`tool.result` + 结构化错误。
你的角色是 **高级开发工程师**。
你的目标是让前端可分段渲染工具阶段，并可追溯到 Evidence 与审计记录：

- 工具调用开始：发出 `tool.call`
- 工具调用结束：成功发出 `tool.result`；失败发出结构化 `error` 并按需跟随 `final`
- 事件 envelope 必须包含 `requestId/tenantId/projectId/sequence` 等强制字段（以 contracts 为准）

# Critical Rules
- **SSE**: 事件字段必须与 contracts 对齐。
- **错误事件结构化**: `error` payload 为 ErrorResponse。
- **Evidence-First**: `tool.result` 必须携带 evidence 引用（IDs/locators），不可伪造。
- **Redaction**: args/result 仅允许摘要且必须脱敏（禁止在 SSE 中输出敏感原始字段）。
- **Sequence**: `sequence` 必须单调递增；客户端可据此检测丢包/乱序。

# References
- PRD: docs/requirements.md（R6.1）
- tasks: docs/tasks.md（13.2）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files
- backend/gangqing/agent/
- backend/gangqing/api/
- backend/gangqing/tools/
- backend/scripts/tool_registry_smoke_test.py（如需要补齐/增强覆盖）

# Execution Plan
1) 在编排层工具调用包装器中发出 `tool.call`。
2) 成功时发出 `tool.result`（脱敏摘要 + evidence 引用）。
3) 失败时发出 `error` + `final`。

# Verification
- **Unit**: `pytest -q` 覆盖事件序列。
- **Smoke**: `backend/scripts/tool_registry_smoke_test.py`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 13.3 - 门禁：allowed tools 计算与校验（角色 + 意图 + 数据域）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：13.3 - 门禁：allowed tools 计算与校验（角色 + 意图 + 数据域）。
你的角色是 **高级开发工程师**。
你的目标是实现服务端强制门禁，保证“可用工具集合”由 **角色 + 意图 + 数据域** 决定，且任何越权/跨域/不在白名单的工具调用都必须被拒绝并审计。

# Critical Rules
- **Tool Whitelist (强制)**: 不允许由模型自由挑选工具；必须以服务端 allowed tools 计算结果为准。
- **RBAC & Data Isolation (强制)**: tenantId/projectId 缺失或不合法必须拒绝请求并审计；跨域访问必须返回 `AUTH_ERROR` 或 `FORBIDDEN`（以 contracts/实现约定为准）。
- **Read-Only Default (强制)**: L1 阶段拒绝任何写入/执行类工具；不确定是否写操作按只读处理。
- **Structured Errors (强制)**: 被拒绝的工具调用必须返回结构化错误（英文 `message`），并能在 SSE 中被解析。
- **Audit (强制)**: 审计记录必须包含：`requestId`、`intent`、`toolName`、拒绝原因摘要（脱敏）、`tenantId/projectId`、`userId/role`（如有）。

# References
- PRD: docs/requirements.md（R1.2/R1.3/R5.1/R15.1/R15.3）
- TDD: docs/design.md（2.4.2/2.5/4.4/6）
- tasks: docs/tasks.md（13.3）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files
- backend/gangqing/agent/
- backend/gangqing/tools/
- backend/gangqing/api/

# Execution Plan
1) 定义 allowed tools 计算输入/输出模型（Pydantic），并明确最小必需字段（intent、role/capabilities、tenantId/projectId、tool metadata）。
2) 实现门禁计算逻辑与校验逻辑（在工具调用入口处强制执行）。
3) 为拒绝路径补齐审计记录与结构化错误映射。

# Verification
- **Unit**: `pytest -q` 覆盖至少：
  - 角色不具备 capability -> `FORBIDDEN`。
  - tenantId/projectId 缺失或跨域 -> `AUTH_ERROR` 或 `FORBIDDEN`。
  - 意图为 action 或疑似写操作 -> `GUARDRAIL_BLOCKED`（或项目约定的拦截码）。
  - 不在白名单工具 -> 拒绝 + 审计。
- **Smoke**: `backend/scripts/tool_registry_smoke_test.py` 覆盖：
  - 触发一次越权/跨域工具调用，确认 SSE 中可解析到结构化 `error` 且审计落库。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检）
- [ ] 是否包含了 Umbrella 的 `# Critical Rules` 且明确禁止写代码？
- [ ] `# Execution Plan` 是否覆盖了 Task 13.1/13.2/13.3 且包含 Goal/Deliverables/Dependencies？
- [ ] 是否明确了工具白名单门禁：角色 + 意图 + 数据域？
- [ ] 是否明确了 Schema 单一事实源（后端 Pydantic / 前端 Zod）与对外契约对齐？
- [ ] 是否明确了结构化错误模型字段，且所有错误 `message` 都是英文？
- [ ] 是否明确了 Evidence-First 与 tool -> evidence 绑定字段要求？
- [ ] 是否明确了 RBAC + 审计 + `requestId` 贯穿要求与脱敏策略？
- [ ] 是否包含真实集成测试（Smoke）且强调不可 skip 的要求？
