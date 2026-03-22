# T08 Postgres 只读查询工具执行蓝图

本蓝图定义 GangQing L1 阶段 Postgres 只读查询工具的落地方案：以模板化 SQL + 强制 SELECT-only + tenantId/projectId scope 注入为核心，统一输出可审计、可追溯的 Evidence 与结构化错误，并给出单元/冒烟测试与验收口径。

## 0. 结论先行（当前仓库现状对齐）

- **[已具备可复用实现]** 仓库内已存在 `backend/gangqing/tools/postgres_readonly.py`、`backend/gangqing/tools/postgres_templates.py`、`backend/gangqing/tools/isolation.py`、`backend/gangqing/tools/runner.py` 等模块，且已经覆盖：
  - Pydantic 入参/出参 schema（单一事实源）
  - SELECT-only + 多语句拒绝（含注释/空白归一化）
  - scope 默认注入 + 显式校验 + 行级二次校验（cross-scope data hit detection）
  - 超时（`statement_timeout`）与只读事务（`SET TRANSACTION READ ONLY`）
  - 工具级 RBAC capability（`tool:postgres:read`）
  - Evidence 输出与审计（`tool_call` 事件 + `evidenceRefs`）
  - 冒烟脚本（真实 Postgres，不允许 skip）：`backend/scripts/postgres_tool_smoke_test.py`
- **[本任务“执行蓝图”要做的事]** 在不改变核心约束的前提下，明确：
  - 工具接口与契约（入参/出参/错误码）对齐 `docs/contracts/api-and-events-draft.md`
  - 模板化查询策略的扩展口径（template registry 的治理与白名单）
  - 字段白名单/脱敏策略与 Evidence/sourceLocator 结构的“稳定字段定义”
  - 测试与验收的“必须覆盖点”（含失败策略）

## 1. 权威约束来源（必须遵循）

- `docs/requirements.md`
  - R8.1：仅 SELECT + RBAC/scope + Evidence + 超时映射
  - R8.2：工具参数 Pydantic 校验，失败 => `VALIDATION_ERROR`
  - R8.3：超时/重试（最多 3 次）与可观测/可审计
- `docs/design.md`
  - 2.5.2：L1 Postgres 工具（模板化、字段白名单、行级安全）
  - 2.9：配置外部化与缺配置快速失败（英文 message）
  - 3.3 / 6.1 / 6.3：Evidence 与错误模型
- `docs/contracts/api-and-events-draft.md`
  - ErrorResponse 与 Evidence 最小字段集合、SSE error/tool.result 同构规则
- `.env.example`
  - `GANGQING_DATABASE_URL`
  - `GANGQING_POSTGRES_TOOL_DEFAULT_TIMEOUT_SECONDS`
  - `GANGQING_POSTGRES_TOOL_MAX_TIMEOUT_SECONDS`
  - 重试相关：`GANGQING_TOOL_MAX_RETRIES` 与 backoff 参数

## 2. 目录与模块边界（Directory Structure）

### 2.1 工具与适配层（权威落点）

- `backend/gangqing/tools/postgres_readonly.py`
  - 工具入口：`PostgresReadOnlyQueryTool`
  - 入参模型：`PostgresReadOnlyQueryParams`
  - 出参模型：`PostgresReadOnlyQueryResult`
  - 只读约束：SELECT-only、多语句阻断
  - scope 注入/二次校验（调用 isolation 模块）
  - Evidence 构建与脱敏（masking）
  - tool_call 审计写入

- `backend/gangqing/tools/postgres_templates.py`
  - 查询模板注册表（`templateId -> PostgresQueryTemplate`）
  - 模板字段白名单：
    - `allowed_filter_fields`
    - `allowed_order_by_fields`
    - `required_hidden_fields`（用于 scope 二次校验）
    - `exposed_fields`（对外暴露字段）

- `backend/gangqing/tools/isolation.py`
  - scope 解析与强制（默认注入/显式校验/跨域拒绝）
  - SQL where 注入（`tenant_id/project_id`）
  - 行级 cross-scope data hit detection（返回前二次校验）

- `backend/gangqing/tools/runner.py`
  - 统一工具 runner：
    - Params Pydantic 校验失败 => `VALIDATION_ERROR`
    - RBAC capability 校验失败 => `FORBIDDEN`
    - Timeout/ConnectionError 映射 => `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE`
    - 重试策略（最多 3 次，指数退避，审计记录 attempt 信息）
    - （若启用 ResultModel 输出契约校验）不符合 => `CONTRACT_VIOLATION`

### 2.2 数据库执行层（只读强制）

