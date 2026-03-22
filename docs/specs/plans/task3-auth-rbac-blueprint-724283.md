# Task 3（L1）认证与权限蓝图：JWT + RBAC 双层门禁 + 审计可追溯

本蓝图基于现有 contracts / OpenAPI / 后端骨架，给出 L1 必须落地的认证、RBAC 与审计的一致性规划（Schema First、双层门禁、tenant/project 隔离、requestId 贯穿），用于直接指导后续子任务 3.1/3.2/3.3 的实现与验收。

## 0. 范围与强制不变式（本任务 = Umbrella/Planning Only）

- **禁止写操作**
  - L1 不引入任何写能力；任何疑似写意图（或工具 side effect）按“只读默认”拒绝或进入 L4 治理（本任务仅定义拒绝策略与审计点位）。
- **Schema First（单一事实源）**
  - 后端：所有对外 I/O（REST/SSE）、RequestContext、ErrorResponse、RBAC 策略输入、审计事件均以 Pydantic 为准。
  - 前端：对外错误模型已存在 `web/schemas/errorResponse.ts`（Zod strict）。
- **RBAC 双层门禁（Defense in Depth）**
  - API 层：每个端点声明 capability，并在 handler 前完成校验。
  - 工具层：工具注册/执行入口必须再次校验 capability（防止绕过 API 直接调用工具 runner）。
- **Isolation（tenantId/projectId）**
  - L1 起强制启用；缺失或与 token scope 不一致 => **401 / AUTH_ERROR**。
- **requestId 贯穿**
  - HTTP 入站 -> RequestContext -> 工具调用 -> 审计落库 -> 对外响应（REST body / SSE envelope / structured logs）
- **Structured Errors（对外字段严格）**
  - 对外错误只允许 `code/message/details?/retryable/requestId`，`message` 必须英文。

## 1. 现状对齐（从仓库中已存在的权威实现/契约提取）

### 1.1 权威文档与契约

- **PRD**：`docs/requirements.md`
  - R1.1 登录返回 JWT；无效凭证 => `AUTH_ERROR`；token 过期需重新登录。
  - R1.2 RBAC：越权 => `FORBIDDEN`。
  - R1.3 隔离（数据域过滤/跨域拒绝）。
  - R11.1 审计：requestId + 工具调用 + 响应摘要 + error code/message。
- **TDD**：`docs/design.md`
  - 2.3.1：tenantId/projectId 必须存在；requestId 可缺失由服务端生成并回传。
  - 2.9：配置外部化、缺失快速失败、英文错误。
  - 2.10：工具装饰器/注册处应自动化一致性约束（RBAC/脱敏/审计/超时/证据）。
- **Contracts**：`docs/contracts/api-and-events-draft.md`
  - RequestContext headers：`X-Request-Id`/`Authorization`/`X-Tenant-Id`/`X-Project-Id`。
  - ErrorResponse：字段严格；REST 非 2xx 必须返回 ErrorResponse。
  - 审计事件最小字段；按 `requestId` 聚合。
- **Security Policy**：`docs/security/auth-rbac-audit-policy.md`
  - 审计 eventType 最小集合：`login.success/login.failure/auth.denied/rbac.denied/tool_call/api.response`。
  - 拒绝矩阵（401 vs 403）与审计要求。

### 1.2 已存在的后端骨架（可复用，不在本任务写实现）

- **RequestContext**：`backend/gangqing/common/context.py`
  - `tenantId/projectId` 缺失 => `AppError(AUTH_ERROR, message=Missing required header: ...)`
  - `requestId` 缺失 => 生成 UUID，并用于日志。
- **JWT（最小实现）**：`backend/gangqing/common/auth.py`
  - `Authorization: Bearer ...` 缺失/非法/过期/签名不匹配 => `AUTH_ERROR`。
  - token payload 含 `tenantId/projectId`，与 header scope mismatch => `AUTH_ERROR`。
- **RBAC**：`backend/gangqing/common/rbac.py`
  - capability 命名校验：必须为 `domain:resource:action` 三段。
  - 缺 capability => `FORBIDDEN`，并写 `rbac.denied` 审计（仅在 API 依赖处触发；工具侧需补齐同类审计点位）。
