### Task 18 - 健康检查与运行态自检（依赖状态/降级态/版本信息）（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 18 号任务：健康检查与运行态自检（依赖状态/降级态/版本信息）。
你的角色是 **技术负责人/架构师**。
你的目标是制定 Task 18 的详细执行计划，并定义健康检查的对外契约、依赖探测策略与验收口径。

本任务面向运维可观测性与发布门禁：
- 对外提供 `GET /api/v1/health` 作为探针端点。
- 具备依赖状态探测（Postgres / llama.cpp / 关键配置完整性）。
- 支持区分 `healthy`/`degraded`/`unhealthy`，便于告警与降级。
- 不泄露敏感信息（密钥/连接串/内部栈信息）。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 本阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 只输出“怎么做、分几步、改哪些文件、契约长什么样、怎么验收”。
- **Schema First（强制）**:
  - 后端对外 I/O 使用 Pydantic 作为单一事实源（健康检查响应/错误模型）。
- **配置校验（强制）**: 关键配置缺失必须快速失败，返回结构化错误；其中 `message` 必须为英文。
- **结构化错误（强制）**: 对外错误响应必须结构化：`code` + `message` + `requestId` + `retryable` + `details?`。
- **RBAC & Audit（按需）**:
  - 若健康检查端点需要鉴权，则必须遵循 RBAC，并记录审计/结构化日志；`requestId` 必须贯穿。
  - 若健康检查端点对内网探针开放且不鉴权，也必须做到：不泄露敏感信息 + 结构化日志可定位。
- **配置外部化（强制）**: 禁止硬编码 URL/端口/超时等；必须来自环境变量并被校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实依赖；缺配置/依赖不可用必须导致测试失败（不得 skip）。

# References
- PRD: docs/requirements.md（R12.3）
- TDD: docs/design.md（2.9, 6.1, 7.x）
- tasks: docs/tasks.md（任务 18）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# 权威参考文档/约束来源（强制）
- docs/contracts/api-and-events-draft.md（以其中 `GET /api/v1/health` 小节为准；含状态码策略/敏感信息边界/验收要点）
- docs/api/openapi.yaml（以 `/api/v1/health` 的 responses 与 `HealthResponse`/`ErrorResponse` schema 为准）
- backend/gangqing/api/health.py（以实际路由与状态码策略为准）
- backend/gangqing/common/healthcheck.py（以依赖探测与状态聚合逻辑为准）
- backend/gangqing/common/context.py（以 scope headers 要求与 requestId 生成/透传规则为准）
- backend/scripts/start_server_and_healthcheck.py（以冒烟脚本断言为准）
- backend/tests/test_fastapi_skeleton.py（以单元测试覆盖面与断言为准）

# Execution Plan
1) Task 18.1（健康检查端点与响应模型）
- Goal:
  - 明确 `GET /api/v1/health` 的输入（headers）与输出（状态枚举、依赖列表、版本信息、requestId）。
  - 定义 `degraded`/`unhealthy` 判定口径与可扩展字段。
- Key Decisions:
  - 响应模型字段与敏感信息边界（哪些信息可返回，哪些只能写日志）。
  - `requestId` 获取策略：从 `X-Request-Id` 透传或服务端生成。
  - 状态码策略与契约一致性：整体 `unhealthy` 必须返回 `503`，否则返回 `200`。
- Deliverables:
  - Pydantic 响应/错误模型定义。
  - `GET /api/v1/health` 在 OpenAPI 中可追溯（如本仓库以 `docs/api/openapi.yaml` 为准，则需对齐）。

2) Task 18.2（依赖探测：Postgres/llama.cpp/关键配置完整性）
- Goal:
  - 定义依赖探测接口：最小代价的连通性/就绪性校验。
  - 明确关键配置集合与缺失时的失败策略（快速失败 + 结构化错误）。
- Key Decisions:
  - Postgres 探测：连接可用性 + 最小查询（避免重负载）。
  - llama.cpp 探测：HTTP 可用性 + 超时与错误映射（`UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT`）。
  - “依赖失败 => 系统状态”映射矩阵（healthy/degraded/unhealthy）。
- Deliverables:
  - 依赖探测函数与统一聚合逻辑（可扩展更多依赖）。
  - 结构化日志字段约定（至少包含 `requestId`、依赖名、耗时、结果）。

3) Task 18.3（冒烟脚本对齐）
- Goal:
  - 以“真实启动 FastAPI 并调用 `/api/v1/health`”为主线，形成可自动化的发布门禁。
  - 冒烟覆盖：成功路径 + 至少一个失败路径（例如缺少 header 或缺少关键配置）。
