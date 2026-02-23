# T02 后端工程骨架（FastAPI 网关层 + RequestContext 贯穿 + 结构化日志）执行蓝图

本蓝图定义 GangQing L1 阶段后端骨架的目录结构、模块边界、RequestContext 贯穿策略、结构化日志与审计对齐方式，并明确测试与验收口径（不包含任何实现代码）。

## 1. 权威约束与对齐来源（Must）

- 权威需求（PRD）：`docs/requirements.md`
- 权威设计（TDD）：`docs/design.md`（重点：2.3/2.8/2.9/6.1）
- 任务拆解：`docs/tasks.md`（任务 2）
- 对外契约：`docs/contracts/api-and-events-draft.md`
- OpenAPI：`docs/api/openapi.yaml`

本任务必须满足以下“硬约束”（验收阻断项）：

- **Schema 单一事实源**：后端对外 I/O、工具参数、Evidence、审计事件统一用 **Pydantic**。
- **requestId 贯穿**：HTTP 入站 -> SSE envelope -> 工具调用 -> 审计落库 -> 对外响应。
- **隔离强制启用**：`tenantId/projectId` 从 L1 起强制（缺失即失败）。
- **结构化错误模型**：对外错误仅 `code/message(英文)/details?/retryable/requestId` 五字段；REST 与 SSE `type=error` 同构。
- **结构化日志（JSON）**：日志必须可按 `requestId` 聚合；敏感信息必须脱敏。
- **配置外部化 + 快速失败**：URL/端口/超时/重试/开关等禁止硬编码；关键配置缺失必须快速失败且英文错误消息。
- **真实集成测试（No Skip）**：冒烟测试必须启动真实 FastAPI，并对真实依赖进行可用性检查；缺配置/依赖不可用必须失败。

## 2. 目标边界（本任务做什么 / 不做什么）

### 2.1 本任务交付目标（T02）

- **可运行的最小 FastAPI 应用骨架**（网关层/路由分层清晰）。
- **RequestContext 机制落地方案**：字段定义、注入点、中间件/依赖策略、向下透传规范。
- **结构化日志 + 审计对齐方案**：字段字典、脱敏策略、与审计事件最小字段映射。
- **测试与验收口径**：单元测试覆盖范围与冒烟链路（含失败路径）定义清楚。

### 2.2 本任务不包含（明确不做）

- 不实现具体业务工具（如 Postgres 工具、llama.cpp 接入）与编排逻辑细节（但需预留边界与接口契约位置）。
- 不扩展/修改对外契约文档（除非发现 T02 与现有契约冲突；若冲突需在“决策点/风险”中提出）。

## 3. 后端目录结构与模块边界（Task 2.1）

目标：形成“API 网关 / 编排层 / 工具层 / 公共能力”四层清晰边界，使后续任务可增量交付且不产生契约漂移。

### 3.1 建议目录结构（仅文件清单与职责）

- `backend/gangqing/`
  - `app/`
    - **职责**：应用装配（创建 FastAPI app、路由挂载、生命周期、依赖初始化顺序）。
    - **边界**：不得包含业务逻辑与 SQL；只做 wiring。
  - `api/`
    - **职责**：HTTP 路由（REST + SSE + health），请求校验（Pydantic）、依赖注入、错误转换。
    - **边界**：不直接访问数据库/外部系统；调用编排层或服务层。
  - `agent/`
    - **职责**：编排层（意图识别/路由/步骤化执行/事件产出抽象）。
    - **边界**：不直接处理 HTTP；对上产出“事件流/结果对象”，对下调用工具层。
  - `tools/`
    - **职责**：外部系统/数据库只读工具封装（参数校验、超时、重试、脱敏、Evidence 产出）。
    - **边界**：对上只暴露“结构化结果 + Evidence/trace”，不暴露底层客户端细节。
  - `common/`
    - **职责**：跨层公共能力：
      - `RequestContext` 模型与上下文传播工具
      - 统一错误模型（对外 ErrorResponse + 内部错误类型）
      - 配置加载与校验（启动快速失败）
      - 结构化日志与脱敏工具
      - 审计事件模型与审计写入接口（仅接口/抽象；落库实现可在后续任务完善）
  - `schemas/`
    - **职责**：Pydantic schema 单一事实源聚合：
      - REST request/response
      - SSE event envelope/payload
      - Evidence
      - AuditEvent
    - **边界**：只放 schema，不放业务逻辑。

