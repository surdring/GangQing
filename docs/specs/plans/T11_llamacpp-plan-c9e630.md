# T11 接入 llama.cpp 推理服务执行蓝图（超时/错误码映射/健康检查联动）
本计划以最小改动方式在现有 GangQing 后端内新增/收敛 `llama.cpp` 适配层、结构化错误映射、健康检查联动与真实集成测试脚本，确保契约与验收口径可自动化验证。

## 决策（已确认，作为本任务权威口径）
- **上游协议**：llama.cpp 提供 **OpenAI 兼容接口**，以 `POST /v1/chat/completions` 为推理调用目标。
- **模型选择**：使用**单一固定模型**，由 ENV 配置（调用侧不暴露可变 `model` 选择）。
- **后备策略**：**启用 provider 后备**（存在时可切换），并将该策略纳入错误映射、健康检查与审计口径。

## 0. 现状对齐（基线盘点）

### 0.1 已存在的“权威机制”（本任务必须复用）
- **统一配置加载**：`backend/gangqing/common/settings.py::load_settings()` 会加载仓库根目录 `.env.local`，并通过 `GangQingSettings(BaseSettings)` 做 Pydantic 校验。
- **统一错误模型**：`backend/gangqing/common/errors.py`
  - `ErrorCode` 已包含：`UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE/CONTRACT_VIOLATION/SERVICE_UNAVAILABLE/...`
  - `ErrorResponse` 字段已对齐草案：`code/message/details?/retryable/requestId`
- **健康检查端点**：`GET /api/v1/health`（`backend/gangqing/api/health.py`）
  - 探针实现：`backend/gangqing/common/healthcheck.py`
  - 已包含 `llama_cpp` 探测（`GANGQING_LLAMACPP_*`）与 overall `healthy/degraded/unhealthy` 聚合。
- **结构化日志（含脱敏）**：`backend/gangqing/common/logging.py` 已接入 `redact_sensitive` 处理器；中间件会通过 `structlog.contextvars` 绑定 `requestId/tenantId/projectId/...`。
- **审计落库**：`backend/gangqing/common/audit.py::write_tool_call_event/write_audit_event` 可作为推理调用的审计入口（注意 actionSummary 必须脱敏）。

### 0.2 任务 11 的关键差距（需要补齐的“推理调用面”）
目前 `llama.cpp` 已在健康检查探针层面有配置与探测，但**推理调用适配层（请求/响应契约、超时/不可用映射、审计字段、真实集成测试脚本）仍需定义与落地**。

另外，由于已确认启用 provider 后备，本任务还必须明确：
- `llama.cpp -> provider` 的**切换条件**（哪些错误/状态触发切换）
- 切换过程的 **SSE 可观测事件** 与 **审计字段**（不泄露密钥/prompt）
- 与 `GET /api/v1/health` 的“model 依赖在线”判定一致性

---

## 1) Task 11.1：llama.cpp 适配层接口与配置（Schema First）

### 1.1 目标
- 定义后端内部的 `llama.cpp` 适配层最小对外接口（给编排层/Chat API 调用）。
- 定义推理调用所需的配置项清单、ENV 映射与 Pydantic 校验规则。
- 明确“不得泄露 prompt/密钥”的日志与审计字段边界。

### 1.2 目录与目标文件（建议）
- **新增** `backend/gangqing/llm/llamacpp_settings.py`
  - 用 `pydantic_settings.BaseSettings` 定义**推理调用配置**（与健康探针配置区分）。
- **新增** `backend/gangqing/llm/llamacpp_client.py`
  - 封装 HTTP 调用、超时、错误映射、响应解析与契约校验（Pydantic）。
- **改动（小）**：`backend/gangqing/api/chat.py` 或编排层中实际调用 LLM 的位置
  - 用适配器替换/接入推理调用。
- **可选改动**：`backend/gangqing/common/settings.py`
  - 若项目倾向“单一 settings 对象”，可将 llama.cpp 推理配置并入 `GangQingSettings`；否则维持 `llamacpp_settings.load_llamacpp_settings()` 独立加载。

> 约束：不新增“第二套 dotenv 加载器”；必须复用现有 `.env.local` 加载策略（进程 env > `.env.local`）。

### 1.3 推理适配层对外接口（内部契约 / Pydantic 模型）
> 命名建议以“契约即接口”为导向；以下为字段口径，不涉及实现代码。

