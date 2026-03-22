### Task 8 - 实现 Postgres 只读查询工具（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 8 号任务：实现 Postgres 只读查询工具（模板化 SQL + 仅 SELECT + 证据对象输出）。
你的角色是 **技术负责人/架构师**。

本任务处于 L1（只读查询）阶段的“工具与适配层”，目标是：
- 提供一个**安全、可审计、可追溯**的 Postgres 查询工具，支撑后续对话/分析链路。
- 工具必须默认注入并强制执行 `tenantId/projectId` 的 scope 过滤，禁止跨域访问。
- 工具输出必须能用于证据链（Evidence）构建：任何数值/表格结果都要带可追溯来源信息。

你需要输出执行蓝图，覆盖：工具接口、参数 schema、只读约束（仅 SELECT）、模板化查询策略、字段白名单、scope 行级过滤、超时/重试策略、审计与 Evidence 输出形态，以及单元/冒烟测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **PLANNING ONLY**: 只输出“怎么做、分几步、改哪些文件、契约长什么样、怎么验收”。
- **Read-Only Default（强制）**:
  - 工具必须只读；禁止任何写入。
  - 必须拒绝任何非 `SELECT`（含 `INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/TRUNCATE/GRANT/REVOKE/COPY/CALL/DO` 等）。
  - 必须拒绝多语句（`;<statement>`），避免绕过只读规则。
- **Schema 单一事实源（强制）**:
  - 工具参数与输出使用 Pydantic 作为单一事实源。
  - 对外返回（工具结果/证据对象/错误对象）在输出前必须通过 schema 序列化/校验。
- **RBAC + 数据域过滤（强制）**:
  - 工具层必须校验 capability（按仓库既有 RBAC 能力命名规则 `a:b:c`）。
  - 必须默认注入并强制执行 scope（`tenantId/projectId`）过滤；检测到跨域访问必须失败并记录审计。
- **Evidence-First（强制）**:
  - 工具输出必须生成 Evidence，可追溯字段至少包括：`source_system`、`table_or_view`、`time_range`、`filters`（脱敏）、`extracted_at`、`query_fingerprint`（避免泄露原 SQL）。
- **结构化错误（强制）**:
  - 统一错误模型字段：`code` + `message`（英文）+ `requestId` + `retryable` + `details?`。
  - 超时必须映射为 `UPSTREAM_TIMEOUT`；连接失败为 `UPSTREAM_UNAVAILABLE`；契约违规为 `CONTRACT_VIOLATION`；越权为 `FORBIDDEN/AUTH_ERROR`。
- **配置外部化（强制）**:
  - 禁止硬编码数据库 URL/超时等，必须来自环境变量并被校验（例如 `.env.example` 中的 `GANGQING_DATABASE_URL`）。
- **真实集成测试（No Skip）**:
  - 冒烟/集成测试必须连接真实 Postgres。
  - 配置缺失或依赖不可用：测试必须失败（不得 skip）。

# References
- PRD: docs/requirements.md（R8.1/R8.2/R8.3）
- TDD: docs/design.md（2.5.2/2.9/3.3/6.1/6.3）
- tasks: docs/tasks.md（任务 8）
- contracts: docs/contracts/api-and-events-draft.md
- env: .env.example（GANGQING_DATABASE_URL 及超时/重试/审计相关配置）

# 权威参考文档/约束来源（强制）
- docs/requirements.md（“Postgres 查询工具”验收标准：仅 SELECT + RBAC/scope + Evidence + 超时映射）
- docs/design.md（L1 Postgres 查询工具约束、Evidence 结构、错误模型、配置外部化）
- docs/contracts/api-and-events-draft.md（ErrorResponse/Evidence 等契约草案，以该文档为准）

# Execution Plan
1) Task 8.1（工具参数与模板化查询）
- Goal:
  - 定义“可被模型调用”的**查询意图参数**，而不是让模型自由拼接 SQL。
  - 支持最小查询场景：按指标/实体/时间范围/过滤条件查询，并可扩展。
- Key Decisions:
  - 参数 schema（Pydantic）字段集合与边界（时间范围、指标名、维度、分页、排序等）。
  - 查询模板集合与映射策略（metric -> SQL template），避免任意 SQL。
- Deliverables:
  - `PostgresToolQuery`（参数模型）与 `PostgresToolResult`（结果模型）草案。
  - 模板化查询的“模板注册表”（例如按 metric 名选择模板）。

