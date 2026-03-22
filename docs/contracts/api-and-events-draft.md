# API 与事件协议草案（Contracts Draft）
本文档定义 GangQing（钢擎）里程碑验收所需的核心接口形态与事件协议（含 SSE/WebSocket）、统一错误模型、证据链与审计事件的对外契约要点。本文档仅定义“接口长什么样/字段是什么/验收怎么验”，不包含任何业务实现。

## 0. 适用范围与强制约束
- **只读默认**：除非满足“权限 + 审批/多签 + 白名单 + Kill Switch 关闭”，否则不得执行写操作。
- **Evidence Required**：数值结论必须可追溯到数据源与时间范围；禁止伪造 evidence id。
- **RBAC & Masking**：所有接口/工具必须权限检查；敏感数据按角色脱敏。
- **Kill Switch**：写操作必须可熔断；熔断状态可审计、可观测。
- **Schema 单一事实源**：前端 Zod；后端 Pydantic；对外输出前必须 schema 断言/序列化校验。
- **Error Handling**：对外错误 `message` 必须英文；错误模型包含 `code/message/details?/retryable/requestId`。
- **Observability**：`requestId` 必须贯穿 HTTP→编排→工具→审计→对外响应。
- **Isolation**：`tenantId/projectId` 从 L1 起强制启用。
- **Streaming**：对话输出需同时支持 SSE 与 WebSocket。

## 1. 统一头部与上下文（RequestContext）

### 1.1 请求头（建议）
- `X-Request-Id`
  - 客户端可传入；未传入则服务端生成并回传。
- `Authorization: Bearer <JWT>`
- `X-Tenant-Id`
- `X-Project-Id`

### 1.2 服务端上下文（贯穿字段）
- `requestId`（强制）
- `tenantId`、`projectId`（强制）
- `sessionId`（对话会话标识，若有）
- `userId`、`role`（鉴权后）
- `taskId/stepId`（Agent 编排过程可选）

## 2. 统一错误模型（对外）

### 2.1 ErrorResponse（草案字段）
- `code`：稳定错误码
  - 示例：`VALIDATION_ERROR`、`AUTH_ERROR`、`FORBIDDEN`、`NOT_FOUND`、`UPSTREAM_TIMEOUT`、`UPSTREAM_UNAVAILABLE`、`SERVICE_UNAVAILABLE`、`CONTRACT_VIOLATION`、`GUARDRAIL_BLOCKED`、`EVIDENCE_MISSING`、`EVIDENCE_MISMATCH`、`INTERNAL_ERROR`
- `message`：英文可读描述（强制）
- `details?`：结构化上下文（禁止敏感信息）
- `retryable`：是否可重试
- `requestId`：链路追踪 ID（强制）

#### 2.1.2 REST 错误码与 HTTP 状态码映射（强制）

说明：REST 任意非 2xx 的响应体必须为 `ErrorResponse`；状态码按下表稳定映射。

| ErrorResponse.code | HTTP Status | 说明 |
| --- | --- | --- |
| `VALIDATION_ERROR` | 400 | 业务参数不合法（例如工具入参、过滤条件、时间范围）；如为请求体 schema 校验失败，可选 422 |
| `AUTH_ERROR` | 401 | 缺少/无效鉴权信息或缺少隔离上下文（`X-Tenant-Id/X-Project-Id`） |
| `FORBIDDEN` | 403 | RBAC 拒绝（缺少 capability） |
| `NOT_FOUND` | 404 | 资源不存在 |
| `UPSTREAM_TIMEOUT` | 504 | 上游超时 |
| `UPSTREAM_UNAVAILABLE` | 503 | 上游不可用 |
| `SERVICE_UNAVAILABLE` | 503 | 服务过载/队列满/系统暂不可用 |
| `GUARDRAIL_BLOCKED` | 409 | 红线/物理边界/安全策略阻断 |
| `CONTRACT_VIOLATION` | 500 | 系统契约错误（输出不符合 schema）；客户端应携带 requestId 报障 |
| `EVIDENCE_MISSING` | 422 | 证据缺失导致无法给出可验证结论（可按产品交互策略调整） |
| `EVIDENCE_MISMATCH` | 409 | 证据与结论不一致 |
| `INTERNAL_ERROR` | 500 | 未捕获异常 |

注：SSE/WebSocket 流式错误不使用 HTTP 状态码表达失败原因，必须通过同构的 `ErrorResponse.code` 表达。

#### 2.1.3 `details` 脱敏与允许字段（强制）

通用规则：
- `details` 仅允许结构化摘要，禁止放入密钥、token、cookie、原始 SQL、完整 rows、堆栈等大对象。
- 对外 `ErrorResponse` 不得包含 `tenantId/projectId/userId/role/sessionId` 等上下文字段。

禁止 key（大小写不敏感；命中任意片段即必须替换为 `[REDACTED]`）：
- `password` / `passwd`
- `secret`
- `token`
- `api_key` / `apikey`
- `authorization`
- `cookie` / `set-cookie`

允许字段（建议最小化）：
- `details.reason`：稳定原因枚举/字符串
- `details.fieldErrors[]`：字段级错误摘要（path/reason）
- `details.source`：契约来源标识（例如 `tool.postgres_readonly.result`）