- **输入模型**：`LlamaCppChatRequest`
  - `model: str`（固定值；由 ENV 注入/默认；上层不得透传用户自定义 model）
  - `messages: list[ChatMessage]`（必填，最小包含 `role/content`）
  - `temperature?: float`（可选，范围 0..2）
  - `top_p?: float`（可选，范围 0..1）
  - `max_tokens?: int`（可选，>0）
  - `stop?: list[str]`（可选）
  - `stream: bool = False`（本任务可先只支持非流式；如后端要 SSE，建议后端仍采用自己的 SSE 协议而非上游流式直透）
  - `request_id: str`（从 `RequestContext` 贯穿，用于日志/审计与错误模型）

- **输出模型**：`LlamaCppChatResponse`
  - `content: str`（必填，assistant 最终文本）
  - `finish_reason?: str`（可选）
  - `usage?: TokenUsage`（可选：`prompt_tokens/completion_tokens/total_tokens`，如果上游返回）
  - `raw_provider?: dict | None`（**禁止**默认向上层暴露；仅用于调试且必须可配置开关+脱敏；推荐本任务先不暴露）

- **错误输出**：通过抛出 `AppError`（`backend/gangqing/common/errors.py`）
  - 最终对外（REST/SSE）必须是 `ErrorResponse`，并满足：`message` 英文，且 `requestId` 可关联。

### 1.4 配置项（ENV）与校验（Pydantic Settings）
> 目标：与 `.env.example` 的 `GANGQING_LLAMACPP_*` 命名保持一致；缺失关键配置必须快速失败（英文错误）。

- `GANGQING_LLAMACPP_BASE_URL`（必填）
  - 规则：必须为 `http(s)://`；允许配置到 `/v1` 或根路径；客户端需要兼容二者。
- `GANGQING_LLAMACPP_MODEL`（必填）
  - 规则：单一固定模型名，用于组装 OpenAI 兼容请求体的 `model` 字段。
- `GANGQING_LLAMACPP_API_KEY`（可选）
  - 规则：不得写入日志/审计；仅允许在 HTTP header 使用。
- `GANGQING_LLAMACPP_TIMEOUT_SECONDS`（必填，>0）
  - 语义：推理调用的端到端超时（非健康探针）。
- （建议新增，若本任务范围包含并发/队列治理）
  - `GANGQING_LLAMACPP_MAX_CONCURRENCY`（>=1）
  - `GANGQING_LLAMACPP_QUEUE_MAX_SIZE`（>=0；0 表示不排队，直接拒绝）
  - `GANGQING_LLAMACPP_QUEUE_TIMEOUT_SECONDS`（>0；排队等待上限）

配置校验失败时的错误策略：
- 服务启动期（如在 app startup 预加载）：抛出 `RuntimeError`（英文 message），使进程启动失败。
- 请求期（延迟加载）：返回 `ErrorResponse(code=UPSTREAM_UNAVAILABLE 或 VALIDATION_ERROR)` 取决于“缺配置是否视为上游不可用”。推荐：
  - **缺少 base_url/model** => `UPSTREAM_UNAVAILABLE`（retryable=true），因为属于依赖未就绪。
  - **参数不合法（超时<=0 等）** => `VALIDATION_ERROR`（retryable=false）。

---

## 2) Task 11.2：超时/不可用错误映射与重试/降级策略

### 2.1 目标
- 将 llama.cpp 调用侧的异常分类为稳定错误码（与 `ErrorCode` 对齐）。
- 明确 `retryable` 判定，并规定在 SSE 内如何对“重试/降级”进行可观测表达。

### 2.2 错误分类 -> 稳定错误码映射（强制）
> 对外错误结构必须为 `ErrorResponse`，其中 `message` 必须英文。

- **连接失败 / DNS / 连接拒绝 / TLS 错误**
  - `code`: `UPSTREAM_UNAVAILABLE`
  - `retryable`: `true`
  - `details.reason`: `connection_failed`
- **请求超时（read/connect/overall timeout）**
  - `code`: `UPSTREAM_TIMEOUT`
  - `retryable`: `true`
  - `details.reason`: `timeout`
- **HTTP 429 / 503 / 502 / 504（上游限流或过载）**
  - `code`: 优先 `UPSTREAM_UNAVAILABLE`（或若你希望区分“本服务队列满”则用 `SERVICE_UNAVAILABLE`）
  - `retryable`: `true`
  - `details.reason`: `upstream_overloaded`
- **HTTP 4xx（除 401/403 外）且可归因于请求参数/模型名不合法**
  - `code`: `CONTRACT_VIOLATION`（若上游契约与我们期望不一致）或 `VALIDATION_ERROR`（若可明确为我们入参不合法）
  - `retryable`: `false`
