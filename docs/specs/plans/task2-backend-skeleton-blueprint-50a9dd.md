# Task 2：后端工程骨架（FastAPI 网关层 + RequestContext 贯穿 + 结构化日志）执行蓝图

本蓝图定义 Task 2 的权威交付物边界：后端目录结构与模块边界、RequestContext 贯穿策略、结构化错误/日志/审计对齐、配置外部化与校验、最小健康检查链路以及测试与验收口径（不包含任何实现代码）。

## 0. 权威约束与契约锚点（必须对齐）

### 0.1 权威参考（本任务以这些文档为准）

- PRD：`docs/requirements.md`
- TDD：`docs/design.md`（重点：2.3/2.8/2.9/6.1/6.4/7）
- 对外契约草案：`docs/contracts/api-and-events-draft.md`
- API 文档：`docs/api/openapi.yaml`
- 审计落库参考实现：`backend/gangqing_db/`
- 冒烟脚本：`backend/scripts/`
- 配置枚举：`.env.example`
- 任务清单：`docs/tasks.md`（任务 2）

### 0.2 L1 不变式（Task 2 必须内建）

- **Schema 单一事实源**
  - 后端：对外 I/O、工具参数、Evidence、审计事件都以 **Pydantic** 为单一事实源。
  - 前端：对外 I/O、配置以 **Zod** 为单一事实源（本任务仅做后端锚点声明，不实现前端）。
- **Isolation 强制（L1 起启用）**：`tenantId/projectId` **无默认值**；缺失必须拒绝请求并审计。
- **requestId 贯穿**：HTTP 入站 → SSE Envelope → 工具调用 → 审计落库 → 对外响应（REST/SSE error）必须可按 `requestId` 聚合追溯。
- **结构化错误**：对外错误固定字段 `code/message(英文)/details?/retryable/requestId`。
- **配置外部化**：端口/URL/超时/重试/开关等禁止硬编码；启动/运行时必须校验。
- **真实集成测试（No Skip）**：冒烟/集成必须连真实服务；缺配置/依赖不可用必须失败。
- **Read-Only Default**：Task 2 不允许出现任何“写操作执行”路径；写相关仅允许预留“草案/审批材料”接口位点（但本任务不实现）。

### 0.3 契约锚点（本任务必须稳定）

- **ErrorResponse**：`code` / `message`（英文）/ `details?` / `retryable` / `requestId`
- **关键错误码（最小集合）**：
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
- **SSE Envelope**：统一 `{type,envelope,payload}`；`envelope` 强制包含：
  - `timestamp` / `requestId` / `tenantId` / `projectId` / `sessionId?` / `sequence`
- **健康检查**：`GET /api/v1/health` 对齐 contracts 第 2.2.1（含依赖探测清单与状态码策略）。

## 1. Directory Structure（交付物 1：权威目录树，不含实现代码）

> 目标：形成“可增量演进”的骨架，后续任务只在既定边界内新增功能，避免跨层耦合与契约漂移。

### 1.1 顶层分层（逻辑边界）

- **API 网关层（FastAPI）**：
  - 负责：入站校验、上下文提取、鉴权/RBAC（后续任务）、统一错误映射、SSE 编码与流控。
- **编排层（Agent Runtime）**：
  - 负责：意图识别/策略路由/步骤化执行（Task 2 仅预留接口与事件位点）。
- **工具层（Tools）**：
  - 负责：真实数据源访问（只读）、参数校验、超时/重试、证据输出、审计。
- **Common（跨层公共能力）**：
  - RequestContext、错误模型、日志与脱敏、配置加载校验、SSE Envelope 模型、审计事件模型等。
- **DB/Audit（存证层）**：
  - 负责：审计落库/查询（参考：`backend/gangqing_db/`）。

### 1.2 建议的目录树（与现有仓库结构对齐）

> 说明：仓库当前已有 `backend/gangqing/`（app/api/common/tools/schemas）与 `backend/gangqing_db/`；本蓝图只定义“应当如何组织与归属”，不要求本任务立即重构迁移。

