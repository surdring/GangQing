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
  - 示例：`VALIDATION_ERROR`、`AUTH_ERROR`、`FORBIDDEN`、`NOT_FOUND`、`UPSTREAM_TIMEOUT`、`UPSTREAM_UNAVAILABLE`、`CONTRACT_VIOLATION`、`GUARDRAIL_BLOCKED`、`EVIDENCE_MISSING`、`EVIDENCE_MISMATCH`、`INTERNAL_ERROR`
- `message`：英文可读描述（强制）
- `details?`：结构化上下文（禁止敏感信息）
- `retryable`：是否可重试
- `requestId`：链路追踪 ID（强制）

#### 2.1.1 错误码枚举（最小集合，验收必需）

| code | 触发场景（示例） | retryable | 客户端建议 |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 请求参数不合法（例如时间范围无效、`expected_interval_seconds<=0`、或请求体 schema 校验失败） | `false` | 修正参数后重试；不要盲目重试 |
| `AUTH_ERROR` | 缺少/无效鉴权信息（JWT 不合法、缺少 `X-Tenant-Id/X-Project-Id`） | `false` | 重新登录/补齐请求头；检查租户/项目上下文 |
| `FORBIDDEN` | RBAC 拒绝（缺少 capability） | `false` | 引导用户申请权限/切换角色；不要自动重试 |
| `NOT_FOUND` | 资源不存在（例如查询不存在的实体） | `false` | 提示用户检查 ID/筛选条件 |
| `UPSTREAM_TIMEOUT` | 上游服务请求超时（ERP/MES/OT 查询） | `true` | 适度重试（指数退避）；必要时降级展示缓存/最近一次结果 |
| `UPSTREAM_UNAVAILABLE` | 上游服务不可用/网络隔离不可达 | `true` | 提示稍后重试；触发告警与运维排查 |
| `CONTRACT_VIOLATION` | 上游返回不符合契约（字段缺失/类型不匹配） | `false` | 记录 requestId 并上报；不要自动重试 |
| `GUARDRAIL_BLOCKED` | 触发红线/物理边界/安全策略阻断（写操作或越界） | `false` | 提示用户原因与合规流程；必要时走审批 |
| `EVIDENCE_MISSING` | 数值结论缺少可追溯证据（Evidence 缺失） | `false` | 降级为“仅展示数据与来源”；提示用户补充证据 |
| `EVIDENCE_MISMATCH` | 证据与结论不一致（口径/时间范围/来源不匹配） | `false` | 降级并提示用户；记录 requestId 便于审计 |
| `INTERNAL_ERROR` | 未捕获异常/系统错误 | `false` | 提示用户稍后重试；携带 requestId 报障 |

### 2.2 错误处理验收点
- 任意接口失败时均返回 ErrorResponse 结构（非裸字符串）。
- `message` 英文且可用于日志检索。
- `requestId` 必须存在且与审计事件可关联。

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

### 3.2 Evidence 验收点
- 数值结论必须能关联至少一个 Evidence。
- 证据缺失/不可验证必须触发降级提示，禁止伪造证据。

## 4. Audit Event（审计事件）对外契约要点

### 4.1 审计事件类型
- `query`
- `tool_call`
- `approval`
- `write_operation`

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

### 6.1 SSE：`GET /api/v1/chat/stream`

用途：对话流式输出（长耗时场景优先 SSE）。

#### 6.1.1 协议与序列化规则（强制）
- 响应 `Content-Type`：`text/event-stream`
- 每条 SSE 事件的 `data:` 必须为**单行 JSON**（禁止多行 JSON），便于客户端稳定解析。
- 事件类型通过 JSON 字段 `type` 区分（不依赖 SSE 的 `event:` 行）。

#### 6.1.2 SSE 统一 Envelope（强制）

所有事件同形，统一 envelope 字段如下：

- `type`（string，强制）：事件类型枚举，见 6.1.3
- `timestamp`（string，强制）：ISO 8601 时间戳
- `requestId`（string，强制）：链路追踪 ID
- `tenantId`（string，强制）：租户隔离 ID
- `projectId`（string，强制）：项目隔离 ID
- `sessionId`（string，可选）：对话会话 ID（若有）
- `sequence`（number，强制）：单 SSE 连接内单调递增（从 1 开始或从任意正整数开始均可；但必须递增）
- `payload`（object，强制）：事件负载，与 `type` 对应

约束：
- 禁止在 `payload` 内重复输出 `requestId/tenantId/projectId/sessionId/sequence/timestamp/type`。
- 禁止输出无法被 JSON 解析的值（例如 `NaN`/`Infinity`）。

#### 6.1.3 最小事件类型集合（验收必需）

- `meta`：元信息（首事件必须为 `meta`）
- `progress`：阶段/步骤进度
- `tool.call`：工具调用开始（参数必须脱敏摘要）
- `tool.result`：工具调用结束（摘要 + 可选错误 + 可选 evidence 引用）
- `message.delta`：assistant 文本增量
- `evidence.update`：证据链增量（append/update/reference）
- `warning`：非致命降级/不确定项提示
- `error`：结构化错误（payload 必须同构 ErrorResponse）
- `final`：结束事件（正常/错误/取消）

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
- `evidence`（object，可选）：Evidence 对象（见第 3 章 Evidence）
- `evidenceId`（string，可选）：证据引用 ID

约束：
- `mode=append|update`：必须包含 `evidence`
- `mode=reference`：必须包含 `evidenceId`

##### `warning.payload`
- `code`（string，强制）：稳定码（推荐复用错误码：`EVIDENCE_MISSING`/`EVIDENCE_MISMATCH`/`GUARDRAIL_BLOCKED` 等，或扩展为 warning 专用枚举）
- `message`（string，强制）：面向用户的提示（允许中文）
- `details`（object，可选）：结构化上下文（禁止敏感信息）

约束：
- `warning` 不要求英文 `messageEn`；英文可检索能力由 `code` + 结构化日志字段保障。

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

#### 6.1.5 事件序列验收（最小序列，强制）

- 成功路径：`meta` ->（0..n 条任意事件）-> `final(status=success)`
- 失败路径：`meta` ->（0..n 条任意事件）-> `error` -> `final(status=error)`

约束：
- `meta` 必须为首事件。
- `final` 必须为最后一个事件；`final` 之后不得再输出任何事件。
- 发生错误时必须尽快输出 `error`，并紧随 `final(status=error)` 结束。
- `sequence` 在同一 SSE 连接内必须单调递增。

验收点：
- `error` 事件可解析为统一错误模型。
- 客户端取消（断开连接）需能向下传播，至少验证“服务端停止继续输出/停止后续工具调用”。
- 必须提供 SSE 端到端取证材料（抓包/录屏 + 事件样例），用于证明分段渲染、结构化错误、取消传播均满足口径。

### 6.2 WebSocket：`/ws/chat`
- 消息必须是 JSON 事件，建议最小事件集合与 SSE 对齐：
  - `meta`、`delta`、`tool_call`、`evidence`、`error`、`done`

验收点：
- 支持双向：客户端可发送 `cancel` 事件请求取消。
- 客户端取消需能向下传播，至少验证“服务端停止继续输出/停止后续工具调用”。
- 必须提供 WebSocket 端到端取证材料（抓包/录屏 + 事件样例），用于证明分段渲染、结构化错误、取消传播均满足口径。

## 7. 审计检索接口（验收必需）

### 7.1 `GET /api/v1/audit/events`
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