- Deliverables:
  - `backend/scripts/start_server_and_healthcheck.py`（对齐最新契约与日志断言；若已存在则只允许做“对齐/补齐”，禁止扩展范围）。
  - 冒烟脚本输出与日志校验口径（例如必须能在结构化日志中找到 requestId）。

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确新增/修改的目录树（以实际改动为准，不能写不存在的路径）。
- [ ] **Environment Variables**: 明确健康检查依赖的关键 ENV 列表与校验策略（缺失即失败），并确保 `.env.example` 覆盖（如本任务涉及新增配置）。
- [ ] **API Contracts**: `GET /api/v1/health` 的响应结构、状态码、错误模型与 header 约束。
- [ ] **Error Model**: 错误码枚举与结构化错误字段要求（`message` 必须英文）。
- [ ] **Observability**: `requestId` 贯穿、关键日志字段（至少 `event=http_request` 以及 `requestId`）。
- [ ] **Security**: 明确鉴权策略与敏感信息边界（默认不泄露连接串/密钥/内部栈）。

# Verification
- Automated Tests:
  - Unit: `pytest -q`
  - Smoke: `python backend/scripts/start_server_and_healthcheck.py`
- Manual Verification:
  - 启动后端服务后，使用带必需 headers 的请求访问：`GET /api/v1/health`
  - 确认返回体中不包含密钥/连接串等敏感信息。
  - 确认服务日志中可检索到本次请求的 `requestId`（结构化字段）。

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 18.1 - 健康检查：依赖状态与 degraded/unhealthy 区分

```markdown
# Context
你正在执行子任务：18.1 - 健康检查：依赖状态与 degraded/unhealthy 区分。
目标是实现健康检查端点，返回系统与依赖的状态摘要，并可用于告警。

# Critical Rules
- **不泄露敏感信息**: 不返回密钥/连接串。
- **英文 message**。
- **Schema First**: 使用 Pydantic 定义对外响应/错误模型。
- **Structured Errors**: 对外错误必须结构化（`code`/`message`/`requestId`/`retryable`/`details?`）。
- **真实依赖**: 测试与冒烟必须连接真实服务；缺配置必须失败（不得 skip）。

# References
- tasks: docs/tasks.md（18.1）
- TDD: docs/design.md（2.9）
- contracts: docs/contracts/api-and-events-draft.md（2.2.1 `GET /api/v1/health`）
- api docs: docs/api/openapi.yaml（/api/v1/health）

# Target Files
- backend/gangqing/api/health.py
- backend/gangqing/api/router.py（确认已挂载 `/api/v1/health`）
- backend/gangqing/common/context.py（`X-Tenant-Id`/`X-Project-Id`/`X-Request-Id` 处理规则）
- backend/gangqing/common/healthcheck.py（Pydantic `HealthResponse`/依赖结构）
- backend/tests/test_fastapi_skeleton.py（健康检查相关测试与敏感信息泄露断言）
- docs/contracts/api-and-events-draft.md（若任务涉及契约补充/修正）
- docs/api/openapi.yaml（若任务涉及 OpenAPI 对齐）
- .env.example（若新增/补齐配置项）

# Execution Plan
1) 对齐契约与现状
- 以 `docs/contracts/api-and-events-draft.md` 的 `/api/v1/health` 小节为“对外契约底线”。
- 以 `docs/api/openapi.yaml` 的 `/api/v1/health` 路径为“接口声明权威来源”。
- 若发现 code/openapi/contract 三者不一致：以“对外契约文档 + 测试断言”为优先，制定对齐策略并在本子任务交付摘要中说明。

2) 定义/校验 HealthResponse 与依赖结构
- 响应体必须满足：`status`/`requestId`/`version`/`dependencies[]`。
- 依赖项必须至少包含：`config/postgres/llama_cpp/provider/model`。

3) 状态码与头部
- `X-Request-Id`：无论成功/失败都必须在响应头返回，且与 body.requestId 一致。
- overall `unhealthy` 必须返回 `503`；overall `healthy/degraded` 返回 `200`。

4) 敏感信息边界
- 响应体不得包含：DB URL、任何密钥/token、内部堆栈、上游响应正文。
- 若需要排障信息：只允许进入结构化日志，且必须脱敏。

# Contract Notes (契约要点)
- 请求头：至少需要 `X-Tenant-Id`、`X-Project-Id`；`X-Request-Id` 可选（若缺失由服务端生成）。
- 响应体：必须包含 `requestId`，并返回总体状态与依赖状态列表。
- 状态码策略：
  - `200`：总体 `healthy` 或 `degraded`
  - `503`：总体 `unhealthy`
  - `4xx`：缺少必需 headers / 鉴权失败（返回结构化错误）

# Environment Variables (契约/实现必须对齐)
- 必需：
  - `GANGQING_DATABASE_URL`
  - `GANGQING_LLAMACPP_BASE_URL` 或 `GANGQING_PROVIDER_HEALTHCHECK_URL`（至少一个）
- 可选（但一旦存在必须可被解析且影响行为可被测试）：
  - `GANGQING_HEALTHCHECK_CACHE_TTL_SECONDS`
  - `GANGQING_HEALTHCHECK_POSTGRES_CONNECT_TIMEOUT_SECONDS`
  - `GANGQING_LLAMACPP_HEALTH_PATH`
  - `GANGQING_LLAMACPP_TIMEOUT_SECONDS`
  - `GANGQING_LLAMACPP_TRUST_ENV`
  - `GANGQING_LLAMACPP_CRITICAL`
  - `GANGQING_PROVIDER_TIMEOUT_SECONDS`
  - `GANGQING_PROVIDER_TRUST_ENV`
  - `GANGQING_SERVICE_NAME` / `GANGQING_BUILD` / `GANGQING_COMMIT`（若服务端支持将其注入 version 字段）

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `python backend/scripts/start_server_and_healthcheck.py`

### Checklist（自检）
- [ ] 是否明确并实现了健康检查端点路径为 `GET /api/v1/health`？
- [ ] 是否明确并校验了必需 headers（至少 `X-Tenant-Id`、`X-Project-Id`），并对缺失返回结构化错误？
- [ ] 响应体是否包含 `requestId`，且 `requestId` 与日志/审计口径一致？
- [ ] 是否能区分 `healthy` / `degraded` / `unhealthy`（或仓库既有状态枚举），并有明确映射规则？
- [ ] 是否对外返回结构化错误（`code`/`message`/`requestId`/`retryable`/`details?`），且 `message` 为英文？
- [ ] 是否确认返回体不包含敏感信息（密钥、连接串、内部栈、主机内网细节）？
- [ ] 是否在真实依赖不可用/超时时返回可解释且稳定的错误码（例如 `UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT`）？
- [ ] 单元测试是否覆盖：成功、缺 headers、缺关键配置、依赖不可用/超时等关键路径？

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 18.2 - 依赖探测：Postgres/llama.cpp/关键配置完整性

```markdown
# Context
你正在执行子任务：18.2 - 依赖探测：Postgres/llama.cpp/关键配置完整性。
目标是把“依赖是否可用”变成可计算、可观测、可测试的结果，并与健康检查端点聚合。