- `backend/`
  - `gangqing/`（后端服务主包）
    - `app/`
      - **职责**：应用工厂/生命周期（create_app）、全局依赖注入装配（CORS、日志、错误处理、路由注册）。
    - `api/`
      - `v1/`
        - `health/`（或 `health.py`）
          - **职责**：`GET /api/v1/health` 端点与响应模型装配。
        - `chat/`（或 `chat.py`）
          - **职责**：`POST /api/v1/chat` 与 `POST /api/v1/chat/stream` 网关接口（Task 2 可仅要求框架位点与最小可运行链路，具体业务编排不在本任务）。
        - `auth/`（后续任务）
      - **规则**：handler 层必须完成入参校验 + RequestContext 依赖注入后，才进入编排/工具层。
    - `agent/`
      - **职责**：编排接口、意图/步骤模型、SSE 事件位点（Task 2 仅定义接口边界，不落业务）。
    - `tools/`
      - **职责**：只读工具封装（Postgres 等），统一 runner（RBAC/隔离/脱敏/审计/超时/重试/契约校验）。
    - `schemas/`
      - **职责**：对外契约与跨层共享的 Pydantic 模型集合（ErrorResponse/SSE Envelope/HealthResponse 等）。
      - **规则**：对外响应输出前必须通过 Pydantic 序列化/校验（避免契约漂移）。
    - `common/`
      - **职责**：
        - `context`：RequestContext 定义与提取/校验
        - `errors`：AppError/ErrorResponse 与错误码枚举
        - `logging`：结构化日志规范与绑定字段
        - `redaction`：脱敏工具（`redact_sensitive`）
        - `settings`：配置加载与校验
        - `sse`：SSE Envelope 编码/序列化/序列号管理（模型与协议规则，不含业务）
        - `observability`：预留 otel/metrics（Task 2 仅预留挂载点）
  - `gangqing_db/`（审计与数据库访问参考实现，已存在）
    - **职责**：审计事件 Pydantic 模型、落库/查询封装、DB 错误映射。
  - `scripts/`（冒烟/集成脚本，已存在）

### 1.3 模块边界强制规则

- **API 不得直接拼装审计 SQL**：只能调用 `gangqing_db` 的封装能力。
- **工具层不得直接写响应**：工具只返回结构化结果/结构化错误与证据对象；输出由网关层统一编码（REST/SSE）。
- **Pydantic 模型位置单一**：对外契约模型在 `gangqing/schemas`（或等价目录）集中维护；避免“同一结构多份定义”。

## 2. Environment Variables（交付物 2：ENV 枚举 + 校验/失败策略）

### 2.1 本任务必须识别并覆盖的关键 ENV（以 `.env.example` 为准）

- 运行态与日志
  - `GANGQING_ENV`
  - `GANGQING_LOG_LEVEL`
  - `GANGQING_LOG_FORMAT`
  - `GANGQING_REDACTION_SENSITIVE_KEY_FRAGMENTS`
- API
  - `GANGQING_API_HOST`
  - `GANGQING_API_PORT`
  - `GANGQING_CORS_ALLOW_ORIGINS`
- Isolation
  - `GANGQING_ISOLATION_ENABLED`
  - `GANGQING_ISOLATION_EXTRA_DIMENSIONS`
- 数据库（健康检查/审计落库相关）
  - `GANGQING_DATABASE_URL`
  - `GANGQING_HEALTHCHECK_POSTGRES_CONNECT_TIMEOUT_SECONDS`
  - `GANGQING_HEALTHCHECK_CACHE_TTL_SECONDS`
- 模型依赖探测（健康检查相关）
  - `GANGQING_LLAMACPP_BASE_URL`
  - `GANGQING_LLAMACPP_HEALTH_PATH`
  - `GANGQING_LLAMACPP_TIMEOUT_SECONDS`
  - `GANGQING_LLAMACPP_TRUST_ENV`
  - `GANGQING_LLAMACPP_CRITICAL`
  - `GANGQING_PROVIDER_HEALTHCHECK_URL`
  - `GANGQING_PROVIDER_TIMEOUT_SECONDS`
  - `GANGQING_PROVIDER_TRUST_ENV`
- 版本信息（健康检查响应 version 区）
  - `GANGQING_SERVICE_NAME`
  - `GANGQING_BUILD`
  - `GANGQING_COMMIT`

> 注：`.env.example` 中还有 JWT、脱敏策略、重试、造数、数据质量等配置；它们属于后续任务或更广范围能力。本任务只需保证“配置加载机制与校验框架”能覆盖这些项（至少做到：枚举齐全、类型校验、关键项缺失快速失败）。

### 2.2 配置加载与优先级（强制）

- 配置来源优先级：**进程环境变量** > **`.env.local`**（仅本地开发/测试）。
- 禁止交互式询问配置。
- 关键配置缺失必须快速失败，并输出**英文**错误消息（不得泄露密钥值）。

