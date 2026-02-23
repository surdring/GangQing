# T08 Postgres 只读查询工具（模板化 SQL + SELECT-only + Evidence）执行蓝图

本蓝图定义 L1 阶段 Postgres 只读查询工具的契约、强制安全门禁与验收策略，并明确需要改动的文件与测试口径以支撑落地与审计。

## 1. 权威约束（必须遵守）

- **只读默认**：仅允许 `SELECT`；拒绝任何非 `SELECT`（含 `INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/TRUNCATE/GRANT/REVOKE/COPY/CALL/DO` 等）。
- **拒绝多语句**：禁止 `;` 形成多 statement（含空白/注释绕过）。
- **Schema 单一事实源**：工具入参/出参/Evidence/错误均以 **Pydantic** 为唯一事实源；输出前必须序列化/校验。
- **RBAC + 隔离**：工具层必须 capability 校验（`a:b:c`）；必须强制 `tenantId/projectId` scope，检测跨域必须失败并写审计。
- **Evidence-first**：工具返回必须带 Evidence（可追溯来源与时间范围），且**不得泄露完整 SQL/连接串/密钥/敏感原值**。
- **结构化错误**：对外错误模型字段固定为 `code/message/details?/retryable/requestId`，其中 **`message` 必须英文**。
- **配置外部化**：数据库 URL/超时等来自环境变量（`.env.example`），缺失必须快速失败（英文错误）。
- **真实集成测试（No Skip）**：冒烟/集成测试必须连真实 Postgres；缺配置/不可达必须失败（不得 skip）。

补充（基于最佳实践的防御纵深）：

- **最小权限（强制）**：工具使用的数据库账号必须是只读账号（仅 `SELECT` 必需权限），禁止 `INSERT/UPDATE/DELETE/DDL`。
- **只读事务（强制）**：每次查询必须在 DB 事务层显式启用 `READ ONLY`，作为对模板误配/绕过的最后门禁（参考 PostgreSQL `SET TRANSACTION ... READ ONLY`）。
- **查询超时（强制）**：每次执行必须设置数据库侧 `statement_timeout`（优先 `SET LOCAL statement_timeout`），避免长查询拖垮连接池。
- **身份贯穿（强制）**：工具必须以 `RequestContext` 为权威身份/范围来源（identity passthrough），审计日志必须能定位到用户与 scope；LLM 不得接触数据库连接串与密钥。

### 1.1 参考文档（权威）

- `docs/requirements.md`：R8.1/R8.2/R8.3（只读 + RBAC/scope + Evidence + 超时映射）
- `docs/design.md`：2.5.2/2.9/3.3/6.1/6.3（工具约束、Evidence、配置外部化、错误码）
- `docs/contracts/api-and-events-draft.md`：ErrorResponse/Evidence/SSE 事件（契约口径）
- `.env.example`：`GANGQING_DATABASE_URL`、隔离/脱敏、审计异步等配置

外部最佳实践参考（用于本计划的“决策依据”）：

- OWASP：SQL 注入防护（Prepared Statements / Parameterized Queries、最小权限）
- PostgreSQL 官方文档：`SET TRANSACTION ... READ ONLY`、运行时参数与超时治理
- DreamFactory：identity passthrough + deterministic query frameworks（把 AI 当作不可信客户端）
- Arcade：SQL tools 设计（Operational tools 优先、参数化、枚举/白名单、最小权限）

## 2. 现状扫描（为落地复用的既有模块）

- **RequestContext（scope 强制输入）**：`backend/gangqing/common/context.py`
  - 强制 `X-Tenant-Id`、`X-Project-Id`；缺失抛 `AppError(AUTH_ERROR, english message)`。
- **RBAC capability 校验**：`backend/gangqing/common/rbac.py` + `backend/gangqing/tools/rbac.py`
  - `assert_has_capability()` 强制 `a:b:c` 命名；拒绝时抛 `FORBIDDEN`，并写 `RBAC_DENIED` 审计。
