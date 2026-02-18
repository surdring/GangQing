# Task 2 - 建立后端工程骨架（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 2 组任务：建立后端工程骨架（FastAPI 网关层 + RequestContext 贯穿 + 结构化日志）。
你的角色是 **技术负责人/架构师**。
你的目标是规划后端目录结构、核心模块边界、上下文贯穿与日志/审计基线，并定义验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 对外 I/O、工具参数、Evidence、审计事件必须用 Pydantic；前端对外 I/O/配置用 Zod。
- **Evidence-First**: 任何数值结论必须可追溯；不可验证必须降级输出 `warning`。
- **Read-Only Default**: 默认只读；写操作仅允许草案/审批/受控执行/回滚点/审计链路。
- **RBAC + 审计 + requestId 贯穿**: `requestId` 从 HTTP 入站生成/透传到 SSE 事件、工具调用、审计落库。
- **结构化错误**: `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **配置外部化**: 服务端配置必须从环境变量加载并校验（不得硬编码）。
- **真实集成测试（No Skip）**: 配置缺失或服务不可用，测试必须失败并输出英文错误。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`（#2、#11）
- tasks: `docs/tasks.md`（Task 2）
- contracts: `docs/contracts/api-and-events-draft.md`

# Execution Plan
1) Task 2.1 - 规划后端目录与分层边界
- Deliverables: `backend/` 目录结构（API 网关/编排层/工具层/配置/日志/审计/契约模型）。

2) Task 2.2 - RequestContext 与 requestId 贯穿策略
- Key Decisions:
  - requestId 生成位置（中间件）与透传（SSE 事件、工具调用、审计）。
  - sessionId / userId / role 的来源与校验。

3) Task 2.3 - 结构化日志基线
- Deliverables: JSON 结构化日志字段基线（至少 `requestId/sessionId/toolName/stepId`）。

4) Task 2.4 - 最小可运行服务与健康检查
- Deliverables: FastAPI app、路由注册、health endpoint（若已存在则对齐）。

# Verification
- Unit Tests: `pytest -q`
- Smoke Tests: `python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`

# Output Requirement
请输出详细执行计划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 2.1 - 创建后端目录骨架与模块边界

```markdown
# Context
你正在执行子任务：2.1 - 创建后端目录骨架与模块边界。
你的目标是新增 `backend/` 并实现清晰分层（API 网关/编排/工具/配置/审计/契约模型）。

# Critical Rules
- **Schema 单一事实源**: 后端所有对外契约必须用 Pydantic。
- **配置外部化**: 不得硬编码 URL/端口/超时/重试。
- **结构化错误**: 对外错误模型字段完整且 message 英文。
- **RBAC + 审计 + requestId**: 预留鉴权与审计写入点；贯穿 requestId。
- **真实集成测试（No Skip）**: 本子任务若需要连接真实服务（如 Postgres），缺配置必须失败并输出英文错误。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.1、#2.2）
- tasks: `docs/tasks.md`（Task 2）

# Execution Plan
1) 在 `backend/` 下创建分层包结构与最小入口。
2) 定义 `RequestContext`（Pydantic 或 dataclass + Pydantic 输出模型，按现有规范选型），并明确在 API 层构造。
3) 预留 `gangqing/` 业务包路径（若项目已有约定则对齐）。

# Verification
- `python -m compileall backend` 通过。

# Output Requirement
- 输出所有新增/修改文件（完整内容）。
```

### Task 2.2 - 实现 requestId 生成与透传（HTTP -> SSE -> 工具/审计）

```markdown
# Context
你正在执行子任务：2.2 - requestId 贯穿。
你的目标是保证每次请求都生成/接受 requestId，并在日志、SSE 事件、工具调用与审计事件中一致。

# Critical Rules
- **RBAC + 审计 + requestId 贯穿**: 必须在关键路径上可追溯。
- **结构化错误**: 任何对外错误必须携带 requestId。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.2、#11）
- tasks: `docs/tasks.md`（Task 2）

# Execution Plan
1) HTTP 入站：从 header 读取或生成 requestId。
2) 写入上下文：在整个请求生命周期可访问。
3) SSE：所有事件 envelope 必须携带 requestId。
4) 日志：结构化日志字段包含 requestId。

# Verification
- 单元测试：验证 requestId 生成/透传与缺失兜底。
- 冒烟：`python backend/scripts/start_server_and_healthcheck.py` 返回含 requestId 的健康响应（若适用）。

# Output Requirement
- 输出相关代码修改与测试文件。
```

### Task 2.3 - 结构化 JSON 日志

```markdown
# Context
你正在执行子任务：2.3 - 结构化日志。
你的目标是实现 JSON 结构化日志输出，并保证至少包含 `requestId/sessionId/toolName/stepId`（可用则填）。

# Critical Rules
- **结构化日志**: 字段稳定、可检索。
- **message 英文（仅错误）**: 错误模型 message 必须英文；日志文本可按既有风格，但建议关键字段结构化。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#11）
- tasks: `docs/tasks.md`（Task 2）

# Execution Plan
1) 选择并集成结构化日志方案（优先 structlog；若项目已有方案则沿用）。
2) 在请求入口/工具调用处补齐统一字段。

# Verification
- 单元测试：日志输出包含 requestId。

# Output Requirement
- 输出所有相关文件修改。
```

### Task 2.4 - 冒烟脚本：启动服务并健康检查

```markdown
# Context
你正在执行子任务：2.4 - 启动服务并健康检查脚本。
你的目标是实现/修复 `backend/scripts/start_server_and_healthcheck.py`，确保能在真实环境启动 FastAPI 并完成健康探测。

# Critical Rules
- **配置外部化**: 端口/host 等必须来自环境变量或统一配置。
- **真实集成测试（No Skip）**: 缺少必要配置必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 2）

# Execution Plan
1) 读取配置并启动服务进程。
2) 轮询 health endpoint，超时返回结构化错误（在脚本层可用英文异常信息）。

# Verification
- `python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py` 成功。

# Output Requirement
- 输出脚本与相关服务代码修改。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（在本任务 Umbrella 中声明；本任务实现以骨架为主）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
