# T18 健康检查与运行态自检执行蓝图
本计划以仓库现有实现为基线，固化 `GET /api/v1/health` 的对外契约、依赖探测与聚合策略，并定义单元测试与冒烟测试的验收口径，服务于发布门禁与可观测性。

## 0. 权威来源与“以谁为准”
- **对外契约底线**：`docs/contracts/api-and-events-draft.md` 的 `GET /api/v1/health` 小节（状态码策略/敏感信息边界/验收要点）。
- **OpenAPI 声明**：`docs/api/openapi.yaml` 的 `/api/v1/health` 与 `HealthResponse`/`ErrorResponse` schema。
- **实际路由与行为**：
  - `backend/gangqing/api/health.py`
  - `backend/gangqing/common/healthcheck.py`
  - `backend/gangqing/common/context.py`
- **验证口径（必须跑通）**：
  - Smoke：`backend/scripts/start_server_and_healthcheck.py`
  - Unit：`backend/tests/test_fastapi_skeleton.py`（健康检查相关用例）

> 规划原则：若出现“契约文档 / OpenAPI / 代码实现”不一致，优先保证 **契约文档 + 自动化测试断言** 一致，再推动 OpenAPI 与实现对齐。

## 1. 现状盘点（基于当前已实现代码）
### 1.1 鉴权策略（结论）
- **当前实现：不鉴权（内网探针）**。
  - `/api/v1/health` 通过 `build_request_context` 强制校验 scope headers（`X-Tenant-Id`/`X-Project-Id`）。
  - 不要求 `Authorization`，也不做 RBAC capability 校验。

### 1.2 已实现的核心能力（与任务目标对齐）
- **端点**：`GET /api/v1/health` 已存在。
- **状态枚举**：overall `healthy | degraded | unhealthy` 已存在。
- **依赖探测**：已覆盖并输出依赖列表（至少 `config/postgres/llama_cpp/provider/model`）。
- **状态码策略**：overall `unhealthy` 时返回 `503`，否则 `200`（与契约一致）。
- **敏感信息边界**：单元测试中已显式断言不泄露连接串/密钥等片段（必须保持）。
- **可观测性**：冒烟脚本断言结构化日志中可以按 `requestId` 检索到 `event=http_request`。

## 2. 对外契约（Schema First：以 Pydantic 为单一事实源）
### 2.1 请求：Headers
- **必需**：
  - `X-Tenant-Id: string`
  - `X-Project-Id: string`
- **可选**：
  - `X-Request-Id: string`（若缺失，服务端生成）
  - 其余上下文字段（例如 `X-Session-Id`）对 healthcheck 非强制

### 2.2 响应：成功/降级/不可用（HealthResponse）
- **HTTP 200**：overall `healthy` 或 `degraded`
- **HTTP 503**：overall `unhealthy`
- **响应头**：
  - `X-Request-Id` 必须返回，且与 body 的 `requestId` 一致

#### HealthResponse 字段（与 OpenAPI/契约保持一致）
- `status`: `healthy | degraded | unhealthy`
- `requestId`: string
- `version`:
  - `service`: string
  - `apiVersion`: string（固定为 `v1`）
  - `build`: string
  - `commit`: string
  - `startedAt`: ISO 8601 string（UTC）
- `dependencies[]`: array of `HealthDependency`

#### HealthDependency 字段
- `name`: `config | postgres | llama_cpp | provider | model`
- `status`: `ok | degraded | unavailable`
- `critical`: boolean
- `latencyMs?`: number | null
- `checkedAt`: ISO 8601 string（UTC）
- `details?`（结构化摘要，不含敏感信息）
  - `reason?`: string（稳定原因枚举/字符串）
  - `errorClass?`: string | null
  - `missingKeys?`: string[] | null（只允许 key 名，不允许 value）

### 2.3 响应：错误（ErrorResponse）
- **错误触发场景（本任务最小集合）**：
  - 缺少 `X-Tenant-Id` 或 `X-Project-Id` => HTTP `401`，`ErrorResponse.code=AUTH_ERROR`
- **ErrorResponse 字段（仅允许这些字段对外输出）**：
  - `code`: string
  - `message`: string（**必须英文**）
  - `details?`: object | null（禁止敏感信息）
  - `retryable`: boolean
  - `requestId`: string

