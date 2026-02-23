# Task 18：健康检查与运行态自检（T18）执行蓝图

本计划定义 `GET /api/v1/health` 的对外契约（Pydantic 单一事实源）、依赖探测策略（Postgres/llama.cpp/关键配置）与验收口径，并明确安全边界与可观测性要求。

## 0. 权威参考与约束来源

- PRD：`docs/requirements.md`（R12.3）
- TDD：`docs/design.md`（2.9、6.* 错误模型）
- 契约：`docs/contracts/api-and-events-draft.md`（统一 ErrorResponse、Header/RequestContext 规则）
- OpenAPI：`docs/api/openapi.yaml`
- 现状实现：
  - 端点：`backend/gangqing/api/health.py`
  - RequestContext：`backend/gangqing/common/context.py`
  - ErrorResponse/AppError：`backend/gangqing/common/errors.py`
  - 设置加载：`backend/gangqing/common/settings.py`、`backend/gangqing_db/settings.py`
  - 冒烟：`backend/scripts/start_server_and_healthcheck.py`
  - 基础测试：`backend/tests/test_fastapi_skeleton.py`

强制规则（摘录）：
- Schema First：后端对外 I/O 必须以 Pydantic 为单一事实源。
- 配置外部化 + 配置校验：关键配置缺失必须快速失败；对外错误 `message` 必须英文。
- 结构化错误：`code` + `message` + `requestId` + `retryable` + `details?`，且 **仅允许**这 5 个字段。
- 可观测性：结构化日志必须可按 `requestId` 检索。
- 安全：健康检查不得泄露密钥/连接串/内部栈信息。

## 1. 现状盘点与差距（Gap）

### 1.1 现状
- `/api/v1/health` 已存在（`backend/gangqing/api/health.py`），在 `create_api_router()` 中全局依赖 `build_request_context`，因此默认 **要求** `X-Tenant-Id` + `X-Project-Id`。
- 现有响应：
  - `status`: `healthy|degraded|unhealthy`（字符串）
  - `dependencies.postgres.status`: `skipped|ok|unavailable`
- Postgres 探测方式：基于 `GANGQING_DATABASE_URL`，执行 `SELECT 1`。
- 现状未覆盖：
  - llama.cpp 依赖探测（现仓库暂无 llama.cpp 配置/适配器实现线索）
  - 版本/构建信息输出
  - 关键配置完整性“明确契约化字段”（例如哪些配置算关键、缺失如何映射为 degraded/unhealthy）
  - OpenAPI 中 `/api/v1/health` 目前是“任意 object<string,string>”的弱 schema，需要对齐。

### 1.2 差距与改造目标
- **契约增强**：健康检查响应必须可用于告警/门禁（稳定字段 + 稳定枚举 + 依赖列表）。
- **依赖探测扩展**：覆盖 Postgres + llama.cpp + 关键配置完整性。
- **敏感信息边界**：响应体与错误 details 不得包含连接串、用户名、host、栈等敏感细节；必要细节仅进结构化日志（也需脱敏）。
- **验收可自动化**：单元测试 + 真实依赖冒烟测试（no-skip）。

## 2. 对外契约（Schema First / Pydantic 单一事实源）

> 说明：以下为“字段定义与约束”，不包含任何实现代码。

### 2.1 请求（Headers）
- **必填**（与当前全局 `build_request_context` 一致）：
  - `X-Tenant-Id: string`
  - `X-Project-Id: string`
- **可选**：
  - `X-Request-Id: string`（透传；缺失则服务端生成并在响应头 `X-Request-Id` 回传）

鉴权（RBAC）策略（需决策，见 6.1）：
- 方案 A：不要求 `Authorization`（对内探针开放），但仍保留 `X-Tenant-Id/X-Project-Id` 以满足隔离不变式与日志关联。
- 方案 B：要求 `Authorization`（对外暴露时更安全），并记录审计（health 属于低敏但高频接口）。

### 2.2 成功响应：`HealthResponse`（HTTP 200/503）