- `backend/gangqing_db/postgres_query.py`
  - `execute_readonly_query(sql, params, ctx, statement_timeout_ms)`
  - 强制：
    - `SET TRANSACTION READ ONLY`
    - `statement_timeout`
    - 会话变量（用于未来 RLS/审计/防线）：
      - `set_config('app.current_tenant', ...)`
      - `set_config('app.current_project', ...)`

- `backend/gangqing_db/settings.py`
  - DB 配置加载与校验（`.env.local` + 环境变量优先）
  - 缺少 `GANGQING_DATABASE_URL`：必须快速失败（英文 message）

### 2.3 Evidence 与审计

- `backend/gangqing_db/evidence.py`
  - Evidence Pydantic 模型（字段约束：`timeRange.end > start`、`dataQualityScore` 范围等）

- `backend/gangqing/common/audit.py`
  - `write_tool_call_event(...)`：工具调用审计封装（支持异步写入开关）

- `backend/gangqing/tools/rbac.py`
  - 工具级 capability 校验 + RBAC_DENIED 审计

## 3. 环境变量与失败策略（Environment Variables）

- **必需**：`GANGQING_DATABASE_URL`
  - 缺失 => 工具/冒烟测试必须失败
  - 当前实现（以代码为准）：
    - **在 DB 执行层**：`backend/gangqing_db/postgres_query.py` 捕获 DB settings 的 `ValidationError`，抛出 `ConfigMissingError(code=CONFIG_MISSING, message='Missing required configuration: GANGQING_DATABASE_URL')`。
    - **在工具对外错误（AppError）层**：`backend/gangqing/tools/postgres_readonly.py` 捕获 `MigrationError` 并尝试映射到 `gangqing.common.errors.ErrorCode`；由于公共枚举中不包含 `CONFIG_MISSING`，最终会落为 `AppError(code=INTERNAL_ERROR, message=<ConfigMissingError.message>)`。
    - **在冒烟脚本层**：`backend/scripts/postgres_tool_smoke_test.py` 会单独捕获 `ConfigMissingError` 并打印 `code=CONFIG_MISSING`，用于提示环境未配置。
  - `message` 必须英文（当前实现已满足），例如：`Missing required configuration: GANGQING_DATABASE_URL`

- **工具默认超时**：`GANGQING_POSTGRES_TOOL_DEFAULT_TIMEOUT_SECONDS`
  - Pydantic 校验：`>0`

- **工具最大超时上限**：`GANGQING_POSTGRES_TOOL_MAX_TIMEOUT_SECONDS`
  - 约束：`>= default`

- **重试策略**：
  - `GANGQING_TOOL_MAX_RETRIES`（0..3）
  - Backoff：`GANGQING_TOOL_BACKOFF_*`

## 4. 工具契约（Pydantic 单一事实源）

> 约束：工具入参/出参必须以 Pydantic 为单一事实源；对外输出（含工具结果与 Evidence）必须在返回前通过 schema 序列化/校验。

### 4.1 输入：`PostgresReadOnlyQueryParams`

#### 4.1.1 顶层字段（JSON alias）

- `tenantId?: string`
- `projectId?: string`
  - **规则**：
    - 若 caller 显式传入任一 scope 字段，则必须两者都传入且必须与 `RequestContext.tenant_id/project_id` 一致；否则拒绝。
    - 若不传入，则默认注入 ctx scope（强制过滤）。

- `templateId: string`
  - 从模板注册表选择；未知 => `VALIDATION_ERROR`（英文 message：`Unknown templateId`）。

- `timeRange: { start: datetime, end: datetime }`
  - **必须** `end > start`（由 EvidenceTimeRange 校验）。
  - **约定**：SQL 使用半开区间：`>= start AND < end`（与当前实现一致）。

- `filters?: FilterCondition[]`
  - `FilterCondition = { field: string, op: 'eq'|'ne'|'gt'|'gte'|'lt'|'lte'|'in'|'between', value: any }`
  - **强制**：禁止包含 scope 字段（`tenant_id/project_id/tenantId/projectId`），防止 caller 试图覆盖 scope。
  - **强制**：`field` 必须在模板的 `allowed_filter_fields` 白名单内。
  - **强制**：所有过滤必须参数化，不允许拼接 SQL。

- `orderBy?: { field: string, direction: 'asc'|'desc' }[]`
  - **强制**：`field` 必须在模板的 `allowed_order_by_fields` 白名单内。

- `limit?: int`（默认 200，1..1000）
- `offset?: int`（默认 0，0..100000）