## 3. 依赖探测策略（最小代价 + 可扩展 + 不泄露敏感信息）
### 3.1 关键配置完整性（dependency: config，critical=true）
- **目标**：在不访问外部依赖的情况下，快速判断关键配置是否齐全。
- **关键配置集合（当前实现口径）**：
  - 必需：`GANGQING_DATABASE_URL`
  - 必需（二选一）：`GANGQING_LLAMACPP_BASE_URL` 或 `GANGQING_PROVIDER_HEALTHCHECK_URL`
- **缺失策略**：
  - `config.status=unavailable`，`details.missingKeys` 返回缺失 key 名列表
  - `details.reason`：
    - 默认 `not_configured`
    - 若“模型提供者二选一”都缺失 => `not_configured_model_provider_required`

### 3.2 Postgres（dependency: postgres，critical=true）
- **探测方式**：连接可用性 + 最小查询（`SELECT 1`）。
- **超时策略**：由 `GANGQING_HEALTHCHECK_POSTGRES_CONNECT_TIMEOUT_SECONDS` 控制（秒）。
- **失败映射**：
  - 未配置 DB URL => `reason=not_configured`
  - 连接失败/认证失败/网络失败 => `reason=connection_failed`，`errorClass` 填异常类型名
- **敏感信息边界**：对外 `details` 绝不包含连接串、用户名、host/port 组合、堆栈。

### 3.3 llama.cpp（dependency: llama_cpp，critical 可配置）
- **探测方式**：HTTP GET health endpoint（支持兼容 `/v1` 前缀候选）。
- **超时策略**：`GANGQING_LLAMACPP_TIMEOUT_SECONDS`（秒），多候选 URL 时按候选数均分（避免总耗时过长）。
- **失败映射**：
  - 未配置 base_url => `reason=not_configured`
  - 超时 => `reason=timeout` + `errorClass`
  - 非 2xx => `reason=unexpected_response`
  - 连接失败 => `reason=connection_failed` + `errorClass`
- **鉴权与敏感信息**：
  - 可携带 `GANGQING_LLAMACPP_API_KEY` 发起探测，但 **不得**在对外响应/日志中打印其值。

### 3.4 Provider（dependency: provider，critical=false）
- **探测方式**：HTTP GET `GANGQING_PROVIDER_HEALTHCHECK_URL`。
- **超时策略**：`GANGQING_PROVIDER_TIMEOUT_SECONDS`。
- **失败映射**：同 llama.cpp（`not_configured/timeout/unexpected_response/connection_failed`）。

### 3.5 Model 聚合（dependency: model，critical=true）
- **语义**：只要 `llama_cpp` 或 `provider` 任意一个 `status=ok`，则 `model.status=ok`；否则 `model.status=unavailable`，`reason=no_model_provider_online`。
- **目的**：将“可用模型后端”抽象成一个关键依赖，便于发布门禁与告警。

## 4. 状态聚合矩阵（healthy / degraded / unhealthy）
### 4.1 Overall 状态规则（与当前实现一致）
- **unhealthy**：存在任意 `critical=true` 的依赖 `status=unavailable`
- **degraded**：
  - 任意依赖 `status=degraded`，或
  - 存在任意 `critical=false` 的依赖 `status=unavailable`
- **healthy**：以上都不满足

### 4.2 HTTP 状态码规则
- overall `unhealthy` => HTTP `503`
- overall `healthy|degraded` => HTTP `200`

## 5. 缓存策略（高频探针降压）
- 配置：`GANGQING_HEALTHCHECK_CACHE_TTL_SECONDS`
- 规则：
  - TTL <= 0：不缓存
  - **只缓存** `healthy/degraded`
  - **不缓存** `unhealthy`（确保故障可被及时探测与告警）

## 6. 安全与敏感信息边界（强制）
### 6.1 对外响应禁止泄露
- 连接串：`postgresql://`、`psycopg://`
- 任何密码/secret/token（含形如 `sk-`、`nvapi-` 的片段）
- 内部异常堆栈、上游响应正文
- 过度内部细节（例如把内部网络拓扑/完整 host:port 组合直接返回给外部）

### 6.2 允许对外返回的信息
- 缺失配置：仅允许返回缺失的 **key 名**（`missingKeys`）
- 错误类型：仅允许异常类名（`errorClass`）
- 稳定原因：`reason`（稳定枚举/字符串）

## 7. 可观测性与日志要求（发布门禁）
- 每次 `/api/v1/health` 请求必须产出可解析的结构化日志（至少包含）：
  - `event=http_request`
  - `requestId`
  - `tenantId`、`projectId`
  - `statusCode`
  - `latencyMs`
