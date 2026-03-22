# Task 4 执行蓝图：数据域隔离 + 字段级脱敏 + 可审计（L1）
本蓝图定义 L1 阶段“默认过滤 + 字段级脱敏 + 可审计”的可执行落地方案，明确改动文件、schema、配置项、测试断言与冒烟脚本口径。

## 1. 目标与不变式（验收口径）
- **Isolation（强制）**
  - `tenantId/projectId` 为强制 scope。
  - **缺失 scope headers 必须快速失败**：对外返回 `ErrorResponse(code=AUTH_ERROR, http=401)`。
  - **显式 scope 只能更严格不能越权**：
    - 调用方显式传入 scope（工具参数/查询参数）时：必须同时提供 `tenantId/projectId`，且必须与 `RequestContext` 一致，否则拒绝。
  - **Defense-in-Depth**：工具层默认叠加 scope；工具返回前再做 cross-scope data hit 检测。

- **Masking（强制）**
  - 按角色/域/字段路径进行字段级脱敏；Evidence / 审计 / 日志默认脱敏。
  - 脱敏仅允许记录**策略命中摘要**（policyId/version/maskedKeys 等），禁止敏感原文。

- **Audit（强制）**
  - 隔离拒绝、RBAC 拒绝、脱敏命中必须留下审计摘要，可按 `requestId` 聚合。
  - 审计/日志字段默认脱敏（尤其是 denied 类事件）。

- **Structured Errors（强制）**
  - 对外错误统一 `ErrorResponse`：`code/message/details?/retryable/requestId`。
  - `message` 必须英文。
  - `details` 对外不得泄露上下文（tenant/project/user/role/session 等），不得含密钥、token、SQL、rows、堆栈。

- **Schema 单一事实源（强制）**
  - 后端：Pydantic 为单一事实源；对外输出/事件输出前必须 schema 校验。
  - 前端（如涉及）：Zod 校验 SSE/错误/证据结构。

- **配置外部化（强制）**
  - 隔离/脱敏策略、开关、默认行为必须配置化；禁止在业务逻辑中硬编码租户/产线/字段白名单。

## 2. 现状快照（用于定位改动点）
### 2.1 RequestContext / scope 来源
- **权威入口**：`backend/gangqing/common/context.py::build_request_context`
  - 已实现：缺失 `X-Tenant-Id` / `X-Project-Id` => `AppError(AUTH_ERROR)`，英文 message。
- **鉴权绑定**：`backend/gangqing/common/auth.py::require_auth`
  - 已实现：token 内 `tenantId/projectId` 必须与 ctx scope 一致，否则 `AUTH_ERROR`（401）。

### 2.2 工具层隔离
- **入口**：`backend/gangqing/tools/isolation.py`
  - 已实现：`resolve_scope`（默认注入/显式校验）、`require_rows_in_scope`（cross-scope data hit 检测）。
- **已接入工具**：`backend/gangqing/tools/postgres_readonly.py`
  - 已实现：scope where 自动叠加 + rows cross-scope 检测 + 审计摘要（queryFingerprint）。

### 2.3 脱敏引擎与策略加载
- **入口**：`backend/gangqing/common/masking.py::apply_role_based_masking` + `load_masking_policy`
- **策略加载点（API 侧）**：`backend/gangqing/api/audit.py`
  - 当前行为：策略加载失败 => `CONTRACT_VIOLATION` + 审计。

### 2.4 审计写入
- **入口**：`backend/gangqing/common/audit.py::write_audit_event/write_tool_call_event`
- **事件类型枚举**：`backend/gangqing/common/audit_event_types.py`

### 2.5 已有真实集成冒烟脚本
- **存在**：`backend/scripts/rbac_and_masking_smoke_test.py`
  - 覆盖：缺 scope => 401；token scope mismatch => 401；审计 denied 不泄露敏感原文；/audit/events 对不同角色返回脱敏差异；data.masked 审计事件存在。

## 3. 设计决策（关键口径统一）
### 3.1 AUTH_ERROR vs FORBIDDEN：统一判定规则
以 `docs/contracts/api-and-events-draft.md#2.1.2` 为准：
- **`AUTH_ERROR` / HTTP 401**
  - 缺少或无效鉴权（Authorization 缺失/无效/JWT 过期/签名不对）。
  - 缺少隔离上下文：缺少 `X-Tenant-Id` / `X-Project-Id`。
  - token scope 与 RequestContext scope 不一致。
  - 显式传入 scope 与 ctx 不一致（视为越权企图）。
  - 工具返回 cross-scope data hit（视为越权或数据污染）。
