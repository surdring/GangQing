### Task 5 - 设计并落地 Postgres 最小数据模型（Umbrella）

```markdown
# Context
你正在执行第 5 号任务：设计并落地 Postgres 最小数据模型（维表/事实表/口径仓库/审计表）。
角色：**技术负责人/架构师**。
目标是规划数据库表、索引、约束、迁移策略（可回滚）、以及与 Evidence/审计/隔离字段对齐的最小数据模型。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Isolation（强制）**: 表设计必须包含 `tenant_id/project_id`（或等价字段）并默认过滤。
- **Evidence-First**: 关键事实表需要支持 time_range 查询与可追溯来源定位（至少可定位到表与主键）。
- **审计不可篡改**: 审计表 append-only 设计与权限约束。
- **结构化错误**: 数据库错误映射为稳定错误码与英文 message。
- **真实集成测试（No Skip）**: 冒烟测试必须连真实 Postgres。

## Technology Standards
- 后端：对外 I/O、工具参数、Evidence、审计事件使用 Pydantic 作为单一事实源。
- 错误信息（`message`）必须为英文；对外错误必须结构化：`code` + `message` + `requestId` + `retryable` + `details?`。
- **Read-Only Default**: 默认只读；本任务只落地 schema/迁移与查询友好性，不引入任何业务写操作能力。
- **RBAC & Audit**: 所有敏感查询/数据访问必须做 RBAC 权限检查并记录审计事件，贯穿 `requestId`。
- **配置外部化**: Postgres 连接、超时等必须通过环境变量配置，不得硬编码。

# References
- PRD: docs/requirements.md（R7.1/R11.1/R11.2）
- TDD: docs/design.md（2.6.1/2.8.1）
- tasks: docs/tasks.md（任务 5）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/*.md
- db migration: backend/migrations/versions/0001_init_min_schema.py
- db ops: backend/README.md
- acceptance: reports/2026-02-19_T5.3_postgres-schema-tests.md

# Execution Plan
1) Task 5.1（表结构与索引）（子任务 5.1）
- Goal: 定义最小可用的维表/事实表/元数据表，并保证隔离字段、查询路径与关键约束。
- Key Decisions:
  - 统一隔离字段：`tenant_id`、`project_id`（或等价）出现在所有业务表。
  - 统一时间字段：事实表至少包含 `event_time`/`start_time`/`end_time`（二选一或组合），以支持 time_range 查询。
  - Evidence 定位：事实表需要可定位来源的稳定主键（如 `id`），以及可选的 `source_system`/`source_record_id`（如适用）。
- Scope Tables:
  - 维表：设备/物料。
  - 事实表：产量/能耗/成本/报警事件/维修工单。
  - 元数据表：指标口径仓库（`metric_lineage`）、审计日志（`audit_log`）。

2) Task 5.2（迁移与回滚策略）（子任务 5.2）
- Goal: 选择迁移工具与目录结构，保证迁移可回滚。
- Rule: 必须验证 upgrade->downgrade->upgrade 成功（如采用 Alembic）。

3) Task 5.3（测试口径）（子任务 5.3）
- Unit: 迁移脚本/模型可导入、基础约束可用、错误映射策略可被单测覆盖。
- Smoke: 在真实 DB 中验证表/索引/关键约束存在，并跑一次回滚循环（如适用）。

# Deliverables Definition
- [ ] **Directory Structure**: 明确迁移与模型文件位置（例如 `backend/.../migrations` / `backend/.../models`，以仓库实际为准）。
- [ ] **Environment Variables**: 列出 Postgres 连接所需 ENV（主机/端口/库名/用户/密码/SSL/超时），并定义校验 Schema（Pydantic）。
- [ ] **DB Schema Contracts**: 每张表的字段、主键、唯一约束、外键（如有）、索引（尤其是 `(tenant_id, project_id, time)` 查询路径）。
- [ ] **Evidence Contract Alignment**: 明确事实表如何定位到 Evidence（表名 + 主键 + 可选来源字段）。
- [ ] **Audit**: 审计表 append-only 语义策略（权限/触发器/应用层约束的取舍）与字段最小集（含 `request_id`）。
- [ ] **Error Model**: 数据库相关错误码映射策略（英文 message），与 `docs/contracts/api-and-events-draft.md` 对齐。
- [ ] **Observability**: `requestId` 在 API/审计/日志中的贯穿字段定义。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/postgres_schema_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 5.1 - Postgres 初始化迁移：表/索引/约束

```markdown
# Context
你正在执行子任务：5.1 - Postgres 初始化迁移：表/索引/约束。
目标是把最小数据模型以迁移脚本形式落地到真实 Postgres。