### 2.3 关键/非关键依赖与失败策略（与冒烟脚本对齐）

- **服务启动阶段（process start）**
  - 若 `GANGQING_DATABASE_URL` 缺失：
    - 若系统设计将 DB 视为 L1 必需（当前冒烟脚本要求）：必须启动失败。
  - 若 `GANGQING_LLAMACPP_BASE_URL` 与 `GANGQING_PROVIDER_HEALTHCHECK_URL` 都缺失：
    - 冒烟脚本要求至少一个存在：必须失败。
- **运行阶段（/api/v1/health）**
  - 依赖探测结果用于 overall `healthy/degraded/unhealthy`，并按契约映射 `200/503`。
  - 禁止在健康检查响应里泄露连接串、token、堆栈、上游正文。

## 3. API Skeleton（交付物 3：网关接口最小集合与分层边界）

### 3.1 最小端点集合（Task 2 骨架要求）

- `GET /api/v1/health`
  - 用途：运行态自检/依赖探测/发布门禁探针。
  - 契约：对齐 `docs/contracts/api-and-events-draft.md#2.2.1` 与 `docs/api/openapi.yaml`。
- （可选骨架位点）`POST /api/v1/chat/stream`
  - 用途：SSE 对话流式输出端点的**契约位点**（Task 2 不要求真实编排与工具调用，但必须明确：SSE Envelope、错误事件同构与 sequence 规则由网关层负责）。

### 3.2 路由分层与依赖注入边界

- `api/*`（handler 层）
  - 只做：
    - 入参 Pydantic 校验
    - `RequestContext` 提取与校验
    - RBAC/鉴权依赖注入（Task 2 可只预留接口，但必须预留上下文字段）
    - 统一错误映射到 `ErrorResponse`
    - 将请求委派给 `agent/*` 或 `tools/*`
- `agent/*`（编排层）
  - 对外暴露最小接口：接收 `RequestContext` + 结构化输入，产出结构化输出或 SSE 事件流描述。
- `tools/*`（工具层）
  - 接收 `RequestContext` + 工具参数（Pydantic）
  - 输出：结构化结果（Pydantic）+ Evidence 或结构化错误
  - 统一 runner 在工具层完成：隔离/RBAC/超时重试/审计/脱敏/契约校验

## 4. RequestContext Contract（交付物 4：字段、映射、拒绝策略、回传策略）

### 4.1 RequestContext 最小字段集合（强制）

对齐任务说明与设计文档（`docs/design.md#2.10.3`、`docs/contracts/api-and-events-draft.md#1`、tasks 2）：

- 强制字段
  - `requestId`
  - `tenantId`
  - `projectId`
- 建议字段（Task 2 定义贯穿策略，后续任务在鉴权/编排阶段填充）
  - `sessionId`
  - `userId`
  - `role`
  - `taskId`
  - `stepId`

### 4.2 HTTP 请求头到 RequestContext 的映射（强制）

- `X-Request-Id` → `requestId`
  - 可选：缺失时服务端生成。
- `X-Tenant-Id` → `tenantId`
  - 必填：缺失直接拒绝。
- `X-Project-Id` → `projectId`
  - 必填：缺失直接拒绝。
- `Authorization: Bearer <JWT>` →（后续任务）解析 `userId/role/capabilities`。

### 4.3 tenantId/projectId 缺失拒绝策略（强制 + 可审计）

- 任意对外端点（包含 `/api/v1/health`）只要缺少 `X-Tenant-Id` 或 `X-Project-Id`：
  - REST：返回 `401` 且响应体为 `ErrorResponse(code=AUTH_ERROR)`（契约草案明确）。
  - SSE：应在 `meta` 之后尽快输出 `error(payload=ErrorResponse)` + `final(status=error)`（若已建立流）。
- 审计要求：
  - 由于缺失 tenant/project 时无法安全落库审计（会违反隔离过滤），因此必须：
    - 仍然输出结构化日志（见第 6 章），并包含一个可定位的 `requestId`。
    - 若系统存在“无 scope 的审计通道”，需显式声明其隔离策略；否则本任务以“仅日志”作为缺 scope 场景的最小取证。

### 4.4 requestId 生成与回传策略（强制）

- 若请求头提供 `X-Request-Id`：
  - 必须原样贯穿并用于日志/审计/对外响应。
- 若未提供：
  - 必须在入口生成，并：
    - REST：在响应头 `X-Request-Id` 回传；在 `ErrorResponse.requestId` 回传。
    - SSE：在所有事件 `envelope.requestId` 填充同一值；错误事件 payload 内也包含同一 `requestId`。