- **审计落库**：
  - schema：`backend/gangqing_db/audit_log.py::AuditLogEvent`（Pydantic；alias 与 contracts 一致）
  - 写入：`backend/gangqing/common/audit.py::write_audit_event/write_tool_call_event`
  - 规则：`actionSummary` 会被递归脱敏（`redact_sensitive`）。
- **冒烟测试脚本（真实服务）**：`backend/scripts/auth_smoke_test.py`
  - 覆盖：login success、缺 token 401、越权 403、可按 requestId 查询审计并能找到 denied 事件。

> 结论：本任务的蓝图需要在“既有骨架”上补齐统一规划口径（capability 表、拒绝矩阵、审计点位清单、模块边界/声明位置），确保后续实现不会出现“绕过 RBAC / 审计缺失”。

## 2. 目录与模块边界（Auth/RBAC/Audit/Config/RequestContext）

> 目标：把“权威逻辑”集中在少数模块，API 与工具仅做声明式引用，避免散落与绕过。

### 2.1 后端（`backend/gangqing/`）推荐边界

- **`gangqing/common/context.py`**
  - 职责：
    - 从请求头/`request.state` 构建 `RequestContext`（Pydantic）。
    - 强制 `tenantId/projectId`；生成并回传 `requestId`。
  - 不得包含：RBAC 规则、审计落库、具体业务。

- **`gangqing/common/auth.py`**
  - 职责：
    - 解析/校验 `Authorization`，输出 `AuthContext`。
    - 校验 token 的 `tenantId/projectId` scope 与 RequestContext 一致。
  - 约束：
    - 对外错误必须通过 `AppError` 生成 `ErrorResponse`。
    - 任何 token/password 等敏感数据不得进入日志/审计。

- **`gangqing/common/rbac.py`**
  - 职责：
    - capability 命名校验（`domain:resource:action`）。
    - 角色->capability 映射（L1 最小集合）。
    - API 依赖注入（`require_capability`）用于路由门禁。

- **`gangqing/tools/rbac.py`**
  - 职责：
    - 工具层 capability 校验入口（`require_tool_capability`）。
  - 强制：工具 runner 在执行前必须调用该校验（或等价机制），并写审计。

- **`gangqing/common/audit.py` & `gangqing_db/audit_log.py`**
  - 职责：
    - 审计事件 Pydantic schema（落库字段）。
    - append-only 落库，按 `requestId/tenantId/projectId` 可检索。

- **`gangqing/common/settings.py` / `gangqing_db/settings.py`**（已存在，规划约束）
  - 职责：
    - 所有配置外部化 + 启动时校验 + 缺失快速失败（英文 message）。

### 2.2 API 层（`backend/gangqing/api/`）边界

- API 层只做：
  - **契约（Pydantic request/response）声明**
  - **依赖注入组合**：`build_request_context` + `require_auth` + `require_capability`
  - **调用编排/工具入口**
  - **审计点位调用**（例如 login success/failure、api.response）

- API 层不得做：
  - 在 handler 内自定义 RBAC 判断逻辑（必须走统一能力检查函数/依赖）。
  - 直接拼装非结构化错误响应。

### 2.3 工具层（`backend/gangqing/tools/`）边界

- 工具层只做：
  - 参数 schema（Pydantic）
  - 工具自身业务（只读查询）
  - 调用工具 runner（统一做超时/重试/审计/脱敏/契约校验）

- 工具层强制：
  - 再次 RBAC 校验（capability）
  - 记录 `tool_call` 审计（argsSummary 脱敏）

## 3. 对外接口契约（REST + Structured Errors）

### 3.1 统一请求头（RequestContext）

- **必选**：
  - `X-Tenant-Id`
  - `X-Project-Id`
- **可选（建议）**：
  - `X-Request-Id`（可由客户端传入；缺失则服务端生成并在响应头/响应体/SSE envelope 回传）
  - `Authorization: Bearer <JWT>`（除 login/health 外的受保护端点必需）