2) Task 8.2（只读与安全：SELECT-only + scope + 字段白名单）
- Goal:
  - 只允许 SELECT，并且防止多语句/注入/绕过。
  - 强制 scope（tenant/project）过滤；任何跨域访问必须失败。
  - 按角色/能力做字段白名单，避免敏感字段泄露。
- Key Decisions:
  - SELECT-only 判定方式（语法层检查优先；最差也要做严格黑名单与多语句阻断）。
  - scope 过滤注入方式（模板 SQL 内置 `tenant_id/project_id` 条件 + 参数化执行）。
  - 对返回行做二次 scope 校验（防止错误模板或 join 漏洞导致跨域数据 hit）。

3) Task 8.3（Evidence 与审计：可追溯 + 可观测 + 可定位）
- Goal:
  - 每次工具调用必须产出 Evidence，并写入审计（tool.call/tool.result）。
  - 审计参数必须脱敏；输出不得泄露连接串/完整 SQL/密钥。
- Key Decisions:
  - Evidence 的 source locator：使用 `table/view + time_range + filters + query_fingerprint`，避免原 SQL 泄露。
  - 审计事件字段：至少包含 `requestId/tenantId/projectId/sessionId/userId/role/toolName/durationMs/result/errorCode/evidenceRefs`。

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确本任务涉及的工具实现、模板注册表、DB 执行层、隔离/RBAC/audit 复用模块的文件路径。
- [ ] **Environment Variables**: 列出本任务依赖的 ENV（至少 `GANGQING_DATABASE_URL`），并说明缺失时的失败策略（必须失败，英文错误）。
- [ ] **Tool Contracts (Pydantic)**:
  - `PostgresReadOnlyQueryParams` 输入 schema（包含 `templateId/timeRange/filters/orderBy/limit/offset/timeoutSeconds` 以及 scope 注入规则）。
  - `PostgresReadOnlyQueryResult` 输出 schema（包含 `rows/rowCount/queryFingerprint/evidence/toolCallId`）。
- [ ] **Error Model**: 明确本工具会返回的错误码（`VALIDATION_ERROR/FORBIDDEN/AUTH_ERROR/CONTRACT_VIOLATION/UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE/INTERNAL_ERROR`），并声明 `message` 必须英文。
- [ ] **Auth & RBAC**: capability 口径（建议以代码为准，例如 `tool:postgres:read`）；拒绝时必须审计。
- [ ] **Isolation (tenantId/projectId)**: scope 注入/显式校验规则、跨域拒绝与二次校验（row-level cross-scope data hit detection）。
- [ ] **Evidence Contract**: Evidence 必填字段与禁止泄露项（不得包含连接串/完整 SQL/密钥）。
- [ ] **Observability & Audit**: `requestId` 贯穿与 tool call 审计字段口径。

# Verification
- Automated Tests:
  - Unit: `pytest -q`
  - Smoke（真实 Postgres）:
    - `python backend/scripts/postgres_tool_smoke_test.py`
- Failure Policy（强制）:
  - 若缺少 `GANGQING_DATABASE_URL`：必须失败并输出清晰英文错误。
  - 若 Postgres 不可达：必须失败并映射为 `UPSTREAM_UNAVAILABLE`（或脚本返回非零退出码）。

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 8.1 - Postgres 只读查询工具：模板化查询 + Evidence 输出