- **隔离与跨域拒绝工具函数**：`backend/gangqing/tools/isolation.py`
  - `resolve_scope()`：默认注入 ctx scope；显式 scope 必须与 ctx 一致；跨域抛 `AUTH_ERROR`。
  - `build_scope_where_sql()`：生成 `tenant_id/project_id` 条件与参数。
  - `require_rows_in_scope()`：对返回行二次校验，发现跨域 data hit 抛 `AUTH_ERROR`。
- **Evidence Pydantic 模型**：`backend/gangqing_db/evidence.py`（符合 contracts 的最小字段集合与约束）。
- **审计写入**：`backend/gangqing/common/audit.py` + `backend/gangqing_db/audit_log.py`
  - `write_tool_call_event()` 写 tool_call 审计；`audit_log` 落库是 append-only。
  - 落库前对 `action_summary` 做 `redact_sensitive()`（避免泄露）。
- **配置加载**：`backend/gangqing/common/settings.py`（从 `.env.local` 注入 env，再用 Pydantic settings 校验）。
- **Postgres 健康探测**：`backend/gangqing/common/healthcheck.py`（可复用连接/超时思路）。

## 3. 目标产物（按 8.1/8.2/8.3 拆分）

### 3.1 Task 8.1：工具接口与“查询意图参数”Schema（禁止自由 SQL）

#### 3.1.1 目标

- 让模型/上层编排只能传入**结构化查询意图**，由工具选择**模板化 SQL**（metric→template）并参数化执行。
- 结果输出为结构化表格/数值集合，并附 Evidence（Evidence-first）。

#### 3.1.2 工具接口形态（建议）

- **工具协议**：遵循 `backend/gangqing/tools/base.py` 的 `ReadOnlyTool` 风格（`run(ctx, params) -> result`）。
- **工具命名**：如 `postgres_readonly_query`（最终以仓库工具注册方式为准）。
- **capability**：建议新增固定 capability（例如 `tool:postgres:read`），并加入允许角色集合（后续实现时更新 `_ROLE_TO_CAPABILITIES`）。

补充（最佳实践）：

- **Operational Tool 优先**：本工具定位为“Operational/Deterministic Query Tool”，只支持已注册模板 + 结构化参数；不提供“探索型任意 SQL”。
- **Secrets 不进模型**：数据库连接串与凭据仅由服务端配置/工具上下文持有，不得进入提示词或模型可见上下文。

#### 3.1.3 参数 Schema（Pydantic）建议字段（草案）

说明：字段名以 Python `snake_case` 为主，对外 alias 可对齐 camelCase（和 `RequestContext` 一致）。

- **scope（可选但受控）**
  - `tenant_id?: str`
  - `project_id?: str`
  - 规则：
    - 允许不传（默认注入 ctx scope）。
    - 只要传了任一项，就必须两者都传，且必须与 ctx 完全一致（复用 `resolve_scope()`）。
- **query 意图**（二选一或多选一，避免“自由 SQL”）
  - `metric_name: str`（或 `metric_key`）
  - `template_id?: str`（可选，内部映射；对外不鼓励模型直接选）
  - `dimensions?: list[str]`（限定枚举；来自模板 registry 定义）
  - `filters?: list[FilterCondition]`（结构化过滤：field/op/value）
  - `time_range: {start, end}`（强制；用于 Evidence）
  - `limit?: int` / `offset?: int`（分页上限硬限制）
  - `order_by?: list[OrderBy]`（字段必须在白名单且绑定方向）
- **执行控制（可观测/可运维）**
  - `timeout_seconds?: float`（可选：上层可请求更短；工具内部需 clamp 到配置上限）
  - `dry_run?: bool`（建议 **不提供**，避免输出 SQL；如要提供必须只返回 `query_fingerprint` 等安全摘要）

FilterCondition 建议：
- `field: str`（必须在模板允许的 filter 字段集合）
- `op: Literal["eq","ne","gt","gte","lt","lte","in","like","between"]`
- `value: str|float|int|bool|list[...]|{start,end}`（按 op 决定）

#### 3.1.4 结果 Schema（Pydantic）建议字段（草案）