### 3.2 ErrorResponse（对外唯一错误模型）

- 字段严格：
  - `code`（稳定错误码）
  - `message`（英文）
  - `details?`（结构化；禁止敏感信息；禁止堆栈/SQL/rows/token）
  - `retryable`（boolean）
  - `requestId`

- HTTP 状态码映射：以 `docs/contracts/api-and-events-draft.md#2.1.2` 为准
  - 401: `AUTH_ERROR`
  - 403: `FORBIDDEN`
  - 500: `CONTRACT_VIOLATION`/`INTERNAL_ERROR`

### 3.3 登录端点（R1.1）契约口径

- 端点：`POST /api/v1/auth/login`
- headers：
  - 按 contracts 建议支持 `X-Request-Id`（可选）
  - **本蓝图建议**：`X-Tenant-Id/X-Project-Id` 在 login 也允许并用于 token scope（与现有实现一致）
- request：
  - `username`（min_length=1）
  - `password`（min_length=1）
- response：
  - `accessToken`
  - `tokenType`（固定 `Bearer`）
  - `expiresAt`（epoch seconds）
- failures：
  - 无效凭证：401 + `AUTH_ERROR` + message=`Invalid credentials`

> 注意：当前 OpenAPI 中 `/api/v1/auth/login` 的 `X-Tenant-Id/X-Project-Id` 标记为 `required: false`，但 `build_request_context` 要求 scope 必填。后续任务需把 OpenAPI 与实现口径对齐（本 Umbrella 阶段仅记录为“必须修正的契约一致性项”，不写代码）。

## 4. Capability 模型（命名规范、声明位置、角色矩阵）

### 4.1 命名规范（强制）

- 格式：`domain:resource:action`
- 约束：
  - 必须正好 3 段
  - 每段使用小写字母/数字/下划线/短横线（建议）；禁止空段

### 4.2 能力点声明位置（双层门禁）

- **API 层声明（强制）**
  - 每个路由在定义处声明 capability（例如通过依赖注入 `require_capability("...")`）。
  - 目标：从 API 路由表能静态枚举“所有受保护能力点”。

- **工具层声明（强制）**
  - 每个工具在注册/类定义处声明 capability（例如 tool metadata / registry 字段）。
  - 工具 runner 在执行前调用 `require_tool_capability(ctx, capability)`。
  - 目标：即使绕过 API 直接调用工具 runner，也无法越权。

### 4.3 L1 最小角色与能力点矩阵（权威口径，后续实现必须以此为准）

> 角色集合与 design/requirements 对齐：厂长/调度员/维修工/财务。

| Role（role 值） | 业务含义 | 允许 capabilities（最小集合） |
| --- | --- | --- |
| `plant_manager` | 厂长/高管 | `chat:conversation:stream`  
`audit:event:read`  
`finance:report:read`  
`tool:demo:run`  
`tool:postgres:read`  
`metric:lineage:read` |
| `dispatcher` | 生产调度员 | `chat:conversation:stream`  
`tool:postgres:read` |
| `maintainer` | 设备维修工 | `chat:conversation:stream`  
`tool:postgres:read` |
| `finance` | 财务人员 | `audit:event:read`  
`finance:report:read` |

约束说明：
- 用例验收必须覆盖：`finance` 访问 `chat:conversation:stream` => `FORBIDDEN`（对应现有 `auth_smoke_test.py`）。
- `tool:postgres:read` 仅允许只读（SELECT）；任何写 SQL 属于读写治理范畴（本任务不开放）。

## 5. 拒绝策略矩阵（强制，REST 对外口径）

> 下表同时作为“错误码/HTTP 状态/审计 eventType”联动的权威口径。`message` 示例必须英文，便于日志检索；但不强制固定文案，只要语义一致、英文、可检索。