实现要求：
- 审计事件 `actionSummary/argsSummary` 与对外 `details` 必须在落库/对外前执行递归脱敏（参考后端 `redaction` 机制：按 key 片段替换为 `[REDACTED]`）。

 约束：
 - 对外 `ErrorResponse` **仅允许**以上 5 个字段；禁止额外输出 `tenantId/projectId/sessionId` 等上下文字段（这些字段应通过请求头、SSE envelope、审计事件与结构化日志贯穿）。
 - 对外错误模型统一命名为 `ErrorResponse`（文档中不再并列使用 `AppError` 作为对外模型名）。

#### 2.1.0 REST 与 SSE 错误同构规则（强制）

- REST：任意非 2xx 响应体必须为 `ErrorResponse`。
- SSE：当 `type=error` 时，其 `payload` 必须为 `ErrorResponse`。
- SSE：当 `type=tool.result` 且 `status=failure` 时，`payload.error` 必须为 `ErrorResponse`。

#### 2.1.0.1 SSE 事件 envelope（扁平字段，强制）

说明：SSE 事件采用统一 envelope 字段，且**必须为扁平结构**（不得嵌套 `envelope` 对象），用于前端可解析渲染与可观测性关联。

最小字段集合：
- `type`：事件类型（见下文）
- `timestamp`：UTC ISO 8601
- `requestId`：链路追踪 ID（强制）
- `tenantId` / `projectId`：隔离上下文（强制）
- `sessionId?`：会话 ID（可选）
- `sequence`：单连接内递增序号（强制）
- `payload`：事件负载（随 `type` 变化）

约束（强制）：
- `message` 字段（若存在）必须为英文。
- 任意不可恢复错误必须尽快输出 `type=error`（payload 为 `ErrorResponse`），并紧跟 `type=final`。

#### 2.1.0.2 SSE 事件类型（最小集合，验收必需）

说明：为支持“重试/降级可视化 + 结构化错误 + 可追溯审计”，SSE 流必须包含如下可解析事件。

- `meta`
  - `payload.capabilities.streaming: boolean`
  - `payload.capabilities.evidenceIncremental: boolean`
  - `payload.capabilities.cancellationSupported: boolean`

- `progress`
  - 用途：阶段提示（含重试/降级的用户可见信息）
  - `payload.stage: string`
  - `payload.message: string`（英文）
  - `payload.stepId?: string`

- `warning`
  - 用途：可恢复异常（将重试/降级）
  - `payload.code: string`（建议复用稳定错误码，如 `UPSTREAM_TIMEOUT`）
  - `payload.message: string`（英文）
  - `payload.details?: object | null`（结构化摘要，禁止敏感信息）

- `tool.call`
  - 用途：工具调用 attempt 开始
  - `payload.toolName: string`
  - `payload.attempt: number`
  - `payload.maxAttempts: number`

- `tool.result`
  - 用途：工具调用 attempt 结果
  - `payload.toolName: string`
  - `payload.status: success | failure`
  - `payload.attempt: number`
  - `payload.maxAttempts: number`
  - `payload.error?: ErrorResponse`（当 `status=failure` 时必须存在）

- `error`
  - 用途：不可恢复错误（必须尽快输出）
  - `payload: ErrorResponse`

- `final`
  - 用途：流结束标志
  - `payload.status: success | error | cancelled`

#### 2.1.1 错误码枚举（最小集合，验收必需）

| code | 触发场景（示例） | retryable | 客户端建议 |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 请求参数不合法（例如时间范围无效、`expected_interval_seconds<=0`、或请求体 schema 校验失败） | `false` | 修正参数后重试；不要盲目重试 |
| `AUTH_ERROR` | 缺少/无效鉴权信息（JWT 不合法、缺少 `X-Tenant-Id/X-Project-Id`） | `false` | 重新登录/补齐请求头；检查租户/项目上下文 |
| `FORBIDDEN` | RBAC 拒绝（缺少 capability） | `false` | 引导用户申请权限/切换角色；不要自动重试 |
| `NOT_FOUND` | 资源不存在（例如查询不存在的实体） | `false` | 提示用户检查 ID/筛选条件 |
| `UPSTREAM_TIMEOUT` | 上游服务请求超时（ERP/MES/OT 查询） | `true` | 适度重试（指数退避）；必要时降级展示缓存/最近一次结果 |
| `UPSTREAM_UNAVAILABLE` | 上游服务不可用/网络隔离不可达 | `true` | 提示稍后重试；触发告警与运维排查 |
| `SERVICE_UNAVAILABLE` | 服务过载/并发队列满/系统暂不可用 | `true` | 引导稍后重试；必要时降级；携带 requestId 便于排障 |
| `CONTRACT_VIOLATION` | 上游返回不符合契约（字段缺失/类型不匹配） | `false` | 记录 requestId 并上报；不要自动重试 |
| `GUARDRAIL_BLOCKED` | 触发红线/物理边界/安全策略阻断（写操作或越界） | `false` | 提示用户原因与合规流程；必要时走审批 |
| `EVIDENCE_MISSING` | 数值结论缺少可追溯证据（Evidence 缺失） | `false` | 降级为“仅展示数据与来源”；提示用户补充证据 |
| `EVIDENCE_MISMATCH` | 证据与结论不一致（口径/时间范围/来源不匹配） | `false` | 降级并提示用户；记录 requestId 便于审计 |
| `INTERNAL_ERROR` | 未捕获异常/系统错误 | `false` | 提示用户稍后重试；携带 requestId 报障 |
| `CONFIG_MISSING` | 启动时缺少必需配置项（环境变量未设置） | `false` | 检查 .env.example 并设置对应环境变量 |
| `CONFIG_INVALID` | 配置值格式/取值范围不合法 | `false` | 检查配置值格式是否符合要求 |
| `CONFIG_TYPE_ERROR` | 配置值类型不匹配（如预期 int 得 str） | `false` | 检查配置值类型是否正确 |
| `CONFIG_DEPRECATED` | 使用了已废弃的配置项 | `false` | 迁移到新配置项，参考文档说明 |