角色：**高级开发工程师**。
你的目标是编写代码与迁移脚本，确保通过单元测试与真实 Postgres 冒烟测试。

# Critical Rules
- **Isolation**: 所有核心表包含 scope 字段，并具备索引支持过滤。
- **只读默认**: 该任务只涉及数据库 schema 迁移，不引入业务写操作能力。
- **真实集成测试（No Skip）**: 冒烟脚本必须连接真实 Postgres，配置缺失必须失败。
- **Schema First**: 与数据库交互的对外契约/模型必须以 Pydantic 为单一事实源（如本子任务涉及 API 或工具参数）。
- **Structured Errors**: 错误必须结构化（`code`/`message`/`requestId`/`retryable`/`details?`），其中 `message` 必须为英文。
- **RBAC & Audit**: 涉及审计表写入/查询的路径必须补齐 RBAC 与审计字段（至少 `request_id`）。

# References
- PRD: docs/requirements.md（R7.1）
- tasks: docs/tasks.md（5.1）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files
- 迁移脚本（例如 `backend/**/migrations/**`，以仓库实际结构为准）
- 数据模型/表定义（例如 `backend/**/models/**`，如项目采用 ORM）
- 冒烟脚本：`backend/scripts/postgres_schema_smoke_test.py`
- 单元测试（例如 `backend/tests/**/test_postgres_schema*.py`）

# Execution Plan
1) 定义迁移边界
- 明确本次迁移创建哪些表/索引/约束，哪些不在本次范围内。

2) 新增迁移脚本：创建表与索引
- 重点索引：`(tenant_id, project_id, event_time)` 或等价 time_range 查询路径。
- 关键约束：主键、必要的唯一约束、NOT NULL、必要的 check 约束（如状态枚举）。

3) 审计表 append-only 策略落地
- 至少说明并实现一种可执行的策略：
  - DB 权限层禁止 UPDATE/DELETE（推荐）
  - 或触发器阻断 UPDATE/DELETE
  - 或应用层保证 append-only + 审计（需明确风险与补救）

4) 补齐错误映射策略（如涉及应用层 DB 异常捕获）
- 定义稳定错误码（英文 message），并保证包含 `requestId`。

5) 补齐测试
- 单元测试：覆盖迁移脚本可运行、关键表/索引/约束名称存在。
- 冒烟测试：连接真实 Postgres 执行迁移并断言 schema 存在。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/postgres_schema_smoke_test.py`
- **Rollback**（如适用）: 验证 upgrade->downgrade->upgrade 成功。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（避免在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 5.2 - Postgres 迁移与回滚策略（可回滚性验证）

```markdown
# Context
你正在执行子任务：5.2 - Postgres 迁移与回滚策略（可回滚性验证）。
目标是把迁移体系（工具/目录/命名/回滚策略）定下来，并提供可自动化验证的 upgrade->downgrade->upgrade 证据。

角色：**高级开发工程师**。
你的目标是补齐迁移框架与回滚链路，并确保在真实 Postgres 上可重复验证。