#### 2.2.1 顶层字段
- `status`: 枚举字符串
  - `healthy`：所有关键依赖 OK，关键配置完整
  - `degraded`：至少一个**非关键**依赖不可用/未配置，或存在可降级能力（系统可服务但需要告警）
  - `unhealthy`：至少一个**关键**依赖不可用，或关键配置缺失，系统不应接流量
- `requestId`: string
  - **注意**：当前 `HealthResponse` 里没有 `requestId`；本任务要求对外契约包含 requestId（你在任务描述里也要求“输出（…、requestId）”）。
  - 约束：同时在响应头回传 `X-Request-Id`。
- `version`: object
  - `service`: string（固定：`gangqing-api` 或同等稳定标识）
  - `apiVersion`: string（例如 `v1`，与路由前缀一致）
  - `build`: string（建议来自环境变量/CI 注入，避免硬编码）
  - `commit`: string（建议来自环境变量/CI 注入）
  - `startedAt`: string（ISO 8601）
- `dependencies`: array（而非 dict，便于扩展与排序稳定）

#### 2.2.2 依赖对象：`HealthDependency`
- `name`: 枚举字符串（最小集合）
  - `postgres`
  - `llama_cpp`
  - `config`
- `status`: 枚举字符串
  - `ok`
  - `degraded`
  - `unavailable`
- `critical`: boolean
  - true 表示该依赖失败将导致整体 `unhealthy`
- `latencyMs`: number | null
  - 探测耗时；失败也尽量填（若有）
- `checkedAt`: string（ISO 8601）
- `details`: object | null（严格脱敏）
  - 仅允许：
    - `reason`: `not_configured|timeout|connection_failed|unexpected_response|validation_failed|unknown`
    - `errorClass`: string（仅类名，不含堆栈）
    - `missingKeys`: string[]（仅配置 key 名称，不含值）
  - 禁止：
    - 连接串、host、用户名、token、堆栈、SQL、上游响应原文

### 2.3 失败响应：`ErrorResponse`（结构化错误，英文 message）

健康检查的“失败”分两类：
- **协议/鉴权/头部缺失导致的失败**：返回 `ErrorResponse`（HTTP 401/403/400/422 等），沿用全局异常处理器。
- **依赖不可用导致的不健康**：仍返回 `HealthResponse`，但 HTTP 状态码可为 `503`（推荐）以便探针/告警系统直接识别。

错误模型字段必须严格为：
- `code`
- `message`（英文）
- `details?`
- `retryable`
- `requestId`

## 3. 依赖探测策略（Postgres / llama.cpp / 关键配置完整性）

### 3.1 总体策略原则
- **最小代价**：每个依赖探测都必须是轻量级。
- **硬超时**：所有探测必须有明确超时（来自配置），防止 health 卡住。
- **不泄露**：对外 details 严格脱敏；可观测性靠结构化日志与审计（按需）。
- **可扩展**：后续新增依赖仅需新增一个探测器并注册到聚合逻辑。

### 3.2 Postgres 探测
- 输入配置：`GANGQING_DATABASE_URL`
- 探测：
  - 建立连接 + `SELECT 1`
  - `pool_pre_ping` 可保留
- 状态映射：
  - URL 缺失/空字符串：
    - 若 Postgres 是 **关键依赖**（L1 默认应该是关键）：整体 `unhealthy`；`dependencies.postgres.status=unavailable`，details.reason=`not_configured`
  - 连接失败/认证失败：`unavailable`
  - 超时：`unavailable` + reason=`timeout`（错误码在对外响应中不直接暴露，靠 details.reason）

### 3.3 llama.cpp 探测（HTTP 就绪性）

仓库当前未出现 llama.cpp 配置字段，因此本任务需要先把“探测目标”配置化并校验。

- 新增关键配置（建议放在 `backend/gangqing/common/settings.py`）：
  - `GANGQING_LLAMACPP_BASE_URL`（例如 `http://127.0.0.1:8080`）
  - `GANGQING_LLAMACPP_HEALTH_PATH`（默认 `/health` 或 `/v1/models`，需与实际 llama.cpp 部署对齐）
  - `GANGQING_LLAMACPP_TIMEOUT_SECONDS`（默认 0.5~2.0；按运维需求）