- **`FORBIDDEN` / HTTP 403**
  - 具备有效鉴权与 scope，但缺 capability（RBAC 拒绝）。

说明：`requirements.md` 中 R1.3 提到“空结果或 FORBIDDEN”，但本任务按你给出的 Critical Rules：跨隔离访问必须拒绝并审计，不做静默空结果作为默认策略。

### 3.2 “显式 scope 只能更严格”在 L1 的实现表达
 L1 先落到**可验收的最小集**：
 - **允许**：显式 scope == ctx scope（等价，不越权）。
 - **拒绝**：显式 scope != ctx scope（越权）。
 - **扩展（更严格）**：若要支持显式 scope“更严格”（例如额外维度 `lineId`/`areaId`/`equipmentId`），必须：
   - 在 schema 中显式声明这些维度为 scope 维度；
   - 在 `resolve_scope` 中引入“更严格”比较规则；
   - 在 SQL 注入处将这些维度作为附加 where；
   - 在审计中记录“scopeMode=explicit_stricter”摘要。
 当前 `settings.isolation_extra_dimensions` 已预留入口，但尚未形成统一 schema/where 注入与审计口径；按当前代码现状，本任务将其作为 **可选增强项**（见 4.2），L1 验收不以该能力为前置条件。

### 3.3 脱敏策略配置化：解决“默认策略硬编码”张力
当前 `masking.py` 内存在 `_DEFAULT_SENSITIVE_KEY_FRAGMENTS/_DEFAULT_DOMAINS` 的硬编码默认值。
- **决策**：保留“默认策略”作为 **开发/PoC fallback**，但生产/验收模式要求：
  - `GANGQING_MASKING_POLICY_REQUIRED=true` 时，必须提供有效 policy；缺失/无效 => 快速失败并产生可审计 `CONTRACT_VIOLATION`。
  - 默认策略中的敏感字段集合不得作为业务白名单；验收以配置 policy 为准。
- **验收**：单元测试与冒烟测试必须覆盖 required 模式缺失策略的失败路径。

### 3.4 审计事件最小集合与“敏感原文禁止”
- **最小事件集合（L1）**
  - `query`：用户查询（含 requestId + scope + user + role + actionSummary 摘要）。
  - `tool_call`：工具调用（含 argsSummary/result 摘要 + evidenceRefs）。
  - `api.response`：API 返回摘要（可选但建议，便于 requestId 聚合）。
  - `auth.denied`：鉴权/隔离上下文/越权（scope mismatch/cross-scope hit）拒绝。
  - `rbac.denied`：缺 capability 拒绝。
  - `data.masked`：脱敏命中（policyHits 摘要）。
  - （可选）`data.unmask`：若支持“展开原文”能力，必须先具备能力门禁与审计。

- **敏感原文禁止策略**
  - denied 类事件的 `actionSummary`：不得包含业务 payload 的原始敏感字段。
  - 工具调用 `argsSummary`：必须是脱敏后的摘要（例如 queryFingerprint、字段名、统计计数、时间范围等）。

## 4. 文件级改动清单（执行阶段落地指引：改哪里、改什么）
> 本节只描述改动范围与责任边界，不给任何实现代码。

### 4.1 后端：RequestContext 与 API scope 强制
- **修改**：`backend/gangqing/api/*`（涉及所有对外 API）
  - **目标**：OpenAPI 层面与运行时保持一致：除明确例外外，所有业务端点必须要求 `X-Tenant-Id/X-Project-Id`。
  - **例外策略**：
    - `POST /api/v1/auth/login` 需要 scope headers。
  - **交付物**：更新 openapi 生成策略或 header 声明，使 `X-Tenant-Id/X-Project-Id` 在大多数端点标记为 required（与 contracts 一致）。

- **修改**：`backend/gangqing/common/context.py`
  - **目标**：统一缺失 scope 的错误细节字段口径（仅输出 `details.header`），并确保审计能记录 `request_context_missing_scope` 事件摘要（不含敏感）。

### 4.2 后端：工具层隔离“强制叠加 + 扩展维度”
- **修改**：`backend/gangqing/tools/isolation.py`
  - **目标**：
    - 统一所有拒绝场景的 `details.reason` 枚举值（例如 `missing_scope|partial_scope_params|cross_scope|cross_scope_data_hit`）。
    - （可选增强）支持 `settings.isolation_extra_dimensions` 的**配置化扩展维度**：
      - 维度 schema（Pydantic）
      - 注入 where 的字段映射
      - 审计摘要字段（命中哪些维度）