### 2.2 错误处理验收点
- 任意接口失败时均返回 ErrorResponse 结构（非裸字符串）。
- `message` 英文且可用于日志检索。
- `requestId` 必须存在且与审计事件可关联。

## 2.2.1 `GET /api/v1/health`（健康检查）

用途：
- 运行态自检与发布门禁探针。
- 汇总系统整体状态（`healthy`/`degraded`/`unhealthy`）与依赖探测结果（Postgres / llama.cpp / provider / model / config）。
- **不泄露敏感信息**（密钥、连接串、内部堆栈、上游响应正文等）。

请求头：
- `X-Tenant-Id`（必须）
- `X-Project-Id`（必须）
- `X-Request-Id`（可选；未传入则服务端生成并在响应头/响应体中回传）

响应头：
- `X-Request-Id`：总是返回（与响应体 `requestId` 一致）

响应体：`HealthResponse`

字段：
- `status`：`healthy | degraded | unhealthy`
- `requestId`：本次请求链路 ID
- `version`：版本信息
  - `service`：服务名（建议由 CI 注入）
  - `apiVersion`：固定为 `v1`
  - `build`：构建号（建议由 CI 注入）
  - `commit`：提交 SHA（建议由 CI 注入）
  - `startedAt`：服务进程启动时间（UTC ISO 8601）
- `dependencies[]`：依赖探测列表
  - `name`：`config | postgres | llama_cpp | provider | model`
  - `status`：`ok | degraded | unavailable`
  - `critical`：是否关键依赖（关键依赖不可用 => overall `unhealthy`）
  - `latencyMs?`：探测耗时（毫秒），可能为 `null`
  - `checkedAt`：探测时间（UTC ISO 8601）
  - `details?`：失败/降级的结构化摘要（**禁止敏感信息**）
    - `reason?`：稳定原因枚举/字符串（示例：`not_configured` / `not_configured_model_provider_required` / `timeout` / `connection_failed` / `unexpected_response` / `no_model_provider_online` / `config_missing` / `config_invalid` / `config_type_error`）
    - `errorClass?`：异常类型名（例如 `ReadTimeout`、`ConnectTimeout`）
    - `missingKeys?`：缺失的环境变量名列表（仅 key 名，不得包含值）
    - `configCode?`：配置错误码（当 `name=config` 且状态异常时），值为 `CONFIG_MISSING` / `CONFIG_INVALID` / `CONFIG_TYPE_ERROR` / `CONFIG_DEPRECATED`

状态码策略（强制）：
- `200`：整体状态为 `healthy` 或 `degraded`
- `503`：整体状态为 `unhealthy`
- `401`：缺少 `X-Tenant-Id` 或 `X-Project-Id`（返回 `ErrorResponse(code=AUTH_ERROR)`）

错误码：
- `AUTH_ERROR`：缺少/无效 scope headers（tenant/project）

敏感信息约束（强制）：
- 对外 `HealthResponse.dependencies[].details` **不得**包含：
  - 数据库连接串（例如 `postgresql://...`）
  - 密钥/Token（例如以 `sk-`/`nvapi-` 开头的 API key）
  - 明文密码/secret
  - 内部异常堆栈与上游返回正文

验收要点：
- 单元测试必须覆盖：
  - 成功路径
  - 缺 headers => `401` 且响应体为 `ErrorResponse`
  - 模型提供者全不可用 => overall `503`
  - 超时场景的 `details.reason=timeout` 且 `errorClass` 填充
- 冒烟测试必须覆盖：
  - 成功路径（输出稳定标志 `healthcheck_ok`）
  - 至少一个失败路径（例如缺少 `X-Tenant-Id` => `401`）

## 2.3 语义层 API（Semantic API）契约要点（验收必需）

语义层 API 位于：`/api/v1/semantic/*`。

### 2.3.1 隔离与上下文
- 必须携带：`Authorization`、`X-Request-Id`、`X-Tenant-Id`、`X-Project-Id`
- 错误返回：使用统一 `ErrorResponse`

说明：语义层 API 的“逐端点”文档（包含每个端点的 capability、错误码枚举、触发条件、以及成功/失败示例请求响应）以 `docs/api/semantic-api.md` 为准。

### 2.3.2 分页响应（强制）

对列表接口返回：
```json
{
  "total": 123,
  "items": []
}
```

### 2.3.3 端点列表（最小集合）

#### Equipment
- `POST /api/v1/semantic/equipment`
- `POST /api/v1/semantic/equipment/batch`
- `GET /api/v1/semantic/equipment/{unified_id}`

#### Material
- `POST /api/v1/semantic/materials`
- `POST /api/v1/semantic/materials/batch`
- `GET /api/v1/semantic/materials/{unified_id}`

#### Batch
- `POST /api/v1/semantic/batches`
- `POST /api/v1/semantic/batches/batch`
- `GET /api/v1/semantic/batches/{unified_batch_id}`