- `tool_call_id: str`（用于 Evidence 关联；若上层有 toolCallId 体系则复用）
- `rows: list[dict[str, Any]]`（严格：只含白名单字段；敏感字段已脱敏/移除）
- `columns: list[{name,type}]`（可选，用于前端表格渲染）
- `row_count: int`
- `truncated: bool`（超过 limit 或安全阈值则 true）
- `evidence: Evidence` 或 `evidence_refs: list[str]`
- `query_fingerprint: str`（强制，替代原 SQL；可放入 `sourceLocator` 或 result 顶层）

> 注意：contracts 中 Evidence 的 `sourceLocator` 是 `dict`，因此“表/视图、过滤、fingerprint”等建议放入 `sourceLocator`（见 3.3）。

### 3.2 Task 8.2：只读与安全门禁（SELECT-only + 多语句拒绝 + scope 强制 + 字段白名单）

#### 3.2.1 SELECT-only 判定策略（强制）

优先顺序建议（防御纵深）：

1) **模板化查询 = 默认安全主路径**
- 工具不接收自由 SQL，因此“只读”主要在模板 registry 与执行层强制。

2) **执行前的 SQL 只读断言（仍然需要）**
- 即便是模板，也必须在执行前对最终 SQL 做只读断言，用于防止：
  - 模板误配
  - 未来扩展时引入危险片段

只读断言必须覆盖：
- **仅允许单 statement**：拒绝任何 `;`（以及 `;` 两侧注释/空白）。
- **仅允许 `SELECT` 开头（忽略前导空白与注释）**。
- **拒绝关键字黑名单**：`INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COPY|CALL|DO` 等（大小写不敏感）。
- **拒绝事务控制**：`BEGIN|COMMIT|ROLLBACK`（防止多语句/隐式写入路径）。

错误映射：
- 只读断言失败：建议统一映射 `CONTRACT_VIOLATION`（原因：内部模板/生成逻辑违反只读契约），并写审计。

补充（数据库侧最后门禁，强制）：

- **事务只读**：每次查询在数据库执行前必须开启 `READ ONLY` 事务（`BEGIN; SET TRANSACTION READ ONLY; ... SELECT ...; COMMIT;` 或 `BEGIN READ ONLY;`）。
- **事务参数仅对当前事务生效**：使用 `SET LOCAL ...`（例如 `statement_timeout`）避免污染连接池后续请求。
- **建议限制 search_path**：在连接初始化或事务开始设置固定 `search_path`，降低意外引用非预期 schema 的风险。

#### 3.2.2 scope 强制与跨域失败策略（强制）

- **scope 注入（生成 SQL 阶段）**：
  - 使用 `resolve_scope(ctx, tenant_id?, project_id?)` 得到 effective scope。
  - 模板必须包含 scope where 条件（`tenant_id = :tenant_id AND project_id = :project_id`）。
  - 禁止模型/调用方通过 filters 提供 “tenant_id/project_id” 自由覆盖；scope 永远由工具注入。

- **scope 二次校验（返回数据阶段）**：
  - 工具必须确保返回行包含 `tenant_id/project_id`（哪怕最终输出要隐藏，也应在内部行结构里存在）。
  - 用 `require_rows_in_scope(ctx, rows)` 检测跨域 data hit，发现即：
    - 抛 `AUTH_ERROR`（英文 message）
    - 写审计（failure + error_code）

#### 3.2.3 字段白名单与脱敏

目标：避免敏感字段通过“表格结果”泄露。

- **模板级白名单**：每个模板声明：
  - `allowed_select_fields`
  - `allowed_filter_fields`
  - `required_hidden_fields`（例如 `tenant_id/project_id` 用于二次校验，但不对外展示）

- **角色/能力级白名单**（可选增强）：
  - 基于 `ctx.role` / capability 决定返回字段集合。
  - 若仓库已有 masking policy（`.env.example` 的 `GANGQING_MASKING_POLICY_JSON`）在其它链路已落地，应在工具输出前复用同一策略执行 `mask/allow/deny`。

补充（数据库层行级安全，作为增强而非替代）：