- `timeoutSeconds?: float`
  - **规则**：
    - `<=0` => `VALIDATION_ERROR`
    - `> maxTimeout` => clamp 到 maxTimeout（防止 DoS）

#### 4.1.2 语义层/模型调用约束（模板化策略）

- 工具仅接受“查询意图参数”，不接受任意 SQL。
- 模板是唯一 SQL 来源：模型只能选择 `templateId` 并提供结构化过滤。

### 4.2 输出：`PostgresReadOnlyQueryResult`

- `toolCallId: string`
- `rows: Array<Record<string, any>>`
  - **强制**：对外 rows 只能包含模板 `exposed_fields` 列表中的字段。

- `rowCount: int`
- `truncated: bool`
  - 建议语义：`rowCount >= limit` 表示可能截断。

- `columns?: Array<{ name: string, type: string }>`
  - 可选：L1 可先不输出；若输出需稳定。

- `queryFingerprint: string`
  - **强制**：不得泄露原 SQL；fingerprint 应基于稳定 payload（templateId/tableOrView/timeRange/filtersSummary/limit/offset/scopeMode）。

- `evidence: Evidence`
  - 必填，见 5。

## 5. Read-Only 只读约束（仅 SELECT + 防绕过）

### 5.1 约束目标

- **必须拒绝任何非 `SELECT`**：包括但不限于 `INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/TRUNCATE/GRANT/REVOKE/COPY/CALL/DO` 等。
- **必须拒绝多语句**：任何 `;`（经注释与空白归一化后）视为多语句企图，直接拒绝。
- **必须拒绝事务控制绕过**：`BEGIN/COMMIT/ROLLBACK` 等（作为 forbidden keyword）。

### 5.2 判定策略（推荐优先级）

- **优先：语法级解析（L2+ 可选增强）**
  - 若未来引入 SQL parser（例如 `sqlglot`），应在工具层对生成 SQL 做 AST 检查：
    - statement 数量必须为 1
    - statement 类型必须为 SELECT
    - 禁止任何 DDL/DML/权限/复制/过程调用节点
- **L1 最低线：严格归一化 + 黑名单 + 多语句阻断**（当前仓库实现已覆盖）
  - 去除 `/* */` 与 `--` 注释
  - trim 与空白归一化
  - `;` 阻断
  - `startswith(select)`
  - forbidden keyword regex 命中 => `CONTRACT_VIOLATION`

### 5.3 数据库层只读防线（Defense in Depth）

- 每次执行：`SET TRANSACTION READ ONLY`
- 通过 `backend/scripts/postgres_tool_smoke_test.py` 进行真实验证：
  - 在只读事务中尝试 `CREATE TEMP TABLE ...` 必须失败

## 6. RBAC 与 capability（工具级强制门禁）

- **建议 capability**：`tool:postgres:read`（当前仓库实现已采用）
- 校验位置：工具 runner 调用前（统一层 `backend/gangqing/tools/runner.py`）
- 拒绝行为：
  - 返回结构化错误：`code=FORBIDDEN`，`message` 英文（例如 `Missing capability: tool:postgres:read`）
  - 必须写入审计：`RBAC_DENIED`（见 `backend/gangqing/tools/rbac.py`）

## 7. scope 行级过滤（tenantId/projectId）

### 7.1 scope 注入规则

- scope 来源：`RequestContext.tenant_id/project_id`（强制）
- 工具参数允许显式传入 `tenantId/projectId`，但仅用于“显式复核”，必须与 ctx 完全一致。
- SQL 注入方式：
  - 模板 SQL 必须选择出 `tenant_id/project_id`（作为 `required_hidden_fields`）
  - where 必须包含：`tenant_id = :tenant_id AND project_id = :project_id`（参数化）

### 7.2 cross-scope 检测（二次校验，必须）

- 执行完成后，在返回前对结果行做二次校验：
  - 若任一行存在 `tenant_id/project_id` 且与 ctx 不一致 => 直接失败（`AUTH_ERROR`），并审计标记 `cross_scope_data_hit`。
- 目的：防止模板错误/Join 漏洞/视图定义问题导致 scope 漏过滤。

## 8. 模板化查询策略（Template Registry）

### 8.1 模板注册表结构

- `templateId` 必须稳定（建议命名：`<domain>_<grain>` 如 `production_daily`）
- 每个模板至少包含：
  - `table_or_view`
  - `time_field`
  - `base_select_sql`（必须以 `SELECT ... FROM ...` 开头）
  - `allowed_filter_fields`
  - `allowed_order_by_fields`
  - `required_hidden_fields`（至少包含 `tenant_id/project_id`）
  - `exposed_fields`（对外可见字段清单）