- 健康探测过程建议额外记录（结构化字段即可）：
  - `event=healthcheck` 或 `event=health_probes`
  - overall 状态与依赖状态摘要（禁止敏感信息）

## 8. 配置项清单（以 .env.example 为准，不新增即可验收）
### 8.1 必需（缺失应导致系统整体 unhealthy 或测试失败）
- `GANGQING_DATABASE_URL`
- `GANGQING_LLAMACPP_BASE_URL` 或 `GANGQING_PROVIDER_HEALTHCHECK_URL`

### 8.2 可选（但一旦设置必须可解析且生效）
- `GANGQING_HEALTHCHECK_POSTGRES_CONNECT_TIMEOUT_SECONDS`
- `GANGQING_HEALTHCHECK_CACHE_TTL_SECONDS`
- `GANGQING_LLAMACPP_HEALTH_PATH`
- `GANGQING_LLAMACPP_TIMEOUT_SECONDS`
- `GANGQING_LLAMACPP_TRUST_ENV`
- `GANGQING_LLAMACPP_CRITICAL`
- `GANGQING_PROVIDER_TIMEOUT_SECONDS`
- `GANGQING_PROVIDER_TRUST_ENV`
- `GANGQING_SERVICE_NAME` / `GANGQING_BUILD` / `GANGQING_COMMIT`

## 9. 交付物与改动范围（规划层面：改哪些文件）
> 本阶段不实现代码，仅定义“实现时需要改哪些文件/改动点是什么”。

### 9.1 若需要对齐契约/实现/测试，可能涉及修改的文件
- **后端路由/响应**：`backend/gangqing/api/health.py`
- **依赖探测/聚合模型**：`backend/gangqing/common/healthcheck.py`
- **上下文与错误**：`backend/gangqing/common/context.py`（缺 header => `AUTH_ERROR`）
- **契约文档**：`docs/contracts/api-and-events-draft.md`（仅当发现不一致时）
- **OpenAPI**：`docs/api/openapi.yaml`（以 schema/响应为准）
- **配置示例**：`.env.example`（仅当新增/修正配置项时）
- **冒烟脚本**：`backend/scripts/start_server_and_healthcheck.py`
- **单元测试**：`backend/tests/test_fastapi_skeleton.py`

## 10. 验收口径（必须自动化）
### 10.1 Unit（pytest）必须覆盖的最小集合
- `/api/v1/health` 成功返回（HTTP `200|503` 皆可，但 body 必须满足 schema）
- 缺少 `X-Tenant-Id` => `401` + `ErrorResponse(code=AUTH_ERROR)`（`message` 英文）
- 缺少 `X-Project-Id` => `401` + `ErrorResponse(code=AUTH_ERROR)`（`message` 英文）
- 缺失关键配置（例如缺 DB URL / 无模型 provider）=> overall `503` + `status=unhealthy`
- llama.cpp/provider 超时：`details.reason=timeout` 且 `errorClass` 有值
- `X-Request-Id` 透传与生成：
  - 未提供时服务端生成并回传
  - 提供时响应头/响应体回显一致
- 敏感信息不泄露：对响应 JSON 做 forbidden fragments 扫描（保持现有断言强度）

### 10.2 Smoke（真实启动 + 真实依赖）必须覆盖的最小集合
- 启动 FastAPI（uvicorn factory）并等待端口就绪
- 调用 `/api/v1/health`：
  - status 允许 `200|503`
  - body `requestId` 与请求头一致（脚本固定 requestId）
  - dependencies 必含 `config/postgres/llama_cpp/provider/model`
- 失败路径：缺 `X-Tenant-Id` => 必须是 `401` 且响应体为 `ErrorResponse`
- 日志可检索：stdout 中必须出现 `event=http_request` 且 `requestId` 匹配
- 成功标志：脚本输出 `healthcheck_ok`

## 11. 风险点与约束（用于实施阶段提前规避）
- **探针头部要求**：必须携带 `X-Tenant-Id/X-Project-Id`，否则 401（运维侧需配置 readiness/liveness probe 或网关探针 headers）。
- **敏感信息红线**：任何对外字段扩展都要先过“禁止 key/片段”审查与测试覆盖。
- **超时与探测成本**：健康检查必须在可控时间内完成（多候选 URL 时均分超时是必要手段）。

