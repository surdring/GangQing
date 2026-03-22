### Task 2 - 建立后端工程骨架（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 2 号任务：建立后端工程骨架（FastAPI 网关层 + RequestContext 贯穿 + 结构化日志）。
你的角色是 **技术负责人/架构师**。
目标是规划后端目录结构、核心模块边界、`RequestContext` 贯穿与结构化日志/审计对齐方式，并明确测试与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出具体实现代码。
- **Schema 单一事实源**: 后端对外 I/O、工具参数、Evidence、审计事件使用 Pydantic；前端对外 I/O/配置使用 Zod。
- **RBAC + 审计 + requestId 贯穿**: `requestId` 必须贯穿 HTTP 入站 -> SSE -> 工具调用 -> 审计落库 -> 对外响应。
- **结构化错误**: 对外错误 `code/message(英文)/details?/retryable/requestId`。
- **配置外部化**: 端口/URL/超时/重试等禁止硬编码。
- **真实集成测试（No Skip）**: 冒烟测试必须连真实服务，缺配置/依赖不可用必须失败。
- **Read-Only Default**: 默认只读；任何写操作仅允许生成草案与审批材料，禁止直接执行。
- **Isolation（强制）**: `tenantId/projectId` 从 L1 起强制启用；缺失必须拒绝请求并审计。

# References
- PRD: docs/requirements.md
- TDD: docs/design.md（2.3/2.8/2.9/6.1）
- 架构方案: docs/GangQing 自研 AI Copilot 核心组件技术方案(架构设计版).md
- tasks: docs/tasks.md（任务 2）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml
- 数据与审计实现参考: backend/gangqing_db/
- 后端冒烟脚本: backend/scripts/

# Scope (范围)
- 目标：定义“后端工程骨架”的权威边界与交付物定义，确保后续子任务可以在此骨架上增量开发。
- 本任务覆盖：FastAPI 分层、配置加载与校验、RequestContext 注入方案、结构化错误模型与对齐、结构化日志与审计字段约定、最小健康检查链路、基础测试与冒烟验收口径。
- 本任务不覆盖：具体业务工具实现（如 Postgres 只读工具细节）、Evidence 引擎完整实现、真实 LLM 编排逻辑（仅预留接口/事件位点），任何写操作执行链路。

# Execution Plan
1) Task 2.1（FastAPI 工程骨架与路由分层）
- 目标：形成 `backend/` 可运行最小骨架；按“API 网关/编排层/工具层”分层。

2) Task 2.2（RequestContext 设计与贯穿）
- 目标：定义 `RequestContext` 最小字段（`requestId/tenantId/projectId/sessionId/userId/role/taskId/stepId`）与透传策略。

3) Task 2.3（结构化日志与审计字段约定）
- 目标：日志 JSON 字段最小集合与敏感信息脱敏策略；与审计事件字段对齐。

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确新增/调整的目录树（只列结构，不写实现代码）。
- [ ] **Environment Variables**: 明确 Task 2 涉及的 ENV（来自 `.env.example`），并定义其校验/失败策略（缺失关键配置必须快速失败，英文错误消息）。
- [ ] **API Skeleton**:
  - 必须包含最小健康检查端点（用于冒烟与依赖探测）。
  - 必须明确路由分层与依赖注入边界（API/Agent/Tools/Common）。
- [ ] **RequestContext Contract**:
  - HTTP 入站请求头 -> RequestContext 字段映射。
  - 缺失 `tenantId/projectId` 的拒绝策略与审计要求。
  - `requestId` 自动生成与回传策略。
- [ ] **Error Model**: 统一结构化错误模型（字段与错误码来源），并明确用于 REST 与 SSE `error` 事件。
- [ ] **Logging & Audit**:
  - 结构化日志字段最小集合与脱敏策略。
  - 审计事件类型最小集合（query/tool_call/response/error 等）与 requestId 关联策略。

# Contract Anchors (契约锚点：必须对齐)
- 结构化错误模型字段：`code` / `message`（英文）/ `details?` / `retryable` / `requestId`
- 关键错误码（至少对齐 design.md 与 contracts 草案）：
  - `VALIDATION_ERROR`
  - `AUTH_ERROR`
  - `FORBIDDEN`
  - `NOT_FOUND`
  - `UPSTREAM_TIMEOUT`
  - `UPSTREAM_UNAVAILABLE`
  - `CONTRACT_VIOLATION`
  - `GUARDRAIL_BLOCKED`
  - `EVIDENCE_MISSING`
  - `EVIDENCE_MISMATCH`
  - `INTERNAL_ERROR`
  - `SERVICE_UNAVAILABLE`

# Environment Variables (本任务最小集)
以下为 Task 2 必须识别并在“配置加载与校验”中覆盖的关键配置项（以 `.env.example` 为准）：
- `GANGQING_ENV`
- `GANGQING_LOG_LEVEL`
- `GANGQING_LOG_FORMAT`
- `GANGQING_API_HOST`
- `GANGQING_API_PORT`
- `GANGQING_ISOLATION_ENABLED`
- `GANGQING_CORS_ALLOW_ORIGINS`
- `GANGQING_DATABASE_URL`（若健康检查包含 Postgres 探测，则缺失应失败；若不包含，则需明确其非关键依赖策略）