### 8.2 模板治理（本任务要求的“怎么扩展”口径）

- **强制**：新增模板必须同步补齐：
  - 过滤字段白名单
  - 排序字段白名单
  - exposed_fields（避免敏感字段泄露）
  - Evidence/sourceLocator 中的 `tableOrView/timeField/templateId`

- **建议**：模板不得接收自由 SQL 片段；如需复杂聚合，聚合逻辑也必须固化在模板中。

## 9. 字段白名单与脱敏（Field Whitelist & Masking）

### 9.1 字段白名单

- **对外 rows**：只能输出 `exposed_fields`
- **对内二次校验**：必须包含 `required_hidden_fields`（例如 `tenant_id/project_id`），但不得对外暴露

### 9.2 Evidence 脱敏

- Evidence 的 `sourceLocator.filters` 必须是“脱敏摘要”，不得记录原始值
  - 建议摘要形态：仅记录 value 类型与长度/范围标签（仓库已有 `summarize_filter_value`）

- 若启用 masking policy：
  - Evidence 输出可通过 `apply_evidence_role_based_masking` 做 role-based 脱敏
  - `unmask` 权限能力：`data:unmask:read`

## 10. 超时/重试策略（Timeout & Retry）

### 10.1 超时

- 以 DB statement_timeout 为准（毫秒）：
  - `timeoutSeconds` 参数优先，否则用 `GANGQING_POSTGRES_TOOL_DEFAULT_TIMEOUT_SECONDS`
  - 上限 clamp：`GANGQING_POSTGRES_TOOL_MAX_TIMEOUT_SECONDS`

- 超时错误映射：
  - 对外必须为 `UPSTREAM_TIMEOUT`
  - `message` 英文：`Upstream request timed out`
  - `retryable=true`

### 10.2 重试

- 统一由 runner 控制（最多 3 次）：
  - 可重试错误：`UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE` 等（以 `should_retry_error` 策略为准）
  - 每次失败：必须写 tool_call 审计（包含 attempt/backoffMs）

## 11. 审计与可观测（Audit & Observability）

### 11.1 审计事件（tool_call）字段口径

- 写入函数：`write_tool_call_event`
- 最小字段（与 docs/contracts 对齐，落库细节以 DB schema 为准）：
  - 上下文：`requestId/tenantId/projectId/sessionId/userId/role`
  - 工具：`toolName`（resource）
  - `argsSummary`（脱敏）建议至少包含：
    - `scopeFilter`（mode + policyVersion）
    - `templateId`
    - `timeRange`（start/end）
    - `filters`（脱敏摘要）
    - `limit/offset`
    - `queryFingerprint`
    - `durationMs`
    - `rowCount`（成功时）
    - 失败时：`errorCode/retryable/attempt/maxAttempts/backoffMs`
  - `evidenceRefs`：成功时包含生成的 `evidenceId`

### 11.2 requestId 贯穿

- 工具执行前 bind contextvars（结构化日志字段）
- 审计落库与 Evidence `toolCallId/requestId` 可关联

## 12. Evidence 输出形态（Evidence-First）

### 12.1 Evidence 必填字段（对齐 docs/contracts）

- `evidenceId`
- `sourceSystem`（本工具固定 `Postgres`）
- `sourceLocator`（见 12.2）
- `timeRange`（与入参一致）
- `confidence`（建议默认 `High`，除非触发降级）
- `validation`（默认 `verifiable`；若出现不可验证/越界/冲突按规则下调）

### 12.2 `sourceLocator` 建议稳定结构（避免泄露 SQL）

- `database`：仅数据库名（从 URL 安全提取），不得包含连接串
- `tableOrView`
- `timeField`
- `filters`：脱敏摘要
- `queryFingerprint`
- `templateId`
- `extractedAt`：UTC ISO8601

### 12.3 禁止泄露项（强制）

- 连接串（`postgresql://...`）
- 密码/密钥/token
- 完整 SQL 文本
- rows 全量镜像写入 Evidence/audit（只允许摘要）

## 13. 结构化错误模型（ErrorResponse 同构）

> 目标：工具层产生的错误应能被 SSE `error` 与 `tool.result.payload.error` 直接复用（同构）。

### 13.1 工具需覆盖的错误码与触发条件

- `VALIDATION_ERROR`
  - templateId 未知
  - filter/orderBy 字段不在白名单
  - filter op/value 类型不合法（例如 `in` 非空 list、`between` 缺 start/end）
  - timeoutSeconds <= 0

- `FORBIDDEN`
  - 缺少 `tool:postgres:read`