| 场景 | 对外错误码 | HTTP 状态码 | `ErrorResponse.message`（英文示例） | 是否写审计 | 审计 eventType（至少） | `details` 建议字段（脱敏） |
| --- | --- | --- | --- | --- | --- | --- |
| 缺少 `X-Tenant-Id` | `AUTH_ERROR` | 401 | `Missing required header: X-Tenant-Id` | 必须 | `auth.denied` + `api.response` | `{ "header": "X-Tenant-Id" }` |
| 缺少 `X-Project-Id` | `AUTH_ERROR` | 401 | `Missing required header: X-Project-Id` | 必须 | `auth.denied` + `api.response` | `{ "header": "X-Project-Id" }` |
| 缺少 `Authorization`（受保护端点） | `AUTH_ERROR` | 401 | `Missing Authorization header` | 必须 | `auth.denied` + `api.response` | `{ "header": "Authorization" }` |
| `Authorization` 非 Bearer | `AUTH_ERROR` | 401 | `Invalid Authorization header` | 必须 | `auth.denied` + `api.response` | `{ "reason": "invalid_scheme" }` |
| token 格式非法/签名错误 | `AUTH_ERROR` | 401 | `Invalid token` | 必须 | `auth.denied` + `api.response` | `{ "reason": "invalid_format|invalid_signature|invalid_encoding" }` |
| token 过期 | `AUTH_ERROR` | 401 | `Token expired` | 必须 | `auth.denied` + `api.response` | `{ "reason": "expired" }` |
| token scope 与 header scope 不一致 | `AUTH_ERROR` | 401 | `Invalid token scope` | 必须 | `auth.denied` + `api.response` | `{ "reason": "scope_mismatch" }` |
| capability 缺失 | `FORBIDDEN` | 403 | `Forbidden` | 必须 | `rbac.denied` + `api.response` | `{ "capability": "...", "role": "..." }` |
| capability 命名不合法（非三段） | `CONTRACT_VIOLATION` | 500 | `Invalid capability name` | 必须 | `api.response` | `{ "capability": "..." }` |

补充约束：
- `auth.denied` / `rbac.denied` 事件必须与对外 `ErrorResponse.code` 通过 `requestId` 可关联。
- 审计中不得记录 `Authorization` 原文或 token 原文（0 容忍）。

## 6. 审计事件（类型、最小字段、脱敏、取证聚合）

### 6.1 事件类型最小集合（L1 必须）

以 `docs/security/auth-rbac-audit-policy.md` 为准：
- `login.success`
- `login.failure`
- `auth.denied`
- `rbac.denied`
- `tool_call`
- `api.response`

### 6.2 审计最小字段（落库/可检索）

以 `docs/security/auth-rbac-audit-policy.md#1` 与 `docs/contracts/api-and-events-draft.md#4` 为准，并与现有 `AuditLogEvent` 对齐：
- `eventType`
- `timestamp`
- `requestId`
- `tenantId`
- `projectId`
- `sessionId?`
- `userId?`
- `role?`
- `resource?`
- `actionSummary?`（JSON；必须脱敏）
- `result`（success|failure）
- `errorCode?`

### 6.3 脱敏与禁止字段（强制）

- 禁止记录（必须为 0）：
  - `Authorization` 原文
  - token/password/secret/apiKey/cookie
  - 原始 SQL、全量 rows、堆栈
- 允许记录（建议最小化）：
  - `requestId/tenantId/projectId/userId/role`
  - `capability`
  - `toolName`
  - `statusCode/durationMs`（API 响应摘要）
  - `details.reason/header` 等结构化原因（不得含凭证原文）

### 6.4 取证聚合策略（强制）

- 聚合键：`tenantId + projectId + requestId`
- 最小可取证链路：
  - login（成功/失败）
  - 任意拒绝（auth.denied/rbac.denied）
  - tool_call（工具调用开始/结束，可用 result_status）
  - api.response（请求最终响应摘要）

## 7. 自动化验收口径（Unit + Smoke + Contract；真实服务）

> 强制：不允许 skip；冒烟必须连真实 FastAPI + 真实 Postgres（配置缺失/服务不可用必须失败）。

### 7.1 Unit Tests（pytest -q）最小用例清单