#### Events
- `POST /api/v1/semantic/events`
- `POST /api/v1/semantic/events/batch`
- `GET /api/v1/semantic/events`（分页：`limit`/`offset`）

#### KPI Definitions
- `POST /api/v1/semantic/kpis`
- `POST /api/v1/semantic/kpis/batch`
- `GET /api/v1/semantic/kpis`（分页：`limit`/`offset`）
- `GET /api/v1/semantic/kpis/{kpi_id}`
- `GET /api/v1/semantic/kpis/{kpi_id}/lineage`

## 2.4 数据接入与数据质量治理 API（Data API）契约要点（T3）

数据接入与数据质量治理 API 位于：`/api/v1/data/*`。

### 2.4.1 端点列表（最小集合）
- `GET /api/v1/data/connectors`
  - 返回接入系统清单（ERP/MES/EAM/LIMS/OT），以及每个系统的只读能力边界（entities）。
- `POST /api/v1/data/timeseries/align`
  - 目的：不同采样频率对齐到统一时间窗口（按 bucket 聚合）。
- `POST /api/v1/data/quality/report`
  - 目的：对给定时间范围与点集生成质量报表（缺失/异常/漂移）与 `data_quality_score`。

### 2.4.2 `quality_code` 语义与评分映射（PoC 口径）

- `quality_code`：来源系统对采样点的数据质量标记（OT/历史系统常见）。本任务 PoC 采用最小映射：
  - `0`/`bad`/`invalid`/`unknown`（忽略大小写与空白）视为坏值
  - 其他值视为好值
- 映射关系：
  - 点级质量码得分：坏值 → `0.0`；好值/缺失（`null`）→ `1.0`
  - 桶级（对齐结果）得分：桶内点级得分的平均值
  - 报表级（quality report）得分：在 `data_quality_score` 中以 `quality_code_weight` 作为惩罚项（坏值比例越高，分数越低）

可配置项：
- `GANGQING_DATA_QUALITY_QUALITY_CODE_BAD_VALUES`
- `GANGQING_DATA_QUALITY_QUALITY_CODE_WEIGHT`

### 2.4.3 `GET /api/v1/data/connectors`

用途：返回接入系统清单（PoC：仅配置展示 + 只读边界声明，不发起真实连接）。

请求头（必须）：
- `Authorization`
- `X-Request-Id`
- `X-Tenant-Id`
- `X-Project-Id`

响应 200（示例）：
```json
{
  "connectors": [
    {
      "system": "ERP",
      "mode": "read_only",
      "entities": ["material", "order"],
      "endpoint": {"host": "erp.example", "port": 443}
    }
  ]
}
```

可能错误码：
- `AUTH_ERROR`（缺少 tenant/project 或鉴权失败）
- `FORBIDDEN`（无 `data:connectors:read` 权限）

### 2.4.4 `POST /api/v1/data/timeseries/align`

用途：将点位时序对齐到统一时间窗口（bucket 聚合）。

请求体（示例）：
```json
{
  "points": [
    {"ts": "2026-02-17T00:00:01+00:00", "value": 10.0, "quality_code": "192"}
  ],
  "alignment": {"method": "bucket_avg", "window_seconds": 60}
}
```

参数约束：
- `alignment.window_seconds >= 1`
- `points[].ts` 必须为 ISO 8601；时区策略：若输入为 naive datetime，服务端按 UTC 处理。

响应 200（示例）：
```json
{
  "aligned": [
    {
      "bucket_start": "2026-02-17T00:00:00+00:00",
      "value_avg": 10.0,
      "count": 1,
      "data_quality_score": 1.0
    }
  ]
}
```

可能错误码：
- `VALIDATION_ERROR`
  - 请求体 schema 校验失败（HTTP 422）
  - 或对齐参数不合法（HTTP 400）
- `AUTH_ERROR` / `FORBIDDEN`

### 2.4.5 `POST /api/v1/data/quality/report`

用途：生成数据质量报表（缺失/异常/漂移/质量码）与综合评分 `data_quality_score`。

请求体（示例）：
```json
{
  "start": "2026-02-17T00:00:00+00:00",
  "end": "2026-02-17T00:04:00+00:00",
  "points": [
    {"ts": "2026-02-17T00:00:00+00:00", "value": 10.0, "quality_code": "192"}
  ],
  "expected_interval_seconds": 60
}
```

参数约束：
- `end > start`
- `expected_interval_seconds >= 1`

评分与算法（PoC）：
- 异常检测方法由配置项控制：
  - `GANGQING_DATA_QUALITY_ANOMALY_METHOD=zscore|iqr`
  - `GANGQING_DATA_QUALITY_ANOMALY_Z_THRESHOLD`
  - `GANGQING_DATA_QUALITY_ANOMALY_IQR_MULTIPLIER`
- 质量报表缓存（PoC 内存缓存）：
  - `GANGQING_DATA_QUALITY_REPORT_CACHE_ENABLED=true|false`
  - `GANGQING_DATA_QUALITY_REPORT_CACHE_TTL_SECONDS=<seconds>`
  - 响应头：`X-Cache: MISS|HIT`