> 说明：如果仓库已存在同名模块（例如 `backend/gangqing_db`），应明确“DB 迁移/模型”与“业务 schema”的边界，避免 Pydantic/SQLAlchemy/迁移脚本相互耦合。

### 3.2 路由分层与挂载原则

- `api` 只做：
  - 入参校验（Pydantic）
  - 鉴权/RBAC/隔离上下文注入（通过依赖）
  - 调用编排层
  - 统一错误转换为 `ErrorResponse`
  - SSE 以统一 envelope 输出事件（单行 JSON）
- `agent` 负责：
  - 产生 `progress/tool.call/tool.result/evidence.update/message.delta/warning/error/final` 的“语义事件”对象（由 schema 定义）
  - 确保 `sequence` 递增、`meta` 首事件、`final` 末事件
  - 错误路径必须尽快发出 `error` + `final`
- `tools` 负责：
  - 工具参数 schema 校验
  - 超时/重试与可观测字段
  - Evidence 生成与脱敏摘要

### 3.3 最小端点集合（用于骨架与冒烟）

以 `docs/api/openapi.yaml` 为准，骨架阶段至少需要：

- `GET /api/v1/health`
  - 用于冒烟启动与健康检查。
- `GET /api/v1/chat/stream`
  - SSE 契约由 `docs/contracts/api-and-events-draft.md#6.1` 权威定义。
  - 骨架阶段可先保证事件流协议形态与错误同构，不要求真实业务产出。

> 注意：OpenAPI 当前已有 `/api/v1/auth/*` 与 `/api/v1/semantic/*` 路径描述，但 T02 只要求骨架与贯穿能力，是否在骨架阶段“挂空路由/占位路由”取决于你对 CI/冒烟的要求（见“决策点”）。

## 4. RequestContext 设计与贯穿（Task 2.2）

### 4.1 RequestContext 最小字段（Pydantic 模型）

必须字段（L1 验收阻断）：

- `requestId`
- `tenantId`
- `projectId`

推荐字段（可选，但建议纳入模型以便后续扩展且不破坏向后兼容）：

- `sessionId`（对话会话）
- `userId`、`role`（鉴权后写入）
- `taskId`、`stepId`（编排过程）

### 4.2 上下文来源与优先级

- 请求头：
  - `X-Request-Id`（可选；无则服务端生成并回传）
  - `X-Tenant-Id`（强制）
  - `X-Project-Id`（强制）
  - `Authorization`（后续任务使用；本任务需预留解析与注入点）
- 优先级（强制建议）：
  - **显式入站 header** > **服务端生成/推导**

### 4.3 注入点与传播路径（必须可审计）

- **HTTP 入站**：在“最早可用位置”生成/解析上下文，并在整个请求生命周期可获取。
- **SSE**：所有事件 envelope 必须携带：
  - `requestId/tenantId/projectId/sessionId?/timestamp/sequence/type/payload`
- **编排与工具调用**：
  - 任何工具调用必须接收 `RequestContext`（至少 `requestId/tenantId/projectId`）。
  - 工具日志与审计事件必须包含同一个 `requestId`。
- **对外响应（REST/SSE）**：
  - REST 错误：`ErrorResponse.requestId` 必须为当前上下文 `requestId`。
  - SSE `type=error`：payload 为 `ErrorResponse`，且其中 `requestId` 与 envelope 的 `requestId` 一致。

### 4.4 缺失上下文的失败策略（强制）

- 缺少 `tenantId` 或 `projectId`：
  - 直接失败，返回 `AUTH_ERROR`（英文 `message`），并确保返回体为 `ErrorResponse`。
- 缺少 `X-Request-Id`：
  - 不失败；服务端生成 `requestId` 并用于后续所有日志/审计/SSE。

## 5. 结构化日志与审计字段对齐（Task 2.3）

### 5.1 结构化日志（JSON）最小字段字典

日志的目的：可按 `requestId` 聚合链路；可与审计落库互相印证；可做脱敏后排障。

建议最小字段（按 `docs/design.md#2.8` 与任务要求）：

