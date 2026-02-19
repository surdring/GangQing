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

# References
- PRD: docs/requirements.md
- TDD: docs/design.md（2.3/2.8/2.9/6.1）
- tasks: docs/tasks.md（任务 2）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# Execution Plan
1) Task 2.1（FastAPI 工程骨架与路由分层）
- 目标：形成 `backend/` 可运行最小骨架；按“API 网关/编排层/工具层”分层。

2) Task 2.2（RequestContext 设计与贯穿）
- 目标：定义 `RequestContext` 最小字段（`requestId/tenantId/projectId/sessionId/userId/role/taskId/stepId`）与透传策略。

3) Task 2.3（结构化日志与审计字段约定）
- 目标：日志 JSON 字段最小集合与敏感信息脱敏策略；与审计事件字段对齐。

# Verification
- 单元测试：`pytest -q`。
- 冒烟测试：`python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`。

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
输出所有新增/修改的文件完整内容 + 测试命令与关键输出。
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
输出修改文件完整内容 + 测试命令。
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
输出修改文件完整内容 + 测试命令。
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