响应 200（示例）：
```json
{
  "time_range": {"start": "2026-02-17T00:00:00+00:00", "end": "2026-02-17T00:04:00+00:00"},
  "total_points": 1,
  "missing_points": 4,
  "missing_ratio": 0.8,
  "anomaly_points": 0,
  "drift_score": 0.0,
  "data_quality_score": 0.52,
  "issues": [
    {"issue_type": "missing", "message": "Missing data points detected", "details": {"expected": 5, "observed": 1}}
  ]
}
```

可能错误码：
- `VALIDATION_ERROR`（参数不合法/请求体校验失败）
- `AUTH_ERROR` / `FORBIDDEN`

## 3. Evidence（证据链）对外契约要点

### 3.1 Evidence（最小字段集合）
- `evidenceId`：证据唯一标识（不可伪造）
- `sourceSystem`：`ERP`/`MES`/`DCS`/`EAM`/`LIMS`/`Manual`/`Detector`
- `sourceLocator`：来源定位信息（表名/接口名/文档路径/记录 ID 等）
- `timeRange`：`start`/`end`
- `toolCallId?`：关联的工具调用 ID
- `lineageVersion?`：指标口径版本
- `dataQualityScore?`：数据质量评分（0-1）
- `confidence`：`Low`/`Medium`/`High` 或等价
- `validation`：`verifiable`/`not_verifiable`/`out_of_bounds`/`mismatch`
- `redactions?`：脱敏说明（可选）

#### 3.1.1 字段级约束（验收必需）
- `timeRange`：必须包含 `start` 与 `end`，且 `end > start`。
- `dataQualityScore?`：若存在，取值范围必须为 `0.0..1.0`。
- `sourceLocator`：必须足以定位到来源（表/接口/文档路径/记录 ID 等），且禁止包含密钥/凭证/敏感原值。

#### 3.1.2 `validation` 语义（强制）
- `verifiable`：证据可追溯且与结论一致。
- `not_verifiable`：无法验证（例如证据缺失、时间范围缺失、或因权限/脱敏导致无法复核）。
- `out_of_bounds`：触发物理边界/变化率边界等 guardrail（不一定表示“数据为假”，但表示不满足安全/一致性要求）。
- `mismatch`：证据与结论不一致（例如口径/时间窗/来源冲突，或同一指标多来源互斥且无法裁决）。

#### 3.1.3 Evidence 降级规则（强制）
- 当结论依赖的 Evidence 存在任意一条 `validation != verifiable` 时：
  - 必须输出至少 1 条 `warning` 事件，且 `warning.payload.code` 应复用稳定码（例如 `EVIDENCE_MISSING`、`EVIDENCE_MISMATCH`、`GUARDRAIL_BLOCKED`）。
  - 最终输出不得把不可验证/不一致的数值包装为“确定性结论”；必须以降级语义呈现（例如“仅展示数据与来源/不确定项”）。
- 当无法为关键数值结论提供任何可追溯 Evidence 时：
  - 必须降级，不得输出确定性数值；并输出 `warning`（推荐 `EVIDENCE_MISSING`）。

#### 3.1.4 `redactions`（脱敏说明）建议结构（SHOULD）

`redactions` 建议为结构化对象，用于审计与前端提示（仅说明“发生了什么脱敏”，不得泄露原值），例如：

```json
{"reason":"masked_by_role_policy","policyId":"rbac-finance-v1","fields":["unit_cost"]}
```

约束：
- `redactions` **不得**包含被脱敏字段的原始值。
- `redactions` **不得**包含任何密钥/凭证。

### 3.2 Evidence 验收点
- 数值结论必须能关联至少一个 Evidence。
- 证据缺失/不可验证必须触发降级提示，禁止伪造证据。

## 4. Audit Event（审计事件）对外契约要点

### 4.0 Guardrail Rules Catalog（权威枚举，验收必需）

说明：本章节用于枚举 Guardrail 默认规则目录（ruleId/category/defaultAction/errorCode/auditEventType），作为“规则 ID 可追溯”的权威来源。

约束（强制）：
- `ruleId` 必须为稳定字符串；审计与 Evidence 中引用的 ruleId 必须来自本目录或经过版本化扩展。
- `defaultAction` 为策略默认动作；实际动作以运行时策略计算结果为准。
- `errorCode` 映射遵循统一错误码（第 2 章）。
- `auditEventType` 为命中时必须落库的审计事件类型。

| ruleId | category | hitLocation | defaultAction | errorCode | auditEventType |
| --- | --- | --- | --- | --- | --- |
| `GUARDRAIL_INJ_DIRECT_IGNORE_RULES` | `prompt_injection` | `input` | `block_guardrail` | `GUARDRAIL_BLOCKED` | `guardrail.hit` |
| `GUARDRAIL_INJ_DIRECT_SYSTEM_PROMPT_EXFIL` | `prompt_injection` | `input` | `block_guardrail` | `GUARDRAIL_BLOCKED` | `guardrail.hit` |
| `GUARDRAIL_INJ_INDIRECT_INSTRUCTION_IN_CONTEXT` | `prompt_injection` | `tool_context` | `block_guardrail` | `GUARDRAIL_BLOCKED` | `guardrail.hit` |
| `GUARDRAIL_OUTPUT_SYSTEM_PROMPT_LEAK` | `output_safety` | `output` | `block_guardrail` | `GUARDRAIL_BLOCKED` | `guardrail.hit` |
| `GUARDRAIL_OUTPUT_SENSITIVE_TOKEN` | `output_safety` | `output` | `block_guardrail` | `GUARDRAIL_BLOCKED` | `guardrail.hit` |