- `timestamp`（ISO 8601）
- `level`
- `message`（允许中文；但**错误对外 message 必须英文**）
- `requestId`（强制）
- `tenantId`（强制建议，与隔离一致）
- `projectId`（强制建议，与隔离一致）
- `sessionId`（可用时）
- `taskId`、`stepId`（可用时）
- `toolName`、`toolCallId`（工具相关日志）
- `durationMs`（工具/阶段耗时）
- `status`（success/failure）
- `error.code`、`error.message`（发生错误时；message 可为内部英文摘要，不泄露敏感信息）

> 约束：日志中不得出现密钥/凭证/敏感原值；对用户输入与工具参数仅记录“脱敏摘要/哈希/长度/字段名列表”等。

### 5.2 脱敏策略（日志与审计一致）

- **默认不记录原文**：用户 query、工具参数、工具结果均采用 `argsSummary/resultSummary`（契约也要求脱敏摘要）。
- **按角色策略**：涉及财务/配方/工艺参数等敏感字段，遵循 RBAC 与字段级脱敏规则（策略配置化）。
- **禁止记录**：
  - `Authorization` 原文
  - 数据库连接串中的密码
  - 外部系统 API key

### 5.3 审计事件最小字段与日志映射

审计事件权威字段见：`docs/contracts/api-and-events-draft.md#4`。

- 审计最小字段（建议骨架阶段就固定 schema）：
  - `eventId/eventType/timestamp`
  - `requestId`（强制）
  - `tenantId/projectId`（强制）
  - `userId/role`（鉴权后）
  - `resource`（访问对象/工具名）
  - `actionSummary`（脱敏参数摘要）
  - `result`（success/failure + errorCode）

映射要求：

- 日志字段应覆盖审计字段的“可观测子集”，使得：
  - **仅靠日志**能粗粒度重建 requestId 链路
  - **靠审计**能做合规取证与导出事件链

### 5.4 SSE 事件与日志/审计对齐

- `tool.call`/`tool.result` 事件 payload 中的：
  - `toolCallId/toolName/argsSummary/resultSummary/error?/evidenceRefs?`
  - 必须能映射到：
    - 工具调用日志（toolName/toolCallId/duration/status）
    - 审计事件（eventType=tool_call、resource=toolName、actionSummary=argsSummary、result=...）

## 6. 配置外部化与启动快速失败

### 6.1 配置原则（强制）

- URL/端口/超时/重试/开关（kill switch、缓存开关等）全部通过环境变量或配置文件提供。
- 本地 `.env.local`：环境变量优先级必须高于 `.env.local`。
- 缺失关键配置必须快速失败，且错误消息为英文（便于检索）。

### 6.2 建议配置项分组（用于后续统一管理）

- 服务基础：host/port/log_level
- 数据库：database_url、pool_size、timeouts
- 模型：llama_cpp_base_url、timeouts、max_concurrency
- 工具：默认超时、最大重试次数、退避策略
- 安全：jwt_secret/jwt_expiry、masking_policy_id
- 审计：audit_sink（postgres/es）、开关与批量写入参数

> 注意：本任务只产出“配置项清单与校验策略”，不在此处定义具体默认值。

## 7. 测试与验收口径（Verification）

### 7.1 单元测试（`pytest -q`）必须覆盖的断言

- `RequestContext`：
  - 未提供 `X-Request-Id` 时能生成且在响应/日志可见。
  - 缺少 `X-Tenant-Id` 或 `X-Project-Id` 时返回 `ErrorResponse(code=AUTH_ERROR)`。
- 错误模型：
  - REST 任意非 2xx 返回体必须为 `ErrorResponse` 五字段。
  - SSE `type=error` 的 `payload` 必须同构 `ErrorResponse`。
- SSE 协议形态：
  - 首事件为 `meta`，末事件为 `final`。
  - `sequence` 单调递增。
  - `data:` 必须是单行 JSON（避免多行 JSON）。
- 日志字段：
  - 至少能断言输出包含 `requestId` 字段（以及 tenant/project 若已注入）。

> 禁止跳过：单元测试不得通过 skip 逃避缺配置问题；缺少必须配置应触发失败并给出英文错误。

### 7.2 冒烟测试（`python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`）验收标准

- `compileall` 通过。
- 启动真实 FastAPI 服务后：
  - `/api/v1/health` 可访问。
  - 至少能观察到一次包含 `requestId` 的结构化日志输出。