# Critical Rules
- **配置外部化**: 禁止硬编码依赖地址、超时、重试次数；必须通过环境变量/统一配置加载。
- **英文 message**。
- **Structured Errors**: 缺配置/依赖不可达必须映射到稳定错误码，并能输出结构化错误（对外或至少日志）。
- **No Heavy Queries**: 探测应尽可能轻量，避免对生产依赖造成压力。

# References
- PRD: docs/requirements.md（R12.3）
- TDD: docs/design.md（2.5.1, 2.9, 6.1）
- tasks: docs/tasks.md（18.2）

# Target Files
- backend/gangqing/common/healthcheck.py（依赖探测与聚合逻辑：`probe_*`/`aggregate_overall_status`/`run_dependency_probes`）
- backend/gangqing/common/context.py（缺 scope headers 的错误码与 message 必须为英文）
- backend/gangqing/api/health.py（`503` 策略与 cache 策略）
- backend/tests/test_fastapi_skeleton.py（依赖探测相关覆盖与敏感信息泄露断言）
- backend/scripts/start_server_and_healthcheck.py（冒烟脚本对依赖项名称的硬断言，修改需同步更新脚本与契约文档）
- .env.example（若新增/补齐配置项）

# Execution Plan
1) 明确“关键配置集合”与缺失时的失败策略
- 例如：数据库 URL、llama.cpp base url、超时等。
- 缺失策略必须一致：快速失败 + 结构化错误（`code/message/requestId/retryable`）。

2) 定义依赖探测函数的统一返回结构
- 每个依赖至少输出：`name`、`status`、`latencyMs`、`error?`（错误仅输出安全摘要）。

3) 定义状态映射矩阵
- 关键依赖失败是否直接 `unhealthy`，非关键依赖失败是否 `degraded`。

4) 性能与稳定性边界
- 探测必须轻量：
  - Postgres 只允许 `SELECT 1`。
  - HTTP 探测必须有严格 timeout，避免卡住健康检查。
- 可选 cache（`GANGQING_HEALTHCHECK_CACHE_TTL_SECONDS`）：
  - 只允许缓存 `healthy/degraded`。
  - 禁止缓存 `unhealthy`。

5) 单元测试
- 覆盖：缺配置（失败）、headers 缺失（失败）、依赖不可达（失败/降级）、成功路径。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `python backend/scripts/start_server_and_healthcheck.py`