- **RLS（可选增强）**：在核心表启用 Row Level Security 并建立 policy（`USING (...)`），将 `tenant_id/project_id` 作为 DB 层的强制过滤；应用侧继续保留 scope 注入与返回行二次校验，形成“双重门禁”。

### 3.3 Task 8.3：Evidence + 审计（可追溯 + 可定位 + 不泄露 SQL）

#### 3.3.1 Evidence 输出形态（对齐 contracts + 现有 Evidence 模型）

Evidence 使用 `backend/gangqing_db/evidence.py::Evidence`：

- `sourceSystem`：固定为 `Postgres`（或项目约定枚举；若必须在 contracts 枚举内，则用最接近的如 `ERP/MES/...` 需要你确认；见“待确认问题”）。
- `sourceLocator`（dict，建议最小字段）：
  - `database`: 逻辑库名/数据域标识（不得含连接串）
  - `tableOrView`: 主要表/视图（或模板声明的视图集合）
  - `timeRange`: 建议不重复（contracts 已有 `timeRange` 顶层），因此 locator 里可放 `timeField`/`timeBucket` 等
  - `filters`: **脱敏后的**过滤摘要（禁止原值；仅展示字段名、op、值类型/区间摘要）
  - `queryFingerprint`: 指纹（hash），代替 SQL 原文
  - `templateId` / `metricName` / `lineageVersion?`：用于可追溯口径
- `timeRange`：来自参数（强制 end>start；Evidence 模型已校验）。
- `extracted_at`：contracts 草案里提到 extracted_at，但当前 Evidence 模型没有该字段；建议在 `sourceLocator.extractedAt` 里记录 ISO 时间（UTC）。
- `toolCallId`：本次工具调用 ID。
- `confidence` / `validation`：
  - 只要能确认来源/范围/过滤且 scope 校验通过，默认 `validation=verifiable`。
  - 若因权限/脱敏导致无法复核，或返回被截断/缺关键字段，改为 `not_verifiable` 并发 `warning`（由上层 SSE 负责）。

#### 3.3.2 query_fingerprint（避免泄露 SQL）的生成策略

- 输入：**规范化后的安全摘要**（不要用原 SQL），建议包含：
  - `templateId`、`metricName`
  - `timeRange.start/end`（ISO）
  - `filters` 的结构化表达（字段名 + op + 值类型/区间摘要，禁止原值）
  - `tenantId/projectId`（可选：为了避免不同 scope 下指纹碰撞；但注意不要对外暴露 scope）
- 输出：`sha256` hex（固定长度）。
- 存放：Evidence `sourceLocator.queryFingerprint`。

补充（最佳实践）：

- **fingerprint 输入必须是“规范化摘要”**：禁止使用原 SQL；只允许模板 ID、字段名、op、值类型/区间摘要、时间范围等安全要素。
- **审计与 evidence 统一引用**：审计事件中记录 `queryFingerprint` + `templateId`，Evidence 中记录同样字段，便于跨系统关联。

#### 3.3.3 审计事件（tool.call/tool.result）字段口径

- 调用开始：`write_tool_call_event(ctx, tool_name, args_summary, result_status="success|failure")`
- 建议 args_summary 最小字段：
  - `metricName`/`templateId`
  - `timeRange`（仅时间，不含敏感字段）
  - `filtersSummary`（脱敏）
  - `limit/offset`
  - `queryFingerprint`
- 调用结束：
  - 目前 `write_tool_call_event` 只写一个事件类型；实现时可：
    - 用同一个 `TOOL_CALL` 事件表达 start/end（需扩展 actionSummary），或
    - 复用 `write_audit_event` 再写一条 `tool_result`（若已有枚举/类型支持）。

审计与 Evidence 关联：
- `backend/gangqing_db/audit_log.py::AuditLogEvent` 已有 `evidenceRefs` 字段，可将 EvidenceId 列表写入。

#### 3.3.4 审计失败策略（必须明确）