- **响应 JSON 不可解析 / 必填字段缺失 / 类型不匹配（Pydantic 校验失败）**
  - `code`: `CONTRACT_VIOLATION`
  - `retryable`: `false`（按 contracts 草案）
  - `details.source`: `llama_cpp.response`

### 2.3 重试/降级策略（建议口径）
- **是否重试**：默认遵循现有全局工具重试策略字段（`GANGQING_TOOL_MAX_RETRIES` 等），但 llama.cpp 调用可能并不属于“工具”。本任务建议两种方案二选一：
  - **方案 A（推荐，最小改动）**：llama.cpp 调用作为“模型依赖”，不走工具 runner 的重试；只在上层（chat 流程）对 `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE` 做最多 1 次重试，并输出 `warning` 事件。
  - **方案 B（统一治理）**：将 llama.cpp 调用也纳入统一“可重试 runner”，复用 backoff 配置，并把每次 attempt 通过 SSE `progress/warning` 输出。

- **降级/切换（已确认启用 provider 后备）**：当 llama.cpp 不可用时
  - **切换触发条件（建议作为本任务验收口径）**：
    - llama.cpp 调用返回 `UPSTREAM_TIMEOUT` 或 `UPSTREAM_UNAVAILABLE`
    - 或 llama.cpp 返回可判定为“服务不可用”的上游状态（如 502/503/504/429 等）
  - **切换前置条件**：provider 调用点已配置且可用（与 healthcheck 的 `provider` 探针保持一致的 URL/API Key 来源）。
  - **切换后的可观测**：必须在 SSE 输出 `warning`，包含：
    - `code`: `UPSTREAM_UNAVAILABLE` 或 `UPSTREAM_TIMEOUT`
    - `details`: 至少包含 `fallbackTo: "provider"`、`attempt: 1`、`provider: "enabled"`
  - **切换后的审计**：必须写入一条审计事件，actionSummary 仅包含非敏感摘要（例如 `route: "llama_cpp->provider"`、`durationMs`、`result`）。
  - **无后备/后备也不可用**：返回 `ErrorResponse(code=UPSTREAM_UNAVAILABLE)`。

### 2.4 SSE 可观测要求（与 contracts 对齐）
- 在发生重试/降级前必须输出：
  - `type=warning`（payload.code 复用 `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE`，message 可中文或英文，但**最终 error.message 必须英文**）
- 每次调用 attempt 产出：
  - `tool.call/tool.result` 或等价事件（若 llama.cpp 不被定义为 tool，仍建议以 `toolName=llama_cpp.generate` 方式复用既有事件模型，避免前端与审计分叉）。

---

## 3) Task 11.3：健康检查联动（unhealthy/degraded）

### 3.1 目标
- 将 llama.cpp 的在线状态与“关键/非关键依赖”策略联动到 `GET /api/v1/health`。
- 明确 `unhealthy` 与 `degraded` 的判定口径，且对外只暴露非敏感摘要。

### 3.2 与现有实现的对齐点
现有 `backend/gangqing/common/healthcheck.py` 已实现：
- `probe_llama_cpp()`：支持 `/v1` 前缀兼容探测；支持 `GANGQING_LLAMACPP_TIMEOUT_SECONDS`；对超时/连接失败输出 `details.reason` 与 `errorClass`。
- `GANGQING_LLAMACPP_CRITICAL` 控制是否 critical：
  - critical=true 且不可用 => dependency `unavailable`，overall 可能变为 `unhealthy(503)`
  - critical=false 且不可用 => dependency `degraded`，overall 可能为 `degraded(200)`

本任务需要补齐的内容是：
- **“推理调用配置”与“健康探针配置”字段一致性**（至少 base_url、api_key、timeout 的命名保持一致，避免两套 ENV）。
- 明确当 llama.cpp 与 provider 都不可用时，`model` 依赖应为 `unavailable`，overall `unhealthy(503)`（现有 `probe_model()` 已覆盖）。

并且由于已确认启用 provider 后备，本任务将以如下口径验收 health：
- `llama_cpp` 不可用但 `provider` 可用 => overall 至少 `degraded`，且 `model` 依赖 `ok`。
- `llama_cpp` 与 `provider` 均不可用 => overall `unhealthy(503)`，且 `model` 依赖 `unavailable`。

### 3.3 对外健康检查契约（验收口径）
- 端点：`GET /api/v1/health`
- 状态码：
  - overall `healthy/degraded` => HTTP 200
  - overall `unhealthy` => HTTP 503
  - 缺少 `X-Tenant-Id` 或 `X-Project-Id` => HTTP 401 + `ErrorResponse(code=AUTH_ERROR)`（由 `RequestContext` 依赖保证）