- 探测方式：HTTP GET
  - 成功条件：HTTP 200 且响应可解析（不要求返回体固定字段，避免依赖上游版本差异）；失败条件：非 2xx、超时、DNS/连接失败。
- 状态映射：
  - 未配置 base_url：
    - 若模型能力对外服务是关键（多数情况下是关键）：整体 `unhealthy`
    - 若允许“无模型降级”（仅提供部分静态/数据库能力）：整体 `degraded`
  - 连接/超时：`unavailable`
  - 非预期响应：`degraded` 或 `unavailable`（建议按是否可降级决定）

> 需要你确认：L1 阶段是否允许“llama.cpp 不可用但系统仍可提供部分只读数据 API/语义 API”？（见 6.2 决策项）

### 3.4 关键配置完整性探测（config 依赖）

目标：把“启动期快速失败”的配置校验，补充为“运行态可观测的配置缺失快照”。

- 建议规则：
  - **启动期**：关键配置缺失直接启动失败（这属于 create_app/load_settings 范畴，非 health 端点本身）。
  - **运行态**：health 返回 `dependencies.config`，列出缺失 key 名称（不含值），用于排查。
- 最小关键配置集合（建议）：
  - `GANGQING_DATABASE_URL`
  - `GANGQING_JWT_SECRET`（若 health 要求鉴权则为关键；不鉴权可降级为非关键，但仍建议校验以避免服务处于不可登录状态）
  - `GANGQING_LLAMACPP_BASE_URL`（若 llama.cpp 为关键依赖）
- `dependencies.config.details.missingKeys`: string[]

## 4. overall 状态判定矩阵（healthy / degraded / unhealthy）

### 4.1 关键性（critical）建议
- `postgres`: critical=true
- `config`: critical=true（缺关键配置即不应对外服务）
- `llama_cpp`: critical（默认 true；若你明确允许“无模型降级”，则 critical=false）

### 4.2 判定规则（推荐）
- 若任一 `critical=true` 的依赖为 `unavailable`：
  - overall=`unhealthy`
  - HTTP=503
- 否则若存在任一依赖为 `degraded` 或存在非关键依赖 `unavailable`：
  - overall=`degraded`
  - HTTP=200（或 207；但建议保持 200 以兼容探针，告警由 body.status + 依赖项判断）
- 否则：
  - overall=`healthy`
  - HTTP=200

## 5. 可观测性与安全边界

### 5.1 requestId 贯穿
- 入口：`X-Request-Id` 透传；缺失则生成。
- 输出：
  - 响应头 `X-Request-Id`
  - 响应体 `requestId`
  - 结构化日志 `event=http_request` 必含 `requestId/tenantId/projectId`

### 5.2 结构化日志字段（health 专用建议）
- `event`: `healthcheck`
- `requestId` / `tenantId` / `projectId`
- `overallStatus`
- `dependencies`: 仅记录状态与耗时（不得记录连接串/密钥）
- `durationMs`

### 5.3 敏感信息红线
- 对外响应与 ErrorResponse.details：禁止任何 secret/连接串/内部堆栈。
- 对内日志：也必须脱敏（只允许记录配置 key 名、错误类名、reason、耗时）。

## 6. 关键决策点

### 6.1 健康检查是否需要鉴权？
- 不要求 `Authorization`，仅要求 `X-Tenant-Id/X-Project-Id`。
  - 理由：
    - 运维探针通常不易携带 JWT；health 高频且应尽量稳定。
    - 仍通过 tenant/project 维度满足隔离与日志关联。
  - 风险：若对公网暴露，可能泄露“系统是否在线”的元信息；但我们已严格脱敏且不暴露拓扑细节。


### 6.2 llama.cpp 不可用时是否允许降级？

- 允许降级（仅数据 API/语义 API 可用，但 chat/stream 不可用），则 health：
  - overall=`degraded`
  - `dependencies.llama_cpp.critical=false`