## 5. Error Model（交付物 5：统一结构化错误模型与对齐规则）

### 5.1 对外错误模型（REST + SSE 同构）

- 模型名：`ErrorResponse`（契约草案明确要求统一命名）。
- 字段：
  - `code`：稳定错误码（枚举见 0.3）
  - `message`：**英文**
  - `details?`：结构化摘要（禁止敏感信息）
  - `retryable`：boolean
  - `requestId`：链路追踪 ID

### 5.2 REST 与 HTTP 状态码映射（强制）

以 `docs/contracts/api-and-events-draft.md#2.1.2` 为准，最小映射如下：

- `AUTH_ERROR` → 401
- `FORBIDDEN` → 403
- `VALIDATION_ERROR` → 400（请求体 schema 校验失败可选 422）
- `UPSTREAM_TIMEOUT` → 504
- `UPSTREAM_UNAVAILABLE` → 503
- `SERVICE_UNAVAILABLE` → 503
- `GUARDRAIL_BLOCKED` → 409
- `EVIDENCE_MISSING` → 422
- `EVIDENCE_MISMATCH` → 409
- `CONTRACT_VIOLATION` → 500
- `INTERNAL_ERROR` → 500

### 5.3 `details` 脱敏与允许字段（强制）

- 对外 `details` 仅允许（建议最小化）：
  - `reason`
  - `fieldErrors[]`（path/reason）
  - `source`（契约来源标识）
- 禁止包含：token/secret/password/cookie/authorization、原始 SQL、完整 rows、堆栈、连接串等。
- 审计事件与对外错误都必须使用统一的递归脱敏机制（参考：`gangqing.common.redaction.redact_sensitive` 与 `.env.example` 中的敏感 key fragments 配置）。

## 6. Logging & Audit（交付物 6：结构化日志字段与审计事件对齐）

### 6.1 结构化日志（JSON）最小字段集合（强制）

结合 `docs/tasks.md` 任务 2 与 `backend/scripts/start_server_and_healthcheck.py` 的日志取证要求：

- `event`：事件名（例如 `http_request`）
- `timestamp`
- `level`
- `requestId`
- `tenantId`（若可得；缺 scope 场景记录为缺失并附 `reason`）
- `projectId`（同上）
- `sessionId?`
- `userId?`
- `role?`
- `path` / `method` / `statusCode`
- `latencyMs`
- `stepId?` / `toolName?` / `toolCallId?`（当进入编排/工具时）

> 约束：日志必须可被冒烟脚本通过 `requestId` 精确定位到（脚本当前扫描 JSON 行，匹配 `event=http_request` 且 `requestId` 等于给定值）。

### 6.2 审计事件最小集合（本任务定义口径，复用现有实现）

对齐 `docs/design.md#2.8.1` 与 `docs/contracts/api-and-events-draft.md#4`：

- `query`
- `tool_call`
- `response`
- `error`
- （L4 预留，不在本任务实现）`approval` / `write_operation`

### 6.3 审计事件字段最小集合（强制）

与 `backend/gangqing_db/audit_log.py:AuditLogEvent` 现状对齐（alias 命名对外一致）：

- `eventType`
- `timestamp`
- `requestId`
- `tenantId`
- `projectId`
- `sessionId?`
- `userId?`
- `role?`
- `resource?`（工具名/资源名）
- `actionSummary?`（脱敏后的参数摘要）
- `result`（`success|failure`）
- `errorCode?`
- `evidenceRefs?`

### 6.4 审计落库关联策略（强制）

- `requestId` 是审计聚合主键：所有 `query/tool_call/response/error` 必须带同一 `requestId`。
- 隔离强制：审计表写入前必须设置会话级 scope（参考现有实现通过 `set_config('app.current_tenant', ...)` / `set_config('app.current_project', ...)`）。
- 脱敏强制：
  - `actionSummary` 在落库前递归脱敏。
  - 审计查询结果对外返回时同样不得泄露敏感信息。

## 7. 最小健康检查链路（交付物 7：健康检查契约与依赖探测策略）

### 7.1 `GET /api/v1/health` 契约（必须完全对齐 contracts）

- 请求头：
  - `X-Tenant-Id` 必须
  - `X-Project-Id` 必须
  - `X-Request-Id` 可选
- 响应：`HealthResponse`
  - `status`：`healthy|degraded|unhealthy`
  - `requestId`
  - `version`：`service/apiVersion/build/commit/startedAt`
  - `dependencies[]`：必须包含 `{config,postgres,llama_cpp,provider,model}` 五项（与冒烟脚本断言一致）