- 依赖项必须包含：`llama_cpp`，且其 `details` 不得包含：base_url 全量、api_key、上游响应正文。

---

## 4) 可观测性与审计（强制）

### 4.1 结构化日志（structlog）
- 必须字段（自动或显式绑定）：
  - `requestId/tenantId/projectId`
  - `toolName`（建议固定 `llama_cpp.generate`）
  - `latencyMs`（推理调用耗时）
  - `status`（success/failure）
- 禁止字段：
  - `llamacpp_api_key`、`Authorization`、原始 prompt、完整 messages、完整上游响应。
  - 如需 debug：仅允许输出**脱敏摘要**（例如 message count、token usage）。

### 4.2 审计事件（落库）
- 事件类型：复用 `AuditEventType.TOOL_CALL` 或新增等价 `MODEL_CALL`（若新增必须同步契约与枚举；本任务建议先复用 TOOL_CALL）。
- 最小字段：
  - `requestId`、`toolName`、`result`、`durationMs`（建议放在 argsSummary/resultSummary 内或扩展 actionSummary）
  - `errorCode`（失败时填 `ErrorCode`）
- `actionSummary/argsSummary` 必须脱敏；不得记录 prompt 原文。

---

## 5) Verification（真实集成测试，No Skip）

### 5.1 单元测试（pytest）
- 命令：`pytest -q`
- 覆盖点（至少）：
  - 错误映射：timeout/connection_failed/unexpected_response/json_parse_error -> `ErrorCode` + `retryable`
  - 响应契约校验失败 -> `CONTRACT_VIOLATION`（message 英文，details 结构化）
  - 配置校验：缺 base_url/timeout<=0 时快速失败（英文 message）

> 说明：单元测试允许通过依赖注入传入“fake http client”来模拟错误形态，但不得以 mock 框架替代真实集成测试。

### 5.2 冒烟测试（必须连接真实 llama.cpp）
- 新增脚本：`backend/scripts/llamacpp_smoke_test.py`
- 运行前置（缺失即失败）：
  - `GANGQING_LLAMACPP_BASE_URL`
  - `GANGQING_DATABASE_URL`（因为审计落库/系统整体依赖）
  - `GANGQING_BOOTSTRAP_ADMIN_USER_ID/PASSWORD`
- 断言链路（至少 3 类）：
  1. **成功链路**：
     - `/api/v1/health` 中 `llama_cpp.status == ok` 且 overall 非 unhealthy
     - `POST /api/v1/chat/stream` 能完成，首事件 `meta`、末事件 `final(status=success)`
     - 审计中存在 `toolName=llama_cpp.generate`（或等价）且包含耗时/状态（脚本可通过审计查询接口或 DB 查询验证，按仓库现有方式选择）
  2. **超时链路**（需要你提供一个“会超时”的 llama.cpp 配置或专用模型/路由；无法构造则本条作为阻断项需要补齐环境）：
     - 触发 `UPSTREAM_TIMEOUT`（REST 或 SSE error）
     - `ErrorResponse.message` 为英文，且 `requestId` 与请求头一致
  3. **不可用链路**（base_url 指向不可达地址）：
     - 触发 `UPSTREAM_UNAVAILABLE`
     - `retryable=true`

---

## 6) 已定稿的关键假设（不再作为开放问题）
- llama.cpp 为 **OpenAI 兼容接口**：以 `POST /v1/chat/completions` 为主路径；base_url 允许带或不带 `/v1` 前缀。
- `model` 为 **ENV 固定单值**（新增 `GANGQING_LLAMACPP_MODEL`）。
- **启用 provider 后备**：发生 `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE` 等可判定不可用场景时允许切换，并通过 SSE + 审计可观测。

---

## 7) 交付清单（Definition of Done）
- [ ] 适配层契约（Pydantic 模型）与对外错误模型完全对齐：`code/message/details?/retryable/requestId`，且 **error.message 英文**。
- [ ] llama.cpp 推理调用配置全部外部化，且启动/请求期均能被 Pydantic 校验；缺失关键配置快速失败。
- [ ] 错误码映射覆盖：timeout/unavailable/contract_violation/service_unavailable（如队列满）。
- [ ] 健康检查可区分 `unhealthy/degraded`，且不泄露密钥。
- [ ] 推理调用产出结构化日志与审计事件，包含 `requestId/toolName/latencyMs/status`，且不含敏感字段。
- [ ] `pytest -q` 通过。
- [ ] `backend/scripts/llamacpp_smoke_test.py` 连接真实 llama.cpp 且通过；缺配置/依赖不可用时 **测试必须失败**（不得 skip）。