- 若关键配置缺失或依赖不可用：
  - 冒烟测试必须失败（不得降级为“通过但提示”）。

> 说明：当前仓库是否已存在 `backend/scripts/start_server_and_healthcheck.py` 需要实现阶段核对；若不存在，应在实现阶段补齐脚本并纳入版本控制。

## 8. 决策点（需要你确认，避免骨架阶段返工）

1) **结构化日志库选型**：
   - 选 `structlog` 还是标准库 `logging` + JSON formatter？
   - 要求：输出 JSON、可注入上下文、与 Uvicorn/FastAPI 兼容。

2) **RequestContext 的技术承载**：
   - 中间件 + contextvars（全链路透明） vs 依赖注入显式传递（更显式可控）。
   - 要求：SSE 生成器/后台任务中不丢失上下文。

3) **审计落库介质与最小实现**：
   - 骨架阶段是否需要“真实写入 PostgreSQL audit 表”，还是仅定义 schema + 接口并在后续任务落库？
   - 约束：最终必须能按 `requestId` 聚合检索导出事件链。

4) **骨架阶段是否挂载 `/api/v1/auth/*` 与 `/api/v1/semantic/*` 的空路由**：
   - 优点：OpenAPI 与路由结构更一致
   - 风险：容易产生“看似可用但未实现”的误导

### 8.1 最终决策（已确认，作为后续实现与验收依据）

1) **结构化日志库**：选用 `structlog`（JSON 结构化日志）。
2) **RequestContext 贯穿机制**：以 **依赖注入显式传递**为主；`contextvars` 仅作为日志便利层（可选），不得作为业务/审计的唯一数据来源。
3) **审计落库**：T02 阶段即落库到 PostgreSQL（append-only 策略在后续任务完善，但 T02 必须做到可按 `requestId` 聚合检索审计链）。
4) **路由占位策略**：T02 不挂载 `/api/v1/auth/*` 与 `/api/v1/semantic/*` 的占位路由，仅保留本任务验收所需的最小端点集合（如 health、chat/stream）。

## 9. 风险清单与控制

- **契约漂移风险**：SSE envelope 与 `ErrorResponse` 字段必须以 `docs/contracts/api-and-events-draft.md` 为准；实现时必须增加 schema 断言。
- **上下文丢失风险**：SSE 流/异步任务容易丢失 `requestId`；必须在实现阶段引入自动化测试覆盖。
- **脱敏不一致风险**：日志与审计必须共享同一套脱敏工具/策略，避免重复实现导致遗漏。

## 10. 全网最佳实践推荐（基于官方/主流文档共识，面向 T02 落地）

说明：本节用于辅助你在 T02 的 4 个“决策点”上做最终选型。由于当前环境对外网抓取正文存在超时问题，本节以可验证的权威链接作为来源锚点，并给出与本仓库契约对齐的工程化建议。

### 10.1 权威参考链接（建议纳入后续评审材料）

- FastAPI
  - Dependencies（依赖注入）：https://fastapi.tiangolo.com/tutorial/dependencies/
  - Middleware（中间件）：https://fastapi.tiangolo.com/tutorial/middleware/
- Starlette（FastAPI 的 ASGI 基座）
  - Middleware（含 ContextVar 注意事项）：https://www.starlette.io/middleware/
  - Requests（断连检测 `request.is_disconnected()`）：https://www.starlette.io/requests/
  - Responses（StreamingResponse 等流式响应）：https://www.starlette.io/responses/
- structlog
  - contextvars 支持（并发安全上下文绑定）：https://www.structlog.org/en/stable/contextvars.html
- OpenTelemetry（后续 L2 可观测增强，但建议在 T02 预留对齐点）
  - Python Instrumentation：https://opentelemetry.io/docs/languages/python/instrumentation/
  - Python Logs auto-instrumentation example：https://opentelemetry.io/docs/zero-code/python/logs-example/

### 10.2 RequestContext 贯穿：推荐“显式传递为主 + contextvars 为辅”

在 FastAPI/Starlette 生态里，请求级上下文常见有两条路线：