- 当前实现：审计写失败只 `logger.warning("audit_write_failed", ...)` 不阻断主流程。
- 对本工具建议：
  - **仍不阻断查询结果返回**（避免因为审计库短暂问题导致主功能不可用），但必须在结构化日志中明确记录失败，并在 metrics 中计数。
  - 这点需在验收口径中明确（见“待确认问题”）。

补充（最佳实践）：

- **审计失败不阻断但要可观测**：必须输出结构化日志字段（`requestId/tenantId/projectId/toolName/errorClass`），并在 metrics 中单独计数，便于告警。

## 4. 需要改动/新增的文件（不写代码，只列落点）

> 以“最小侵入 + 复用已有隔离/RBAC/审计/Evidence 模型”为原则。

- **新增（建议）**
  - `backend/gangqing/tools/postgres_readonly.py`：工具实现（模板 registry + 参数校验 + 执行 + Evidence + 审计）。
  - `backend/gangqing/tools/postgres_templates.py`：模板注册表（metric→template 定义、字段白名单、表/视图声明）。
  - `backend/gangqing_db/postgres_query.py`（或同层模块）：Postgres 执行器（连接、超时、参数化执行、DB 错误映射）。
  - `backend/tests/test_postgres_tool_*.py`：单元测试覆盖 SELECT-only/scope/RBAC/错误映射/Evidence。
  - `backend/scripts/postgres_tool_smoke_test.py`：真实 Postgres 冒烟（端到端）。

- **可能需要更新（按实际实现选择）**
  - `backend/gangqing/common/rbac.py`：加入 `tool:postgres:read` capability 到允许角色。
  - `backend/gangqing/api/router.py` 或其它工具注册位置：暴露工具调用入口（如果现阶段通过 API 调用工具）。
  - `.env.example`：补齐 Postgres 工具的超时/重试相关配置（若目前未定义）。

## 5. 超时与重试策略（工具层）

### 5.1 超时

- **连接/查询超时**必须可配置：
  - 不硬编码秒数；来自 env（例如 `GANGQING_POSTGRES_TOOL_QUERY_TIMEOUT_SECONDS`）。
- 超时错误码：`UPSTREAM_TIMEOUT`（`retryable=true`）。

补充（最佳实践，数据库侧优先）：

- **statement_timeout**：每次查询设置 `SET LOCAL statement_timeout = ...`，并将超时统一映射为 `UPSTREAM_TIMEOUT`。
- **连接超时**：连接层使用 driver/connect_args 的 connect timeout，连接失败映射 `UPSTREAM_UNAVAILABLE`。

### 5.2 重试

- 对 **可重试错误**（网络抖动、连接失败、超时）最多 3 次（指数退避），并写审计：
  - `attempt` 次数
  - 最终错误码/成功
- 不可重试错误（契约违规、越权、scope 错）不得重试。

> 备注：仓库的通用“工具重试框架”是否已有实现尚不明确；若没有，Task 8 中可先只做超时映射与最小重试（但必须在验收口径里说清）。

## 6. 验收与测试口径

### 6.1 单元测试（pytest，必须通过）

最小覆盖（建议至少 10 条用例，含失败路径）：

- **scope**
  - 缺 `tenantId/projectId`（ctx 构造或 resolve_scope）=> `AUTH_ERROR`
  - 只传 tenant 不传 project / 反之 => `AUTH_ERROR`
  - 显式 scope 与 ctx 不一致 => `AUTH_ERROR`
  - 返回行跨 scope（require_rows_in_scope）=> `AUTH_ERROR`
- **RBAC**
  - 缺 capability => `FORBIDDEN`（英文 message=Forbidden）
- **SELECT-only**
  - 模板/生成 SQL 含 `;` => `CONTRACT_VIOLATION`
  - 非 `SELECT`（含 `DELETE` 等）=> `CONTRACT_VIOLATION`
- **DB 只读事务门禁**
  - 当执行路径尝试非只读命令时，必须在 `READ ONLY` 事务下被拒绝（不依赖应用侧字符串检查）。
- **错误映射**
  - DB 连接失败 => `UPSTREAM_UNAVAILABLE`（retryable=true）
  - DB 超时 => `UPSTREAM_TIMEOUT`（retryable=true）