- JWT / Auth：
  - 登录成功返回 token（只断言结构：`accessToken/tokenType/expiresAt`）。
  - 无效凭证 => 401 + `ErrorResponse(code=AUTH_ERROR)` + message 英文。
  - 缺少/无效/过期 token => 401 + `AUTH_ERROR`。
  - scope mismatch（token tenant/project != header tenant/project）=> 401 + `AUTH_ERROR`。
- RBAC：
  - 角色越权 => 403 + `FORBIDDEN`。
  - capability 命名不合法 => 500 + `CONTRACT_VIOLATION`（系统错误路径）
- Isolation：
  - 缺少 `X-Tenant-Id` 或 `X-Project-Id` => 401 + `AUTH_ERROR`。
- 审计：
  - 拒绝场景必须写入审计记录（可通过真实 DB 集成测试验证；纯单元可用依赖注入的等价 fake，但不得跳过）。

### 7.2 Smoke Test（backend/scripts/auth_smoke_test.py）必须覆盖点

- 必须启动真实服务并连接真实 Postgres：
  - env 必需：`GANGQING_DATABASE_URL`；缺失直接失败。
- 必须验证：
  - login success
  - 缺 token => 401 + ErrorResponse 字段严格
  - 越权 => 403 + ErrorResponse 字段严格
  - 能通过 `GET /api/v1/audit/events?requestId=...` 查到 `auth.denied` 与 `rbac.denied`
  - structured logs 中存在 `event=http_request` 且带 `requestId`

### 7.3 Contract Tests（如仓库已有入口，需补齐断言点）

- REST：非 2xx 响应体字段 **不多不少**（严格为 ErrorResponse 5 字段）。
- 审计：拒绝场景在 audit events 可被检索，且能按 requestId 聚合。

## 8. 对后续子任务（3.1/3.2/3.3）的交付约束（DoD 口径）

- 3.1（JWT 登录）
  - 交付物：
    - 登录/refresh/logout 契约与错误码映射
    - JWT 配置项清单与快速失败策略
    - `login.success/login.failure` 审计事件落库

- 3.2（RBAC capability 与双层门禁）
  - 交付物：
    - capability 常量/枚举的单一事实源位置
    - API 路由 capability 声明覆盖率（必须 100%）
    - 工具 registry capability 声明覆盖率（必须 100%）

- 3.3（审计与拒绝策略）
  - 交付物：
    - `auth.denied/rbac.denied/tool_call/api.response` 全量点位
    - audit_log 可按 requestId 检索
    - 脱敏规则 0 泄露（token/password/secret 绝不落库）

## 9. 按当前代码实现锁定的决策（后续子任务实现口径）

1) **tenantId/projectId 的权威来源（双来源 + 一致性校验）**
- L1 口径以当前实现为准：
  - **每次请求必须带** `X-Tenant-Id` / `X-Project-Id`（由 `build_request_context` 强制）。
  - JWT payload **必须携带** `tenantId/projectId`，并在 `require_auth` 中与 headers 做 **scope 一致性校验**。
- 失败语义：缺失 scope headers 或 scope mismatch => `401 AUTH_ERROR`。

2) **login 端点 scope 强制**
- 以当前实现为准：`POST /api/v1/auth/login` 同样依赖 `build_request_context`，因此 **必须携带** `X-Tenant-Id/X-Project-Id`。
- 对后续任务的强制要求：
  - **必须修正 OpenAPI**（`docs/api/openapi.yaml`）中 login 端点对 `X-Tenant-Id/X-Project-Id` 的 `required` 标记，使其与实现一致，避免契约漂移。

3) **L1 角色集合固定为 4 个**
- 以当前 RBAC 实现为准：`plant_manager` / `dispatcher` / `maintainer` / `finance`。
- L1 **不新增** `admin` 等额外角色（否则需要同步：capability 矩阵、bootstrap 用户、冒烟脚本与验收口径）。

4) **审计查询权限允许财务角色**
- 以当前 RBAC capability 矩阵为准：`finance` 具备 `audit:event:read`。
- 对后续任务的强制要求：
  - `GET /api/v1/audit/events` 必须保持双层门禁：`require_authed_request_context`（Auth）+ `require_capability("audit:event:read")`（RBAC）。