# Risks & Non-Goals (风险与边界提醒)
- 任何隐式默认 `tenantId/projectId` 都会造成安全降级：禁止设置默认值。
- 任何对外错误 `message` 使用中文会降低可检索性：必须英文。
- 未经授权不得引入写操作路径：即使未来预留，也只能是“草案/审批材料”。

# Verification
- 单元测试：`pytest -q`。
- 冒烟测试：`python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`。

# Verification Plan (整体验收：自动化断言)
- 结构化错误：当缺少 `X-Tenant-Id` 或 `X-Project-Id` 时，请求必须失败，并返回结构化错误（含英文 `message` 与 `requestId`）。
- requestId 贯穿：当未提供 `X-Request-Id` 时，服务端必须生成并在响应/日志/审计中可定位。
- 健康检查：冒烟脚本必须能启动 FastAPI 并通过健康检查端点；若依赖探测开启则必须对依赖不可用给出结构化结果或明确失败策略。

# Output Requirement
输出详细执行蓝图（Markdown），禁止写代码。
```

---

### Task 2.1 - FastAPI 工程骨架与路由分层

```markdown
# Context
你正在执行子任务：2.1 - FastAPI 工程骨架与路由分层。
目标是新增/调整 `backend/` 的基础目录结构、应用入口与路由模块边界，使后续功能可以在此基础上增量交付。

# Critical Rules
- **Schema 单一事实源**: 对外请求/响应模型必须 Pydantic。
- **结构化错误**: 对外错误必须使用统一错误模型字段；`message` 英文。
- **配置外部化**: 任何 host/port/timeouts 不得硬编码。
- **真实集成测试（No Skip）**: 冒烟脚本必须启动真实 FastAPI 并通过健康检查。

# References
- PRD: docs/requirements.md
- TDD: docs/design.md（2.3/2.4/2.8/2.9）
- tasks: docs/tasks.md（2.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 建立目录结构与模块边界（仅列文件清单，不写实现细节）：
- `backend/gangqing/api/`（路由与依赖注入）
- `backend/gangqing/agent/`（编排层：意图识别/路由/证据链）
- `backend/gangqing/tools/`（工具层：只读工具）
- `backend/gangqing/common/`（错误模型、RequestContext、配置加载、日志/审计公共能力）

2) 定义最小可运行入口与健康检查端点（契约与测试对齐）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 2.2 - RequestContext 设计与贯穿

```markdown
# Context
你正在执行子任务：2.2 - RequestContext 设计与贯穿。
目标是保证 `requestId` 与 scope 字段（`tenantId/projectId`）从 HTTP 入站开始贯穿到工具调用、审计与 SSE 输出。

# Critical Rules
- **requestId 贯穿（强制）**: 未提供则服务端生成并回传；日志与审计必须包含。
- **Isolation（强制）**: `tenantId/projectId` 从 L1 起强制启用。
- **结构化错误**: 缺少 scope 时返回 `AUTH_ERROR`，英文 `message`。

# References
- TDD: docs/design.md（2.3.1/2.3.2/2.8）
- tasks: docs/tasks.md（2.2）
- contracts: docs/contracts/api-and-events-draft.md（1/2）

# Execution Plan
1) 定义 RequestContext Pydantic 模型（最小字段集合与可选字段）。
2) 定义在 FastAPI 中的注入方式（依赖注入/中间件）。
3) 定义与 SSE 首事件/`meta` 事件的字段映射。

# Verification
- **Unit**: `pytest -q` 覆盖：未传 `X-Request-Id` 时自动生成；缺 scope 返回 `AUTH_ERROR`。
- **Smoke**: 通过健康检查脚本验证服务可启动；并在日志中看到 `requestId` 字段。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 2.3 - 结构化日志（JSON）与最小字段集合

```markdown
# Context
你正在执行子任务：2.3 - 结构化日志（JSON）与最小字段集合。
目标是统一日志字段，确保可观测与审计字段对齐，并避免敏感信息泄露。

# Critical Rules
- **结构化日志（强制）**: JSON 输出，至少包含 `requestId`，并在可用时包含 `sessionId/taskId/stepId/toolName`。
- **脱敏（强制）**: 日志/审计参数摘要必须脱敏，禁止写入密钥与敏感原文。
- **message 英文**: 错误消息英文。

# References
- PRD: docs/requirements.md（R11.x/R10.2）
- TDD: docs/design.md（2.8/4.2/6.1）
- tasks: docs/tasks.md（2.3）

# Execution Plan
1) 约定统一日志字段字典与日志级别策略。
2) 约定审计事件字段与日志字段的映射关系（至少能按 `requestId` 聚合）。

# Verification
- **Unit**: `pytest -q`（验证日志字段存在性可通过捕获 handler 或日志结构断言）。
- **Smoke**: 启动服务执行一次健康检查，查看日志输出包含 `requestId`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（本任务主要是骨架与日志；Evidence 约束仍在 Critical Rules 中保留）
- [x] 是否包含只读默认与审批链要求？（作为全局规则已写入）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
- [x] Doc References Updated