### 4.1 审计事件类型
- `query`
- `tool_call`
- `approval`
- `write_operation`

补充（验收必需）：
- `guardrail.hit`：安全策略命中（阻断/降级）；禁止敏感原文落库。
- `auth.denied`：鉴权失败/缺 token 等（与 `AUTH_ERROR` 对齐）。
- `rbac.denied`：RBAC 拒绝（与 `FORBIDDEN` 对齐）。
- `data.masked`：审计检索发生脱敏策略命中（用于追踪策略生效）。

### 4.2 审计事件最小字段
- `eventId`
- `eventType`
- `timestamp`
- `requestId`（强制）
- `tenantId`、`projectId`（强制）
- `userId`、`role`
- `resource`（访问对象/工具名/草案/执行单等）
- `actionSummary`（脱敏后的参数摘要）
- `result`（success/failure + errorCode）

#### 4.2.1 `guardrail.hit` actionSummary 最小字段约束（验收必需）

说明：`guardrail.hit` 的 `actionSummary` 必须包含“可追溯但不泄露”的最小集合，用于复核拦截原因。

最小字段集合（强制）：
- `stage`：命中阶段（示例：`guardrail.input` / `guardrail.tool_context` / `guardrail.output`）
- `decisionAction`：`allow|warn_degrade|block_forbidden|block_guardrail`
- `policyVersion`：策略版本（示例：`guardrail_default@v1`）
- `riskLevel`：`low|medium|high`
- `timestamp`：UTC ISO 8601
- `hits[]`：命中摘要数组（元素至少包含 `ruleId/category/hitLocation/reasonSummary`）

按阶段补充字段（可选但推荐；若存在必须脱敏）：
- `inputDigest`：仅摘要（`sha256/length`），不得包含原文
- `toolName` / `toolCallId`：仅当 `stage=guardrail.tool_context` 或与工具调用有关时

禁止字段（强制）：
- 用户输入原文、系统提示词、工具返回原文、密钥/Token/凭证等任何敏感信息

### 4.3 审计存储与检索
- 先写 PostgreSQL（主存证），后写 Elasticsearch（ES）用于检索增强。
- 验收：可按 `requestId` 聚合检索并导出事件链。

## 5. 对话接口（非流式）形态草案

### 5.1 `POST /api/v1/chat`
用途：提交用户输入，返回一次对话结果（可选携带 evidence 摘要）。

请求（字段要点）：
- `sessionId`（可选，未传入则新建）
- `message`（用户输入文本）
- `attachments?`（上传文件引用）
- `clientContext?`（前端上下文，如页面/选区）

响应（字段要点）：
- `requestId`
- `sessionId`
- `assistantMessage`（最终文本或卡片摘要）
- `evidenceChain?`（Evidence 列表或引用）
- `auditRef?`（审计事件引用，如 eventId 列表）

验收点：
- `requestId` 贯穿；错误返回 ErrorResponse；数值输出可追溯。

## 6. 对话流式协议（SSE + WebSocket）

### 6.1 SSE：`POST /api/v1/chat/stream`

用途：对话流式输出（长耗时场景优先 SSE）。

#### 6.1.1 协议与序列化规则（强制）
- 响应 `Content-Type`：`text/event-stream`
- 每条 SSE 事件的 `data:` 必须为**单行 JSON**（禁止多行 JSON），便于客户端稳定解析。
- 事件类型通过 JSON 字段 `type` 区分（**不依赖** SSE 的 `event:` 行；服务端可输出 `event:` 作为兼容，但客户端与测试必须以 `type` 为准）。

#### 6.1.2 SSE 统一 Envelope（强制）

所有事件同形，统一结构如下：

- `type`（string，强制）：事件类型枚举，见 6.1.3
- `timestamp`（string，强制）：ISO 8601 时间戳
- `requestId`（string，强制）：链路追踪 ID
- `tenantId`（string，强制）：租户隔离 ID
- `projectId`（string，强制）：项目隔离 ID
- `sessionId`（string，可选）：对话会话 ID（若有）
- `sequence`（number，强制）：单 SSE 连接内单调递增
- `payload`（object，强制）：事件负载，与 `type` 对应

约束：
- 禁止在 `payload` 内重复输出 `requestId/tenantId/projectId/sessionId/sequence/timestamp` 等上下文字段。
- 禁止输出无法被 JSON 解析的值（例如 `NaN`/`Infinity`）。

#### 6.1.3 最小事件类型集合（验收必需）

以下事件类型为对外契约强制支持的最小集合，所有实现必须遵循：

| 事件类型 | 用途 | 首次出现时机 | 强制约束 |
|---------|------|------------|---------|
| `meta` | 元信息声明 | 必须为首事件 | `payload.capabilities` 必须声明 `streaming/evidenceIncremental/cancellationSupported` |
| `progress` | 阶段/步骤进度 | 处理开始后 | `payload.stage` 与 `payload.message` 必填 |
| `tool.call` | 工具调用开始 | 工具调用前 | `payload.toolCallId/toolName/argsSummary` 必填；`argsSummary` 必须脱敏 |
| `tool.result` | 工具调用结束 | 工具调用后 | `payload.toolCallId/toolName/status` 必填；`status=failure` 时 `payload.error` 必须为 ErrorResponse |
| `message.delta` | assistant 文本增量 | 生成回答时 | `payload.delta` 必填 |
| `evidence.update` | 证据链增量 | 工具返回证据后 | `payload.mode` 必填；`mode=append\|update` 时必须包含 `payload.evidences` |
| `warning` | 非致命降级/不确定项 | 检测到降级条件时 | `payload.code` 与 `payload.message` 必填 |
| `error` | 结构化错误 | 发生错误时 | `payload` 必须为完整 ErrorResponse 结构 |
| `final` | 结束事件 | 流结束前 | `payload.status` 必填；必须为最后一个事件 |