# Critical Rules
- **NO SCOPE CREEP**: 该子任务聚焦迁移体系与回滚验证，不新增业务表字段以外的需求。
- **真实集成测试（No Skip）**: 回滚验证必须连真实 Postgres；配置缺失必须失败。
- **结构化错误**: 失败时必须输出稳定错误码与英文 message（便于 CI/日志检索）。
- **配置外部化**: 迁移连接信息必须来自环境变量，不得硬编码。

# References
- tasks: docs/tasks.md（5.2）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files
- 迁移工具配置（例如 `backend/**/alembic.ini` / `backend/**/migrations/**`，以仓库实际为准）
- 回滚验证脚本/用例（例如 `backend/scripts/postgres_schema_smoke_test.py` 或新增 `backend/scripts/postgres_migration_rollback_smoke_test.py`，以仓库实际为准）
- 单元测试（例如 `backend/tests/**/test_migrations*.py`）

# Execution Plan
1) 明确迁移工具与目录结构
- 选择并固定使用的迁移方案（如 Alembic），并明确版本表、脚本目录、命名规范。

2) 定义回滚策略与回滚边界
- 明确哪些变更必须可逆（表/索引/约束），以及不可逆操作的处理策略（若存在，必须禁止或替代）。

3) 落地自动化验证：upgrade->downgrade->upgrade
- 提供可重复执行的命令或脚本，输出关键断言（版本号变化、表/索引存在性）。

4) 错误输出标准化
- 当迁移失败/连接失败时，输出英文 message + 稳定 code，并包含 requestId（如该脚本在服务端上下文中运行）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: 运行回滚循环验证脚本（必须连真实 Postgres）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**。
- 摘要：迁移工具/目录结构/回滚验证方式的最终决定。
- 关键片段：回滚循环的命令/脚本入口与关键断言。
- 文件路径：所有变更落盘路径。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 5.3 - Postgres Schema 测试口径（Unit + Smoke）

```markdown
# Context
你正在执行子任务：5.3 - Postgres Schema 测试口径（Unit + Smoke）。
目标是把 schema 相关测试分层（单元测试 + 冒烟测试），并确保在真实 Postgres 上可跑通且不可 skip。

角色：**高级开发工程师**。
你的目标是新增/完善测试用例与冒烟脚本，使其对关键表/索引/约束与隔离字段具备自动化断言。

# Critical Rules
- **Real Integration (No Skip)**: 冒烟测试必须连接真实 Postgres；配置缺失必须失败。
- **失败必须可定位**: 断言失败时要输出清晰英文 message（包含表名/索引名/约束名等），便于排障。
- **Isolation（强制）**: 必须验证关键表存在隔离字段，并且存在支持过滤的索引。

# References
- tasks: docs/tasks.md（5.3）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files
- 冒烟脚本：`backend/scripts/postgres_schema_smoke_test.py`
- 单元测试：`backend/tests/**/test_postgres_schema*.py`（以仓库实际为准）

# Execution Plan
1) 定义测试断言清单
- 表存在性、列存在性、主键/唯一约束、关键索引、隔离字段、时间字段。

2) 单元测试（Unit）
- 覆盖：迁移脚本可被加载/执行（在测试环境的 DB 上），以及关键 schema 元信息断言。

3) 冒烟测试（Smoke）
- 覆盖：连接真实 Postgres，执行迁移到目标版本，并断言关键 schema。

4) 错误输出标准化
- 配置缺失/连接失败/断言失败：必须失败并给出英文 message。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/postgres_schema_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**。
- 摘要：新增/修改了哪些测试断言与脚本逻辑。
- 关键片段：最核心的断言与失败信息格式。
- 文件路径：所有变更落盘路径。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？（要求已明确）
- [x] 是否包含结构化错误模型字段？（全局规则已包含）
- [x] 是否包含证据链要求与字段？（强调表需支持 time_range 与 evidence 定位）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（审计表在范围内）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
- [x] Doc References Updated