```markdown
# Context
你正在执行子任务：8.1 - Postgres 只读查询工具：模板化查询 + Evidence 输出。
目标是实现只读查询工具，并把查询结果与 Evidence/审计绑定到 `requestId`。

# Critical Rules
- **仅 SELECT**: 任何非 SELECT 必须被拒绝并返回结构化错误。
- **RBAC + scope**: capability 与 `tenantId/projectId` 强制。
- **Evidence**: 输出必须含 `timeRange/filters/extracted_at/sourceLocator`。
- **配置外部化**: 数据库 URL/超时等必须来自环境变量并校验（例如 `GANGQING_DATABASE_URL`）。
- **英文 message**: 任何对外错误 `message` 必须为英文。

# References
- PRD: docs/requirements.md（R8.1）
- tasks: docs/tasks.md（8.1）
- contracts: docs/contracts/api-and-events-draft.md（Evidence/ErrorResponse）
- env: .env.example（GANGQING_DATABASE_URL）

# Target Files
- backend/gangqing/tools/postgres_readonly.py（工具参数/结果 schema + 模板化查询拼装 + Evidence 生成）
- backend/gangqing/tools/postgres_templates.py（模板注册表：templateId -> base_select_sql/白名单字段/暴露字段）
- backend/gangqing/tools/isolation.py（scope 注入与跨域拒绝/二次校验复用）
- backend/gangqing/tools/runner.py（统一 Params/Result 校验、RBAC、重试与输出契约校验）
- backend/gangqing/common/context.py（RequestContext：requestId/tenantId/projectId 注入约束）
- backend/gangqing/common/audit.py（tool call 审计事件写入封装）
- backend/gangqing/tools/rbac.py（工具级 capability 校验与 RBAC_DENIED 审计）
- backend/gangqing_db/postgres_query.py（只读事务 + statement_timeout + set_config scope 上下文）
- backend/gangqing_db/settings.py（DB settings：`GANGQING_DATABASE_URL` 校验与 `.env.local` 读取）
- backend/tests/test_postgres_tool_readonly.py（单元测试：Evidence 字段/不泄露/只读门禁/错误映射）
- backend/scripts/postgres_tool_smoke_test.py（真实 Postgres 冒烟：migrate + seed + tool.run + audit_log 验证）

# Execution Plan
1) 定义工具参数 Pydantic schema。
2) 实现模板化查询生成与参数化执行。
3) 生成 Evidence 与审计事件。

# Contract Notes (契约要点)
- 输入上下文：必须从 `RequestContext` 获取 `requestId/tenantId/projectId`，并用于：
  - 作用域过滤（scope 注入）
  - 审计字段
  - Evidence 绑定
- 参数约束：
  - 时间范围必须是闭区间或半开区间之一（按项目约定），并在 Evidence 中原样记录。
  - 过滤条件必须结构化（key/op/value），禁止直接拼 SQL。
- 输出约束：
  - 结果必须是结构化 JSON（行列表/列定义/分页信息等），并在返回前通过 Pydantic 校验。
  - Evidence 不得包含敏感信息与完整 SQL；允许包含 `query_fingerprint`。

# Verification
- **Unit**: `pytest -q`
  - 覆盖至少包括：
    - 拒绝非 SELECT / 多语句
    - scope 缺失/部分缺失 => `AUTH_ERROR`
    - 越权 capability => `FORBIDDEN`
    - 超时映射 => `UPSTREAM_TIMEOUT`
- **Smoke**（真实 Postgres）: `python backend/scripts/postgres_tool_smoke_test.py`
  - 缺少 `GANGQING_DATABASE_URL` 必须失败（不得 skip）。

 # Output Requirement
 交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
 - 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
 - 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
 - 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
 - 输出验证命令与关键输出摘要（文本）。

 # Checklist（自检）
 - [ ] 是否严格禁止任意 SQL 输入（只能走模板化查询与结构化过滤条件）？
 - [ ] 是否所有对外错误都返回结构化错误模型，且 `message` 为英文？
 - [ ] 是否拒绝非 SELECT 与多语句？
 - [ ] 是否强制 scope（tenantId/projectId）过滤，并对返回行做二次 scope 校验？
 - [ ] Evidence 是否包含 `sourceLocator/timeRange/filters/extracted_at`（或等价字段），且不包含完整 SQL/连接串/密钥？
 - [ ] 是否写入 tool call 审计事件，且参数摘要已脱敏并包含 `requestId`？
 - [ ] 单元测试是否覆盖：越权/缺 scope/跨域/超时等失败路径？
 - [ ] 冒烟是否连接真实 Postgres，且缺 `GANGQING_DATABASE_URL` 必须失败（不得 skip）？
 ```

 ---
 
 ### Task 8.2 - Postgres 只读查询工具：SELECT-only 防护 + scope 强制 + 字段白名单
 
 ```markdown
 # Context
 你正在执行子任务：8.2 - Postgres 只读查询工具：SELECT-only 防护 + scope 强制 + 字段白名单。
 目标是把“只读默认”落到**不可绕过**的工程实现上：
 - 严格拒绝任何非 SELECT 与多语句。
 - 强制 scope（`tenantId/projectId`）过滤，禁止跨域访问。
 - 按角色/能力进行字段白名单与脱敏策略接入（如本阶段适用）。
 
 # Critical Rules
 - **仅 SELECT**: 必须拒绝任何非 SELECT（含 DDL/DML/权限/复制等）。
 - **拒绝多语句**: 出现 `;`（含注释/空白绕过）必须拒绝。
 - **参数化执行**: 禁止字符串拼接 SQL；所有变量必须参数化。
 - **RBAC + scope（强制）**:
   - capability 必须校验。
   - scope 必须默认注入并强制执行，跨域必须失败并记录审计。
 - **Structured Errors**: 对外错误必须结构化（`code/message/requestId/retryable/details?`），且 `message` 为英文。
 - **No Secret Leakage**: 错误 details 与日志不得包含连接串/密码/完整 SQL。
 
 # References
 - PRD: docs/requirements.md（R5.1/R8.1/R1.2/R1.3）
 - TDD: docs/design.md（只读默认/隔离与脱敏/错误模型）
 - contracts: docs/contracts/api-and-events-draft.md
 - env: .env.example（GANGQING_DATABASE_URL，隔离与脱敏相关开关）
 
 # Target Files
 - backend/gangqing/tools/isolation.py（scope 解析与跨域拒绝）
 - backend/gangqing/common/rbac.py（capability 校验与拒绝策略）
 - backend/gangqing/common/context.py（RequestContext 与必需 headers）
 - backend/gangqing_db/errors.py（错误映射与英文 message）
 - backend/gangqing_db/settings.py（配置加载与缺配置失败策略）
 - backend/tests/*（新增/更新单元测试）
 
 # Execution Plan
 1) 定义 SELECT-only 防护策略
 - 明确判定规则：非 SELECT/多语句/危险关键字/注释绕过等如何处理。
 - 明确拒绝策略与错误码映射：非 SELECT / 多语句应返回稳定错误码（按契约统一口径）。
 
 2) scope 强制与二次校验
 - 生成 SQL 时必须内置 `tenant_id/project_id` 条件（模板层约束）。
 - 结果返回前必须对每行进行 scope 二次校验，发现跨域 data hit 直接失败。
 
 3) 字段白名单与脱敏接入（如适用）
 - 明确不同角色可见字段集合；敏感字段默认脱敏。
 - 审计中记录策略命中摘要（不得记录原始敏感值）。
 
 # Contract Notes (契约要点)
 - 只读防护是安全门禁，不得依赖上层调用者自律。
 - scope 过滤是默认注入，不得允许 caller 通过参数移除过滤条件。
 - 错误 `details` 允许包含命中规则 ID/类型，但不得包含 SQL 原文。
 
 # Verification
 - **Unit**: `pytest -q`
   - 覆盖至少包括：
     - 非 SELECT 被拒绝
     - 多语句被拒绝
     - 缺 scope headers => `AUTH_ERROR`
     - 显式传入 scope 与 ctx 不一致 => `AUTH_ERROR`
     - 越权 capability => `FORBIDDEN`
 
 # Output Requirement
 交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
 - 摘要：说明本次修改了哪些文件、哪些安全门禁被实现。
 - 关键片段：仅粘贴 SELECT-only 与 scope 二次校验的最小必要片段。
 - 文件路径：给出修改后的文件路径（以仓库文件为准）。
 - 输出验证命令与关键输出摘要（文本）。
 
 ### Checklist（自检）
 - [ ] 是否拒绝所有非 SELECT（含 DDL/DML/权限/复制/过程调用）？
 - [ ] 是否拒绝多语句（防止 `SELECT ...; DELETE ...` 绕过）？
 - [ ] 是否全程参数化执行，无字符串拼接 SQL？
 - [ ] 是否强制 scope 注入，并对返回行做二次 scope 校验？
 - [ ] 是否对越权/跨域访问写入审计（至少包含 `requestId` 与拒绝原因摘要）？
 - [ ] 是否所有对外错误 `message` 为英文、字段结构化且不泄露敏感信息？
 - [ ] 单元测试是否覆盖：非 SELECT、多语句、缺 scope、跨域、越权等失败路径？
 ```
 
 ---
 
 ### Task 8.3 - Postgres 只读查询工具：Evidence 生成 + 审计落库 + 可观测字段
 
 ```markdown
 # Context
 你正在执行子任务：8.3 - Postgres 只读查询工具：Evidence 生成 + 审计落库 + 可观测字段。
 目标是让“工具调用”具备可追溯证据链与可审计证据：
 - 每次查询都生成 Evidence（可用于 Context Panel 展示）。
 - 每次工具调用都写入审计事件（参数摘要脱敏 + 耗时 + 结果状态）。
 - `requestId` 必须贯穿工具调用、审计与证据对象。
 
 # Critical Rules
 - **Evidence-First（强制）**: 任何数值/表格结果都必须绑定 Evidence。
 - **Audit（强制）**: 必须记录工具调用审计事件，参数摘要必须脱敏。
 - **Structured Errors**: 错误模型结构化且 `message` 必须英文。
 - **No Sensitive Data**: Evidence/审计不得包含连接串、密码、完整 SQL、原始敏感字段值。
 
 # References
 - PRD: docs/requirements.md（R2.2/R11.1/R8.1）
 - TDD: docs/design.md（3.3 Evidence 结构、2.8 审计、6 错误模型）
 - contracts: docs/contracts/api-and-events-draft.md
 - env: .env.example（审计异步开关/脱敏配置等，如适用）
 
 # Target Files
 - backend/gangqing/tools/postgres_readonly.py（Evidence 生成与脱敏策略接入、审计 evidenceRefs 绑定）
 - backend/gangqing/common/audit.py（tool call 审计写入）
 - backend/gangqing/common/settings.py（审计异步开关与工具默认超时配置）
 - backend/gangqing_db/audit_log.py（审计事件落库与表结构口径）
 - backend/tests/test_postgres_tool_readonly.py（单元测试：Evidence 字段完整性、不泄露、审计写入调用）
 - backend/scripts/postgres_tool_smoke_test.py（真实 Postgres 冒烟：验证 Evidence+审计）
 
 # Execution Plan
 1) 定义 Evidence 结构与最小字段集
 - 明确 `sourceLocator` 组成：`table_or_view + time_range + filters + query_fingerprint`。
 - 明确 `extracted_at` 时间标准（UTC）与格式。
 
 2) 绑定 requestId 与审计事件
 - 工具调用开始/结束必须写入审计事件，字段至少包含：
   - `requestId/tenantId/projectId/sessionId/userId/role/toolName/durationMs/result/errorCode/evidenceRefs`
 - 参数摘要必须脱敏。
 
 3) 错误映射与安全摘要
 - DB 错误必须映射到稳定错误码（`UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE/CONTRACT_VIOLATION` 等）。
 - 错误 details 仅允许安全摘要（不得包含 SQL 原文/连接串）。
 
 # Contract Notes (契约要点)
 - Evidence 可包含 `query_fingerprint`，但不得泄露 SQL 原文。
 - 审计写入失败策略必须明确并一致（是否阻断请求需在设计中明确）。
 
 # Verification
 - **Unit**: `pytest -q`
   - 覆盖至少包括：
     - Evidence 字段完整性（含 `timeRange/filters/extracted_at/sourceLocator`）
     - Evidence 不包含敏感字段（连接串/完整 SQL）
     - 审计事件字段完整性与脱敏生效
     - 错误映射：超时/不可达/契约违规映射到稳定错误码
 - **Smoke**（真实 Postgres）: `python backend/scripts/postgres_tool_smoke_test.py`
   - 必须验证：
     - 成功查询能生成 Evidence
     - `audit_log` 中出现对应 `requestId` 的工具调用审计事件
 
 # Output Requirement
 交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
 - 摘要：说明 Evidence 与审计分别在哪些模块落地，以及字段口径。
 - 关键片段：仅粘贴 Evidence 结构与审计写入调用处的最小必要片段。
 - 文件路径：给出修改后的文件路径（以仓库文件为准）。
 - 输出验证命令与关键输出摘要（文本）。
 
 ### Checklist（自检）
 - [ ] Evidence 是否具备可追溯字段（source/table/view、timeRange、filters 脱敏、extracted_at）？
 - [ ] Evidence/审计是否避免泄露连接串、密码、完整 SQL、敏感原始值？
 - [ ] 是否实现工具调用审计事件，并绑定 `requestId`？
 - [ ] 审计参数摘要是否脱敏且可定位（包含命中模板/metric 等安全信息）？
 - [ ] DB 错误是否映射为稳定错误码，且 `message` 为英文？
 - [ ] 单元测试是否覆盖 Evidence 字段完整性、脱敏、审计落库与错误映射？
 ```
 
 ---
 
 ### Task 8 子任务通用 Checklist（适用于 8.1/8.2/8.3）
 - [ ] 是否列出并仅修改/新增仓库实际存在或本任务允许新增的文件路径（不写不存在的路径）？
 - [ ] 是否所有对外错误都满足结构化错误模型（`code/message/requestId/retryable/details?`），且 `message` 为英文？
 - [ ] 是否明确并实现 scope（`tenantId/projectId`）强制与跨域拒绝策略？
 - [ ] 是否明确并实现 RBAC capability 校验，并对拒绝写入审计（至少 `requestId` 可追踪）？
 - [ ] 是否确认输出不泄露敏感信息（连接串、密钥、完整 SQL、内部栈细节）？
 - [ ] 是否提供可执行的自动化验证命令（Unit + Smoke），且 Smoke 连接真实 Postgres、缺配置必须失败（不得 skip）？

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求？（工具只读）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
- [x] 是否包含权威参考文档/约束来源段落并对齐？