**事件序列约束（强制）**：
- `meta` 必须为首事件（`sequence=1`）
- `final` 必须为最后一个事件，之后不得再输出任何事件
- 发生错误时必须输出 `error` 事件，并紧随 `final(status=error)`
- `sequence` 在同一 SSE 连接内必须单调递增，不得跳号或重复

#### 6.1.4 各事件 payload 约束（字段级，验收必需）

说明：以下仅定义对外契约形态与字段约束，不包含任何内部实现细节。

##### `meta.payload`
- `capabilities`（object，强制）
  - `streaming`（boolean，强制，必须为 true）
  - `evidenceIncremental`（boolean，强制）
  - `cancellationSupported`（boolean，强制）

##### `progress.payload`
- `stage`（string，强制）：阶段名（例如 `intent`/`tooling`/`reasoning`/`finalizing`）
- `message`（string，强制）：面向用户的阶段提示（允许中文）
- `stepId`（string，可选）：编排步骤 ID

##### `tool.call.payload`
- `toolCallId`（string，强制）
- `toolName`（string，强制）
- `argsSummary`（object，强制）：脱敏参数摘要（禁止包含密钥与敏感原文）

##### `tool.result.payload`
- `toolCallId`（string，强制）
- `toolName`（string，强制）
- `status`（string，强制）：`success|failure`
- `resultSummary`（object，可选）：脱敏结果摘要
- `error`（object，可选）：当 `status=failure` 时必须存在，且必须为统一 ErrorResponse 结构
- `evidenceRefs`（array，可选）：证据引用（元素为 `evidenceId` 字符串）

##### `message.delta.payload`
- `delta`（string，强制）：文本增量

##### `evidence.update.payload`
- `mode`（string，强制）：`append|update|reference`
- `evidences`（array，可选）：Evidence 对象数组（元素见第 3 章 Evidence）
- `evidenceIds`（array，可选）：证据引用 ID 数组（元素为 `evidenceId` 字符串）

约束：
- `mode=append|update`：必须包含 `evidences` 且 `evidences.length >= 1`
- `mode=reference`：必须包含 `evidenceIds` 且 `evidenceIds.length >= 1`

映射规则（强制）：
- `mode=append`：新增 Evidence；`payload.evidences[*]` 必须满足 3.1 的最小字段集合与字段级约束。
- `mode=update`：更新既有 Evidence；`payload.evidences[*].evidenceId` 作为幂等键，更新必须遵守“字段不可回退/不可篡改来源”规则。
- `mode=reference`：仅引用；前端可按需通过证据链检索接口拉取详情。

##### `warning.payload`
- `code`（string，强制）：稳定码（推荐复用错误码：`EVIDENCE_MISSING`/`EVIDENCE_MISMATCH`/`GUARDRAIL_BLOCKED` 等，或扩展为 warning 专用枚举）
- `message`（string，强制）：英文可读描述（必须英文，便于日志检索）
- `details`（object，可选）：结构化上下文（禁止敏感信息）



##### `error.payload`
`payload` 必须为统一错误模型 ErrorResponse（见第 2 章），至少包含：
- `code`（string，强制）
- `message`（string，强制，必须英文）
- `details`（object，可选）
- `retryable`（boolean，强制）
- `requestId`（string，强制）

##### `final.payload`
- `status`（string，强制）：`success|error|cancelled`
- `summary`（object，可选）：脱敏摘要（可用于客户端收尾/归档）

约束（强制）：
- `final.payload` **不得**包含 `done`、`requestId` 等冗余字段；结束语义以 `status` 为准。

#### 6.1.5 事件序列验收（最小序列，强制）

- 成功路径：`meta` ->（0..n 条任意事件）-> `final(status=success)`
- 失败路径：`meta` ->（0..n 条任意事件）-> `error` -> `final(status=error)`

取消路径（强制，见 6.1.6）：
- 显式取消（连接仍存活）：`meta` ->（0..n 条任意事件）-> `final(status=cancelled)`
- 客户端断连：服务端必须尽快停止后续处理（停止输出/停止后续调用），但**不保证**客户端一定能收到 `final(status=cancelled)`（因为连接已断开）

约束：
- `meta` 必须为首事件。
- `final` 必须为最后一个事件；`final` 之后不得再输出任何事件。
- 发生错误时必须尽快输出 `error`，并紧随 `final(status=error)` 结束。
- `envelope.sequence` 在同一 SSE 连接内必须单调递增。

验收点：
- `error` 事件可解析为统一错误模型。
- 客户端取消（断开连接）需能向下传播，至少验证“服务端停止继续输出/停止后续工具调用”。
- 必须提供 SSE 端到端取证材料（抓包/录屏 + 事件样例），用于证明分段渲染、结构化错误、取消传播均满足口径。

#### 6.1.6 显式取消（REST）（强制）