- **修改**：`backend/gangqing/tools/postgres_readonly.py`
  - **目标**：
    - 确保模板层面不允许过滤条件覆盖 scope（当前已禁止）。
    - 将扩展维度纳入 where 与 rows in scope 检测（如果 rows 具备维度字段）。

- **涉及**：其他工具（如未来 ERP/MES/DCS/EAM 连接器）
  - **要求**：所有工具必须复用同一 `resolve_scope`/cross-scope 检测与审计口径；禁止各自实现不同的 scope 判定。

### 4.3 后端：字段级脱敏策略与边界
- **修改**：`backend/gangqing/common/masking.py`
  - **目标**：
    - 明确 policy schema 版本化（`policyId/version`）与加载失败行为。
    - 默认策略仅作为 fallback；当 required 模式开启，必须强制提供策略。
    - 输出脱敏元信息结构稳定（`policyId/version/maskedKeys`）。

- **修改**：`backend/gangqing/api/audit.py`
  - **目标**：
    - `/audit/events` 返回前对 `actionSummary` 执行脱敏。
    - 当发生脱敏命中：写入 `data.masked` 审计事件（当前已实现），并确保 actionSummary 只包含 policyHits 摘要。

- **扩展点（可选）**：Evidence 默认脱敏
  - **涉及潜在文件**：`backend/gangqing_db/evidence.py`（Evidence schema）、`backend/gangqing/api/chat.py`（SSE evidence.update payload）
  - **目标**：Evidence 的 `sourceLocator.filters`/`sourceLocator` 内字段需要脱敏/摘要化，避免泄露敏感过滤值。

### 4.4 后端：审计事件与落库一致性
- **修改**：`backend/gangqing/common/audit_event_types.py`
  - **目标**：审计事件类型枚举与 contracts 对齐（至少覆盖 query/tool_call/response/error/denied/masked）。

- **修改**：`backend/gangqing/common/audit.py` + `backend/gangqing_db/audit_log.py`
  - **目标**：
    - 写入前对 `actionSummary` 执行递归脱敏（key-fragment redaction），避免 denied/error 场景泄露。
    - 落库字段必须包含 requestId + scope + user + role。

## 5. Schema 与契约改动（单一事实源落地）
### 5.1 后端 Pydantic（必须）
- **RequestContext**：已经存在；需要确保所有对外响应/事件 envelope 使用其字段来源。
- **ErrorResponse**：`backend/gangqing/common/errors.py::ErrorResponse` 已存在；需确保 REST 与 SSE error 同构（chat.py 已做 validate）。
- **MaskingPolicy**：`backend/gangqing/common/masking.py::MaskingPolicy` 已存在；需补齐策略版本化与 domains/fieldPathRules 的约束说明（文档级）。
- **AuditLogEvent/AuditLogRecord**：来自 `gangqing_db`；需确保 actionSummary 结构与脱敏元信息可序列化且不泄露。

### 5.2 前端 Zod（如涉及）
- 若前端展示 Evidence/错误/审计事件：必须用 Zod schema 校验字段完整性（已有 `web/schemas/*`，执行阶段确认与后端一致）。

## 6. 配置项与环境变量清单（缺失必失败）
> 以 `backend/gangqing/common/settings.py` 为基线，补齐任务 4 所需配置枚举与验收口径。

### 6.1 Isolation
- `GANGQING_ISOLATION_ENABLED`（默认 true）
- `GANGQING_ISOLATION_EXTRA_DIMENSIONS`（默认空；用于启用扩展维度，例如 `line_id,area_id`）
- （建议新增/补齐）扩展维度映射：
  - `GANGQING_ISOLATION_DIMENSION_FIELD_MAP_JSON`：维度名 -> DB 字段名（仅 key 映射，不含敏感值）。

### 6.2 Masking
- `GANGQING_MASKING_DEFAULT_ACTION`（mask/allow/deny）
- `GANGQING_MASKING_POLICY_REQUIRED`（true 时缺策略必须失败）
- `GANGQING_MASKING_POLICY_JSON`（策略 JSON，需 schema 校验）
- `GANGQING_MASKING_AUDIT_INCLUDE_POLICY_HITS`（是否写 data.masked 事件）

### 6.3 Audit
- `GANGQING_AUDIT_ASYNC_ENABLED` / `GANGQING_AUDIT_ASYNC_MAX_WORKERS`