- `AUTH_ERROR`
  - scope 缺失（ctx 缺 tenant/project）
  - 显式 scope 与 ctx 不一致
  - cross-scope data hit detection 命中

- `UPSTREAM_TIMEOUT`
  - statement_timeout 触发

- `UPSTREAM_UNAVAILABLE`
  - 连接失败/网络不可达（ConnectionError/OSError）

- `CONTRACT_VIOLATION`
  - 生成 SQL 非 SELECT / 多语句 / forbidden keyword
  - 工具输出不满足 ResultModel（若启用输出契约校验）

- `INTERNAL_ERROR`
  - 未分类异常

### 13.2 错误 message 规则

- `message` 必须英文
- `details` 仅允许结构化摘要，禁止包含原 SQL/连接串/敏感原值

## 14. 测试与验收口径（Unit + Smoke，No Skip）

### 14.1 单元测试（pytest -q）范围

目标：覆盖核心纯逻辑与关键门禁，不依赖外部 Postgres。

- **Pydantic 校验**：
  - `timeRange.end <= start` 必须失败
  - `filters` 禁止包含 scope 字段
  - `in`/`between` 参数结构校验与错误码

- **模板白名单**：
  - filter 字段不在白名单 => `VALIDATION_ERROR`
  - orderBy 字段不在白名单 => `VALIDATION_ERROR`

- **SELECT-only**：
  - 多语句（包含注释/空白绕过）=> `CONTRACT_VIOLATION`
  - 非 SELECT => `CONTRACT_VIOLATION`
  - forbidden keyword 命中 => `CONTRACT_VIOLATION`

- **scope 行级安全**：
  - 显式 scope 与 ctx 不一致 => `AUTH_ERROR`
  - cross-scope data hit detection => `AUTH_ERROR`

- **Evidence**：
  - evidence 必填字段齐全
  - `sourceLocator` 不包含敏感信息（连接串/SQL）
  - `queryFingerprint` 存在且稳定

> 现有仓库已存在 `backend/tests/test_postgres_tool_readonly.py`，本任务蓝图要求将其作为主要单元覆盖载体（具体断言以现有实现为准）。

### 14.2 冒烟测试（真实 Postgres，必须失败不允许 skip）

- 命令：`python backend/scripts/postgres_tool_smoke_test.py`
- 必须覆盖：
  - 缺少 `GANGQING_DATABASE_URL` => 脚本退出非 0 且打印英文错误
  - 可连 Postgres => 自动 `alembic upgrade head`
  - 验证 DB 防线：
    - `SET TRANSACTION READ ONLY` 下 DDL/写入必须失败
    - `statement_timeout` 必须能取消慢查询（`pg_sleep(1)`）
  - 验证工具链：
    - unknown templateId => `VALIDATION_ERROR`
    - 正常模板查询 => Evidence 生成 + audit_log 存在 tool_call 事件 + evidenceRefs 包含 evidenceId

## 15. 决策点定稿（按当前代码实现）

1) **配置缺失（`GANGQING_DATABASE_URL`）的错误码**
   - **工具对外错误（AppError）**：`INTERNAL_ERROR`（`message` 为英文：`Missing required configuration: GANGQING_DATABASE_URL`）。
   - **冒烟脚本输出/退出**：打印 `CONFIG_MISSING`（来自 `gangqing_db.errors.ConfigMissingError`），用于明确提示缺少环境变量。

2) **跨 scope 拒绝（显式 scope 与 ctx 不一致 / cross-scope data hit）错误码**
   - `AUTH_ERROR`（由 `backend/gangqing/tools/isolation.py` 的 `resolve_scope/require_rows_in_scope` 直接抛出）。

3) **模板扩展的文档同步策略**
   - 本任务（T08）**不强制**同步 docs；模板清单的文档化属于后续治理项。

---

## Checklist（用于你 Review/验收）

- [ ] 仅 SELECT：拒绝非 SELECT 与多语句，且不可绕过
- [ ] Schema 单一事实源：入参/出参 Pydantic 校验，输出前序列化校验
- [ ] RBAC：`tool:postgres:read` 强制，拒绝写审计
- [ ] 隔离：scope 默认注入 + 显式校验 + 行级二次校验
- [ ] Evidence-First：Evidence 字段齐全且不泄露 SQL/连接串
- [ ] 错误模型：`code/message(英文)/retryable/requestId/details?`
- [ ] 配置外部化：禁止硬编码 URL/超时，缺配置快速失败
- [ ] 测试：`pytest -q` + `postgres_tool_smoke_test.py`（真实 Postgres，No Skip）