> 目的：为“用户点击停止生成”等场景提供**可控、可审计、可自动化验证**的取消入口。

##### 端点

- `POST /api/v1/chat/stream/cancel`

##### 鉴权与隔离（强制）

- 必须要求登录态。
- 必须要求能力：`chat:conversation:stream`。
- 必须执行租户/项目隔离：只能取消同一 `tenantId/projectId` 作用域内的 `requestId`。

##### 请求

请求体（JSON）：

```json
{
  "requestId": "rid_xxx"
}
```

约束（强制）：
- `requestId` 必填且非空。

##### 响应

成功（200）：

```json
{
  "status": "ok"
}
```

失败（非 2xx）：必须返回统一错误模型 ErrorResponse（见第 2 章），且 `message` 必须英文。

推荐错误码（最小集合）：
- `VALIDATION_ERROR`：缺少/非法 `requestId`
- `AUTH_ERROR`：未登录/鉴权失败
- `FORBIDDEN`：缺少能力或跨 tenant/project 取消
- `NOT_FOUND`：`requestId` 未注册/已结束（实现可选；若实现选择幂等 ok，也必须在文档中声明）

##### 与 SSE 的行为约束（强制）

- 当服务端收到显式取消请求后：
  - 必须尽快停止该 `requestId` 的后续处理（推理/工具调用/证据生成等）。
  - 若 SSE 连接仍存活：必须输出 `final(payload.status=cancelled)`，并且 `final` 之后不得再输出任何事件。
  - 若 SSE 连接已断开：不要求输出 `final`，但仍必须停止后续处理。

##### 可验证口径（强制）

- 取消信号生效时间点之后：**不得再发起新的 `tool.call`**。
  - 允许在取消生效前已发起的工具调用自然结束或被工具层取消回调中断（实现策略可选），但不得出现“取消后仍持续发起新工具调用”的行为。

### 6.2 WebSocket：`/ws/chat`
- 消息必须是 JSON 事件，建议最小事件集合与 SSE 对齐：
  - `meta`、`delta`、`tool_call`、`evidence`、`error`、`done`

验收点：
- 支持双向：客户端可发送 `cancel` 事件请求取消。
- 客户端取消需能向下传播，至少验证“服务端停止继续输出/停止后续工具调用”。
- 必须提供 WebSocket 端到端取证材料（抓包/录屏 + 事件样例），用于证明分段渲染、结构化错误、取消传播均满足口径。

## 7. 审计检索接口（验收必需）

### 7.1 `GET /api/v1/audit/events`
- 查询参数（最小集合，验收必需）：
  - `limit`（int）
  - `offset`（int）
  - `requestId`（string，可选）：按链路追踪 ID 过滤
  - `unmask`（boolean，可选，默认 false）：是否请求返回未脱敏的 `actionSummary`

- 权限与脱敏（强制）：
  - `actionSummary` 在审计落库时必须执行默认脱敏（禁止把敏感原文写入审计表）。
  - `unmask=true` 仅表示客户端显式请求“尽可能返回未脱敏版本”。
    - 服务端必须执行 RBAC：仅当具备 `data:unmask:read` 能力时才可接受该请求；否则返回 `ErrorResponse(code=FORBIDDEN)`。
    - 即使具备能力，服务端也不得绕过“审计落库禁止敏感原文”的红线；若落库数据已脱敏，则 `unmask=true` 也可能无法还原原文。

- 过滤条件（要点）：
  - `requestId`、`sessionId`、`userId`
  - `tenantId`、`projectId`
  - `eventType`
  - `timeRange`

验收点：
- 能通过 `requestId` 检索到同一链路上的 query/tool_call/approval/write_operation。

## 8. 证据链检索接口（验收必需）

### 8.1 `GET /api/v1/evidence/chains/{requestId}`
- 返回：Evidence 列表 + 验证/降级信息。

验收点：
- 与对话响应一致；不可验证时有明确标记。

## 9. 写操作接口（Phase 4：受控闭环）

### 9.1 草案（Draft）
- `POST /api/v1/drafts`
  - 只生成草案，不执行。

### 9.2 审批/多签（Approval）
- `POST /api/v1/approvals/{draftId}/submit`
- `POST /api/v1/approvals/{draftId}/approve`
- `POST /api/v1/approvals/{draftId}/reject`
- `POST /api/v1/approvals/{draftId}/withdraw`

验收点：
- 每个动作写审计（approval）。

### 9.3 受控执行（Execution）
- `POST /api/v1/executions/{draftId}/execute`

验收点：
- 执行前检查：权限、审批状态、白名单范围、Kill Switch 状态。
- 执行产生 `write_operation` 审计。

### 9.4 回滚（Rollback）
- `POST /api/v1/executions/{executionId}/rollback`

验收点：
- 回滚动作可审计可复核。

## 10. Kill Switch（管理员）

### 10.1 `POST /api/v1/admin/kill-switch/enable`
### 10.2 `POST /api/v1/admin/kill-switch/disable`
### 10.3 `GET /api/v1/admin/kill-switch/status`

验收点：
- 开启熔断后所有写能力被阻断（降级仅查询）。
- 熔断启停操作写审计并可告警。

## 11. OT 写入的接口/通道约束（Phase 4 强制）
- OT 写入不得通过通用对话接口直接触发。
- 必须通过“受控执行网关 + 专用通道 + OT 二次确认”链路。
- 必须可审计并可复核二次确认记录。