### Checklist（自检）
- [ ] 是否列出了“关键配置集合”，并且缺失时快速失败（不得降级为“返回 healthy 但提示”）？
- [ ] 是否做到配置外部化（URL/端口/超时/重试等均来自环境变量/统一配置加载），无硬编码？
- [ ] 依赖探测是否轻量（避免重查询/重操作），且有明确超时边界？
- [ ] 是否为每个依赖输出统一结构字段（如 `name/status/latencyMs/error?`），并能被健康检查聚合？
- [ ] `error`/失败摘要是否经过脱敏（不包含连接串、token、完整 host/port 细节等敏感信息）？
- [ ] 是否定义并实现了“依赖失败 => 系统状态”的映射矩阵（关键依赖 vs 非关键依赖）？
- [ ] 是否把依赖探测结果写入结构化日志（至少包含 `requestId`、依赖名、耗时、结果）？
- [ ] 单元测试是否覆盖：缺配置、依赖不可达、依赖超时、成功路径、聚合状态计算？
```

---

### Task 18.3 - 冒烟脚本对齐：启动服务 + health 探针 + 日志 requestId 断言

```markdown
# Context
你正在执行子任务：18.3 - 冒烟脚本对齐：启动服务 + health 探针 + 日志 requestId 断言。
目标是让 CI/本地可以一键验证：服务可启动、健康检查可访问、并且日志可追踪（requestId）。

# Critical Rules
- **Real Integration (No Skip)**: 必须连接真实 FastAPI + 真实依赖；配置缺失必须失败。
- **不引入新依赖**（除非任务强制需要，并能在仓库依赖管理中对齐）。
- **输出稳定**: 冒烟脚本的 stdout 应可被 CI 解析（例如输出固定标志文本）。

# References
- tasks: docs/tasks.md（18.3）
- Script: backend/scripts/start_server_and_healthcheck.py

# Target Files
- backend/scripts/start_server_and_healthcheck.py
- backend/tests/test_fastapi_skeleton.py（如需补充：对端点契约、敏感信息边界、依赖项列表做回归断言）

# Execution Plan
1) 校验脚本请求头与端点契约一致
- 必需 headers：`X-Tenant-Id`、`X-Project-Id`、可选 `X-Request-Id`。

2) 校验失败策略
- 服务端口未就绪必须失败。
- `/api/v1/health` 非 200 必须失败并打印 body。

3) 校验日志 requestId
- 必须能在结构化日志中找到本次请求的 `requestId`（脚本中 requestId 与日志字段一致）。

4) 输出稳定性
- 成功时必须输出固定标志：`healthcheck_ok`。
- 失败时必须输出可诊断信息（包含 status code 与 response body 的安全摘要）。

# Verification
- **Smoke**: `python backend/scripts/start_server_and_healthcheck.py`

### Checklist（自检）
- [ ] 冒烟脚本是否实际启动了 FastAPI（而非仅单元级调用），并等待端口就绪？
- [ ] 冒烟脚本请求是否携带了必需 headers（`X-Tenant-Id`、`X-Project-Id`），并可选携带 `X-Request-Id`？
- [ ] 当 `/api/v1/health` 返回非 200 时，脚本是否立即失败并打印 body（便于 CI 定位）？
- [ ] 当服务端口未就绪/启动失败时，脚本是否失败并给出英文错误？
- [ ] 脚本是否验证日志中可找到该次请求的 `requestId`（结构化日志字段一致）？
- [ ] 冒烟脚本输出是否稳定且可被 CI 解析（例如固定输出 `healthcheck_ok`）？
- [ ] 冒烟链路是否连接真实依赖；缺配置/依赖不可用时是否确实失败（不得 skip）？
```

---

### Checklist（自检）
- [x] Umbrella 是否包含 `# Critical Rules` 并明确禁止写代码？
- [x] `# Execution Plan` 是否覆盖了 18.1 / 18.2 / 18.3？
- [x] 是否定义了 Schema First（后端 Pydantic）与契约对齐要求？
- [x] 是否明确了结构化错误模型字段，并强调 `message` 为英文？
- [x] 是否明确了配置外部化、缺配置快速失败、敏感信息不外泄？
- [x] 是否包含 `requestId` 贯穿与日志可观测性要求？
- [x] 是否强调真实集成测试且不可 skip，并给出可执行的验证命令？
- [x] Doc References Updated
- [x] 是否明确了状态码与头部的契约要求？
- [x] 是否明确了环境变量的契约/实现要求对齐？
- [x] 是否明确了输出要求与验收口径？
- [x] 是否明确了依赖探测的契约与实现要求？
- [x] 是否明确了冒烟脚本的契约与实现要求？