## 7. 需要修改/对齐的文件清单（仅列现存路径）

- 后端 API：
  - `backend/gangqing/api/health.py`：
    - 统一响应 schema（新增 requestId/version/dependencies 数组等）
    - 增加 llama.cpp/config 探测器
    - overall 状态与 HTTP 状态码映射
- 配置：
  - `backend/gangqing/common/settings.py`：新增 llama.cpp 探测相关配置项 + 校验（英文错误信息）
  - `.env.example`：补齐新增 ENV（若引入）
- 文档/契约：
  - `docs/api/openapi.yaml`：将 `/api/v1/health` 的 response schema 从弱对象改为明确 schema（可引用 Pydantic 生成的 OpenAPI 组件）
  - `docs/contracts/api-and-events-draft.md`：若需要新增错误码或补充 health 约束，则在此补齐（确保错误码枚举完整）
- 测试与冒烟：
  - `backend/tests/`：新增 health 契约相关单测（见 8.1）
  - `backend/scripts/start_server_and_healthcheck.py`：
    - 调整请求头与断言，以对齐新的 health 响应契约与状态码规则

## 8. 验收口径（必须可自动化、No Skip、真实依赖）

### 8.1 单元测试（pytest）验收点（建议最小集合）
- **契约字段完整性**：`HealthResponse` 顶层字段与依赖数组字段齐全、枚举值合法。
- **requestId 规则**：
  - 缺失 `X-Request-Id` 时生成并回传（header + body 一致）。
  - 提供 `X-Request-Id` 时透传。
- **头部缺失错误**：缺 `X-Tenant-Id`/`X-Project-Id` 返回 `ErrorResponse` 且仅 5 字段，`message` 英文。
- **Postgres 未配置/不可用**：根据“是否关键依赖”映射到 degraded/unhealthy，并验证 HTTP 状态码（200/503）。
- **llama.cpp 未配置/不可用**：同上（按你在 6.2 的决策）。
- **敏感信息不泄露**：断言响应体不包含 `postgresql://`、`password`、`secret` 等敏感片段（白盒字符串扫描）。

> 注：集成/冒烟必须连真实依赖；单元测试可通过“依赖注入”形式提供可控的探测器实现，但不得用 mock 隐藏真实失败模式。

### 8.2 冒烟测试（真实服务）
- 命令：`python backend/scripts/start_server_and_healthcheck.py`
- 必须满足：
  - 能真实启动 FastAPI 并请求 `/api/v1/health`
  - 响应可解析且 `requestId` 可在结构化日志 `event=http_request` 中检索到
  - 若配置缺失或依赖不可用：冒烟应 **失败**（exit code != 0），不得 skip
- 建议扩展（至少新增 1 个失败路径）：
  - 例如：不传 `X-Tenant-Id`，断言返回 `AUTH_ERROR` 且 `requestId` 与响应头一致

## 9. 里程碑拆分（Task 18.1~18.3）

### 9.1 Task 18.1：端点与响应模型
- 产出：Pydantic `HealthResponse`/`HealthDependency`/`VersionInfo`（或等价）
- OpenAPI 对齐：`docs/api/openapi.yaml` 更新 `/api/v1/health`

### 9.2 Task 18.2：依赖探测与聚合
- 产出：Postgres + config + llama.cpp 探测器 + overall 判定矩阵
- 产出：结构化日志字段约定与脱敏边界

### 9.3 Task 18.3：冒烟脚本对齐
- 产出：`backend/scripts/start_server_and_healthcheck.py` 对齐新契约
- 冒烟覆盖：成功路径 + 失败路径（no-skip）

## 10. 计划完成定义（DoD）

- `/api/v1/health`：
  - 能区分 `healthy/degraded/unhealthy`
  - 依赖项覆盖 Postgres/llama.cpp/config
  - 不泄露敏感信息
  - `requestId` 贯穿（header + body + logs）
- OpenAPI/契约文档对齐
- 单元测试通过：`pytest -q`
- 冒烟测试通过：`python backend/scripts/start_server_and_healthcheck.py`