- **Evidence**
  - Evidence `timeRange` 校验（end<=start 必须失败）
  - Evidence `sourceLocator` 不包含连接串/SQL 原文（可用断言：不包含 `postgresql://`、不包含 `select` 原文片段）

### 6.2 冒烟测试（真实 Postgres，必须通过，No Skip）

脚本：`python backend/scripts/postgres_tool_smoke_test.py`（需新增）

- **前置失败策略（强制）**
  - 未配置 `GANGQING_DATABASE_URL` => 脚本直接失败（exit code !=0），并输出英文错误。
  - Postgres 不可达 => 脚本失败，并输出映射后的错误码（或至少明确不可达）。

- **成功路径（最小）**
  - 用固定 `tenantId/projectId`（`.env.example` 已有 `GANGQING_TENANT_ID/GANGQING_PROJECT_ID`）
  - 执行 1 个模板化查询（例如从事实表按天聚合）
  - 断言：
    - 返回结果非空（或返回结构符合 schema）
    - Evidence 生成且 `evidenceId` 存在
    - `audit_log` 表可按 `requestId` 查到对应 tool_call 事件，且 `evidenceRefs` 有值

补充（必须验证的 DB 侧行为）：

- 冒烟脚本必须验证：
  - 查询执行时应用了 `statement_timeout`（可通过制造可控慢查询触发超时，验证错误码 `UPSTREAM_TIMEOUT`）。
  - 查询在 `READ ONLY` 事务中执行（可通过尝试一条明确会被只读事务拒绝的语句来证明门禁有效；此语句仅用于测试，且必须保证不会写入成功）。

## 7. 关键决策（已基于最佳实践定稿）

1) **capability 命名**：采用 `tool:postgres:read`。
- 依据：满足既有 `a:b:c` 规范，语义清晰；按 DreamFactory/Arcade 的“least privilege + deterministic tool”建议，将数据库访问收口到单一 read capability。

2) **Evidence.sourceSystem**：采用 `Postgres`。
- 依据：Evidence 的语义是“证据来源系统”，数据库本身是明确来源；用 `ERP/MES` 会造成语义漂移。
- 约束：若 contracts 对枚举值有限制，则在 contracts 中补充允许值（本任务仍以计划为准，后续实现时对齐契约）。

3) **extractedAt 字段位置**：采用 `Evidence.sourceLocator.extractedAt`（ISO 8601, UTC）。
- 依据：不修改既有 Evidence Pydantic 模型字段结构，避免对 contracts 与上下游造成破坏性变更；同时满足“可追溯 extracted_at”。

4) **审计写失败策略**：不阻断查询结果，但必须：
- 写结构化日志（含 `requestId`）
- metrics 计数（便于告警）
- 在审计事件中（若可写）标记 `auditWriteStatus`（仅摘要）
- 依据：与当前代码行为一致（`audit_write_failed` warning），且符合高可用最佳实践。

5) **首批模板 registry 覆盖范围**：只定义“最小可验收集合”，先做 3 类模板：
- **按时间窗聚合的指标查询**（日/小时粒度）
- **按实体/产线/工序维度分组的 TopN**
- **按唯一主键/业务键的明细查询（带强制 limit）**

约束：模板必须声明 `allowed_select_fields/allowed_filter_fields/required_hidden_fields`，并强制 scope 注入。

---

## Checklist（用于你确认蓝图是否满足任务）

- [ ] 工具不接收自由 SQL，仅结构化意图 + 模板化查询
- [ ] 只读门禁：非 SELECT 与多语句必拒绝
- [ ] scope 强制注入 + 返回行二次校验
- [ ] capability 校验 + 拒绝写审计
- [ ] Evidence 可追溯（timeRange/sourceLocator/queryFingerprint/filtersSummary/extractedAt）且不泄露敏感信息
- [ ] 错误模型字段与英文 message 符合 contracts
- [ ] 配置外部化：缺 `GANGQING_DATABASE_URL` 快速失败
- [ ] 单元测试 + 真实 Postgres 冒烟测试（No Skip）验收口径明确