- 状态码：
  - overall `healthy|degraded` → 200
  - overall `unhealthy` → 503
  - 缺 scope headers → 401 + `ErrorResponse(code=AUTH_ERROR)`

### 7.2 依赖探测“关键性”策略（与 ENV 对齐）

- `config`：关键依赖（缺关键配置 → unhealthy）
- `postgres`：
  - 在当前冒烟脚本口径下视为关键依赖（缺 `GANGQING_DATABASE_URL` 冒烟直接失败）。
- `llama_cpp` 与 `provider`：
  - 只要两者至少一个在线即可认为模型能力可用（对齐 `.env.example` 说明）。
  - 具体是否 critical 由 `GANGQING_LLAMACPP_CRITICAL` 等配置决定，但健康检查必须明确将此信息落到 `dependencies[].critical` 字段。
- `model`：聚合项（由 llama_cpp/provider 探测结果组合给出）。

## 8. Verification & Acceptance（交付物 8：测试与验收口径）

### 8.1 自动化验证命令（本任务以 tasks.md 为准）

- 单元测试：`pytest -q`
- 冒烟测试：
  - `python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`

### 8.2 必测验收点（可自动化断言）

- **隔离拒绝**：
  - 缺 `X-Tenant-Id` 或缺 `X-Project-Id`：必须失败。
  - `/api/v1/health` 缺 `X-Tenant-Id`：必须 `401` 且 body 为 `ErrorResponse`，包含 `code/message/details/retryable/requestId`（对齐 `start_server_and_healthcheck.py`）。
- **requestId 回传与可定位**：
  - 当提供 `X-Request-Id` 时：响应体 `requestId` 必须一致；日志中必须出现 `event=http_request` 且 `requestId` 可被脚本检索到。
  - 当未提供 `X-Request-Id` 时：服务端生成，并在响应头与响应体/错误体中回传。
- **健康检查依赖清单**：
  - `dependencies` 必须为 list，且包含 `config/postgres/llama_cpp/provider/model` 五项。
- **敏感信息不泄露**：
  - 健康检查与错误 `details` 不得包含连接串/token/secret/cookie 等（契约草案明确禁止）。

## 9. 已确定结论（以当前实现与验收脚本为准）

### 9.1 `GANGQING_DATABASE_URL`：对当前实现/验收为强依赖

- 当前实现将 `GANGQING_DATABASE_URL` 视为 **config 探测的关键项**，缺失会导致健康检查整体 `unhealthy` 并返回 `503`：
  - 代码锚点：`backend/gangqing/common/healthcheck.py` 的 `probe_config` / `probe_postgres`
- 当前单元测试与冒烟脚本都将其视为 **必需配置**：
  - 单元测试锚点：`backend/tests/test_fastapi_skeleton.py::test_health_ok`（显式 `_require_env("GANGQING_DATABASE_URL")`）
  - 单元测试锚点：`backend/tests/test_fastapi_skeleton.py::test_health_unhealthy_when_database_url_missing`（缺失时断言 `503` + `unhealthy`）
  - 冒烟脚本锚点：`backend/scripts/start_server_and_healthcheck.py`（启动前 `_require_env("GANGQING_DATABASE_URL")`）

结论：在不修改验收脚本与测试口径的前提下，**Task 2 的当前实现要求 `GANGQING_DATABASE_URL` 必须配置**。

### 9.2 `/api/v1/health`：强制要求 `X-Tenant-Id` 与 `X-Project-Id`

- 当前 `/api/v1/health` 通过 `Depends(build_request_context)` 注入上下文，`build_request_context` 对缺失 scope header 的请求直接抛出 `AUTH_ERROR`：
  - 代码锚点：`backend/gangqing/common/context.py::build_request_context`
  - 代码锚点：`backend/gangqing/api/health.py::get_health`
- 单元测试与冒烟脚本均断言缺失 `X-Tenant-Id` 返回 `401` 且响应体为结构化 `ErrorResponse`：
  - 单元测试锚点：`backend/tests/test_fastapi_skeleton.py::test_missing_tenant_header_returns_auth_error`
  - 冒烟脚本锚点：`backend/scripts/start_server_and_healthcheck.py`（缺 header 的 failure path）

结论：在当前实现与验收口径下，**`/api/v1/health` 必须携带 `X-Tenant-Id` 与 `X-Project-Id`**。