- 路线 A：**依赖注入（DI）显式产出 `RequestContext`，并作为参数显式向下传递**。
  - 优点：
    - 边界清晰，测试更可控（单元测试可直接构造 `RequestContext`）。
    - 避免“隐式全局状态”导致的串扰与难排查。
    - 与你们的强约束（tenant/project 隔离、审计落库）更契合：每个工具/审计写入都必须拿到上下文。
  - 风险/成本：
    - 需要在 agent/tools 的函数签名中显式加入 `RequestContext` 参数（但这是契约化/可审计系统的合理成本）。

- 路线 B：**中间件绑定到 `contextvars`，日志等通过全局上下文自动取值**。
  - 优点：
    - 对日志埋点更“省心”，不必每次传参。
  - 风险：
    - 在复杂异步/流式（SSE 生成器、后台任务）场景下，上下文丢失/错绑的风险更高。
    - Starlette 文档明确提示了某些 middleware 形态下 `ContextVar` 的行为差异与注意事项（见 10.1 Starlette middleware 链接）。

**推荐策略（用于 T02）**：

- **DI 作为权威来源**：在网关层构造 `RequestContext`（含 `requestId/tenantId/projectId`），并显式注入到编排层与工具层。
- **contextvars 作为日志便利层（可选）**：如果选择 structlog，可用 contextvars 绑定 `requestId/tenantId/projectId/sessionId` 等，用于“少传参的日志一致性”；但不把它作为业务/审计的唯一数据来源。

### 10.3 结构化日志：推荐 `structlog`（若你接受一个依赖）

你们的日志要求本质是：

- JSON 结构化
- 可注入 request-scoped 字段（`requestId` 必须）
- 与审计字段对齐
- 与 async 并发安全

在这几个约束下，主流两种选择：

- `structlog`（推荐）
  - 适用理由：
    - 官方提供 `contextvars` 绑定能力，适配 async 并发，常用于 request-id 注入与日志关联（见 10.1 structlog 链接）。
    - 更容易把你们的“字段字典”固化为统一 processor pipeline（例如强制补齐缺失字段、统一脱敏处理）。
- 标准库 `logging` + JSON formatter
  - 适用理由：依赖更少。
  - 主要风险：
    - request-scoped 字段注入通常需要自建 Filter/Adapter/contextvars glue，工程一致性更难保证。

**推荐结论**：若允许引入依赖，T02 直接选 `structlog`，并把“字段字典 + 脱敏 + 上下文注入”集中在 `common/logging`（或等价模块）统一管理。

### 10.4 SSE 流式与取消/断连：推荐以 Starlette 能力为基础设计“可取消”的生成器

你们的契约要求：

- SSE 单行 JSON envelope（`meta` 首事件、`final` 末事件、`sequence` 递增）
- 发生错误尽快 `error` + `final`
- 客户端取消需向下传播（至少停止继续输出/停止后续工具调用）

工程最佳实践建议：

- **断连检测**：在流式输出循环中周期性检测客户端是否断开（Starlette `request.is_disconnected()` 的能力锚点见 10.1）。
- **取消传播**：将“取消状态”作为编排层的控制信号（例如传入 agent 的 cancel token/flag），使得：
  - 工具调用开始前先检查是否已取消
  - 工具调用进行中尽量支持超时/可中断（至少做到“不再发起新的工具调用”）
- **事件序列强约束**：建议在编排层使用一个“事件写入器/序列号分配器”的抽象，确保：
  - 所有事件都自动携带 envelope 字段（避免 payload 内重复上下文字段）
  - `sequence` 单调递增
  - `final` 之后禁止再写

### 10.5 审计：推荐“先定义稳定 schema，再决定落库时机”

对你们来说，审计的关键不在技术，而在“取证可复核、可按 requestId 聚合”。因此最佳实践是：

- **先固化审计事件 schema（Pydantic 单一事实源）**：字段以 `docs/contracts/api-and-events-draft.md#4` 为准。
- **实现上分两层**：
  - `common/audit` 定义事件模型、脱敏摘要生成、写入接口（sink abstraction）
  - sink 实现（Postgres/ES）可在后续任务增强

对 T02 的落地建议：

- 若你希望 T02 就可端到端验收“按 requestId 查到审计链”，则选择“在 T02 就写入 Postgres audit 表”。
- 若你更关注骨架的分层与契约稳定，可先定义 schema + 接口，并在 T02 的测试中至少断言“审计事件对象可被构造且包含必填字段”（但这会降低‘真实集成取证’强度）。