### 6.4 运行依赖（真实集成必需）
- `GANGQING_DATABASE_URL`（冒烟/集成必需，缺失必须失败）
- `GANGQING_BOOTSTRAP_ADMIN_USER_ID/PASSWORD`
- `GANGQING_BOOTSTRAP_FINANCE_USER_ID/PASSWORD`
- `GANGQING_TENANT_ID` / `GANGQING_PROJECT_ID`（冒烟脚本默认值可在脚本内 fallback，但验收应建议配置明确）

## 7. 测试与验收（必须：Unit + Smoke，真实服务，不可 skip）
### 7.1 单元测试（pytest -q）覆盖点（最小集）
- **Isolation**
  - 缺少 scope（ctx 内缺 tenant/project 或 headers 缺失）=> `AUTH_ERROR`。
  - 显式传 scope 且与 ctx 不一致 => `AUTH_ERROR`。
  - 工具返回 rows 命中跨域 => `AUTH_ERROR`。
  - 失败原因应在 metrics 中有计数（已有 `test_isolation_metrics.py`）。

- **Masking**
  - 不同角色对同 payload 的脱敏结果不同（finance vs non-finance）。
  - 返回携带脱敏元信息（policyId/version/maskedKeys）。
  - policy required 且缺失/无效 JSON => `ValueError`（并由 API 映射为 `CONTRACT_VIOLATION`）。

- **Audit**
  - denied 类审计 actionSummary 不出现敏感原文（不得含敏感字段名/敏感值）。

### 7.2 冒烟测试（真实 FastAPI + 真实 Postgres）
- **复用并加强**：`backend/scripts/rbac_and_masking_smoke_test.py`
  - 成功路径：
    - 合法 scope + 合法角色：`/audit/events` 返回 items 且同 scope。
    - plant_manager 看到 seeded actionSummary 中敏感字段为 `[MASKED]`，且带 masking meta。
    - finance 看到敏感字段原值。
  - 失败路径：
    - 缺 scope headers => 401 + `ErrorResponse(code=AUTH_ERROR)`。
    - token scope mismatch => 401 + `AUTH_ERROR`，且审计中存在 `auth.denied`，actionSummary 不泄露。
  - 审计链路：
    - `/audit/events` 对 plant_manager 的返回触发 `data.masked` 审计事件并包含 policyHits 摘要。

## 8. OpenAPI / Contract 对齐策略（交付要求）
- **权威契约**：`docs/contracts/api-and-events-draft.md`。
- **交付**：
  - 更新 `docs/api/openapi.yaml` 或其生成源，使 scope headers required 与实际运行时一致（避免文档漂移）。
  - 明确哪些端点例外（若存在），并给出安全证明（为何不构成跨域风险）。

## 9. 风险点与防回归门禁
- **风险：默认策略硬编码**
  - 门禁：required 模式下必须加载外部 policy；CI/验收环境启用 required。
- **风险：OpenAPI 与运行时不一致**
  - 门禁：契约校验冒烟脚本应覆盖“缺 scope headers”对关键端点必 401。
- **风险：审计泄露**
  - 门禁：在 denied/error/tool_call 事件写入前统一做递归脱敏；冒烟脚本做关键字符串扫描断言。

## 10. 以当前实际代码实现为准的结论（用于实现阶段对齐）
 1) **Login 需要 scope headers**
    - 当前实现中 `build_request_context` 强制要求 `X-Tenant-Id/X-Project-Id`，因此 `POST /api/v1/auth/login` 不带 scope 会返回 `AUTH_ERROR/401`。
    - 本任务实现阶段以此为准：优先补齐 OpenAPI/文档/测试口径，避免“契约允许但运行时拒绝”的漂移。
 2) **跨域访问默认拒绝（不返回空结果）**
    - 当前工具隔离与鉴权链路以 `AUTH_ERROR` 拒绝越权（scope mismatch / cross-scope data hit）。
    - 本任务实现阶段以“拒绝 + 可审计”为默认策略，避免静默降级带来的可审计性缺失。
 3) **扩展隔离维度暂不作为 L1 前置**
    - 当前代码仅强制 `tenantId/projectId`；`settings.isolation_extra_dimensions` 尚未形成端到端落地闭环（schema/SQL 注入/审计/测试）。
    - 本任务实现阶段把扩展维度能力列为可选增强：若要启用，需新增配置 schema 与端到端测试覆盖。
