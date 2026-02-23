# T05 Postgres 最小数据模型蓝图（维表/事实表/口径仓库/审计表）

本计划定义 GangQing L1 阶段最小可用的 Postgres 数据模型（表/索引/约束/迁移回滚/测试口径），以满足 **Isolation（tenant/project 强制）**、**Evidence-First（可追溯+time_range）** 与 **append-only 审计不可篡改** 的验收要求。

 ## 0.1 当前仓库现状与 5.1 前置条件（阻塞项）

 - **[现状发现]** 当前仓库未发现 `backend/` 目录、未发现 Alembic 配置（如 `alembic.ini`）、未发现 `pytest` 配置与任何后端 Python 代码（除 `scripts/update_task_prompts_output_requirement.py` 外）。
 - **[结论]** 子任务 5.1 所需的“迁移脚本 + 单元测试 + 真实 Postgres 冒烟脚本（`backend/scripts/postgres_schema_smoke_test.py`）”目前缺少承载位置与运行入口。
 - **[必须确认]** 若要继续落地 5.1/5.2/5.3，需要先允许在仓库中新增最小后端工程骨架（`backend/`）与依赖管理文件（例如 `pyproject.toml` 或 `requirements.txt`），否则无法满足 `pytest -q` 与冒烟脚本的验证要求。

 ### 0.1.1 建议的最小后端落盘结构（用于承载 5.1/5.2/5.3）

 - **[建议目录]**
   - `backend/`
   - `backend/migrations/`（Alembic versions 目录按实际工具结构）
   - `backend/scripts/postgres_schema_smoke_test.py`
   - `backend/tests/test_postgres_schema.py`
   - `backend/gangqing/`（业务包名可调整，但应有稳定的 Python 包路径）
 - **[建议配置]**
   - `.env.example` 追加 Postgres 连接与迁移所需环境变量（保持配置外部化）
   - 测试与脚本：必须读取环境变量；缺失配置应失败（No Skip）

## 0. 范围与硬约束（从权威文档提炼）

- **[范围]** 仅输出“执行蓝图（Markdown）”，不输出任何实现代码。
- **[Isolation 强制]** 所有业务表必须包含并默认过滤：`tenant_id`、`project_id`（或等价字段）。
- **[Evidence-First 强制]** 关键事实表必须：
  - 支持 `time_range` 查询（至少 `start_time/end_time` 或 `event_time`）。
  - 能定位到来源记录：至少“表名 + 主键”；建议补充 `source_system` + `source_record_id`。
- **[审计不可篡改 强制]** 审计表必须 append-only（禁止 UPDATE/DELETE）并具备严格权限约束。
- **[结构化错误 强制]** DB 相关错误需映射为稳定 `code` + **英文** `message` + `requestId` + `retryable` + `details?`。
- **[真实集成测试 强制]** 冒烟测试必须连接真实 Postgres；配置缺失必须失败（No Skip）。

## 1. 数据模型总览（最小闭环：L1）

### 1.1 表清单（最小集合）

- **[维表]**
  - `dim_equipment`
  - `dim_material`
- **[事实表]**
  - `fact_production_daily`（产量）
  - `fact_energy_daily`（能耗）
  - `fact_cost_daily`（成本）
  - `fact_alarm_event`（报警/事件）
  - `fact_maintenance_workorder`（维修工单）
- **[元数据表]**
  - `metric_lineage`（指标口径仓库）
  - `audit_log`（审计日志，append-only）

### 1.2 统一字段规范（跨表一致性）

- **[隔离字段（强制）]**
  - `tenant_id`（string/uuid，按项目约定）
  - `project_id`（string/uuid，按项目约定）
  - 约束：所有主查询路径必须以 `tenant_id, project_id` 作为最左前缀过滤（索引与查询模板均如此）。

- **[通用主键与可追溯性]**
  - 每张表必须有稳定主键 `id`（建议 uuid；或 bigint 自增，但必须稳定且不可复用）。
  - 关键事实表建议包含：
    - `source_system`（枚举/字符串：ERP/MES/DCS/EAM/LIMS/Manual/Detector 等；与 Evidence `sourceSystem` 对齐）
    - `source_record_id`（字符串：上游系统记录 ID / 报表行 ID）

- **[时间字段（强制：支持 time_range）]**
  - 日粒度事实表：使用 `date`（业务日）作为查询主轴，同时保留 `start_time/end_time`（可选）用于证据链精确定位。
  - 事件类事实表：必须包含 `event_time`（timestamp with time zone）；如有持续事件，补充 `end_time`。
  - 约束：任何 time_range 查询都必须明确包含 `start` 与 `end` 且 `end > start`（与 Evidence `timeRange` 约束一致）。

- **[可观测与审计关联]**
  - `audit_log` 必须包含 `request_id`，并可据此聚合同链路事件（与 contracts 中 `requestId` 对齐）。

## 2. 具体表设计（字段/约束/索引蓝图）

> 说明：以下为“字段与约束级别的最小设计”，不涉及 ORM/迁移代码。字段类型以 Postgres 常用类型表述；实现时可在不改变语义的前提下做等价替换。

### 2.1 `dim_equipment`（设备维表）

- **[用途]** 支持设备统一查询与聚合维度；作为事实表的外键或弱关联。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `unified_equipment_id`（业务统一 ID，跨系统映射后的 ID）
  - `name`
  - `line_id`/`area`（产线/区域，用于隔离内细分）
  - `source_system`、`source_record_id`（可选：用于回溯维表来源）
  - `created_at`、`updated_at`（可选；若审计强要求也可省略 updated）
- **[约束]**
  - 唯一：`(tenant_id, project_id, unified_equipment_id)`
  - 非空：`tenant_id, project_id, unified_equipment_id, name`
- **[索引]**
  - `idx_dim_equipment_scope_unified_id`：`(tenant_id, project_id, unified_equipment_id)`
  - 可选：`idx_dim_equipment_scope_name`：`(tenant_id, project_id, name)`（支持模糊检索时再加）

### 2.2 `dim_material`（物料维表）

- **[用途]** 支持物料统一查询与成本/消耗聚合。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `unified_material_id`（业务统一 ID）
  - `name`
  - `category`（可选）
  - `source_system`、`source_record_id`（可选）
- **[约束]**
  - 唯一：`(tenant_id, project_id, unified_material_id)`
- **[索引]**
  - `idx_dim_material_scope_unified_id`：`(tenant_id, project_id, unified_material_id)`

### 2.3 `fact_production_daily`（日产量事实表）

- **[用途]** 支持“昨天二号高炉产量是多少”类查询与趋势分析。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `business_date`（date，强制：统计日期）
  - `equipment_id`（可选 FK -> `dim_equipment.id`，或存 `unified_equipment_id`；二选一需统一）
  - `quantity`（numeric/float，强制）
  - `unit`（例如 `t`）
  - `source_system`、`source_record_id`（建议，Evidence 定位）
  - `time_start`、`time_end`（可选：与 Evidence `timeRange` 对齐，且满足 end>start）
  - `extracted_at`（可选：取数时间，用于 Evidence 追溯）
- **[约束]**
  - 唯一（建议）：`(tenant_id, project_id, business_date, equipment_id)`（避免重复日汇总）
  - 检查（建议）：`quantity >= 0`
- **[索引]**
  - `idx_fact_production_daily_scope_date_equipment`：`(tenant_id, project_id, business_date, equipment_id)`
  - 若采用 `unified_equipment_id`：索引等价替换为 `(tenant_id, project_id, business_date, unified_equipment_id)`

### 2.4 `fact_energy_daily`（日能耗事实表）

- **[用途]** 支持能耗查询与与产量联动的吨钢能耗分析（L1 可先只存日能耗）。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `business_date`（date）
  - `equipment_id`（可选）
  - `energy_type`（例如 electricity/gas/steam）
  - `consumption`（numeric/float）
  - `unit`（kWh/Nm3 等）
  - `source_system`、`source_record_id`、`time_start/time_end`、`extracted_at`（建议同上）
- **[约束]**
  - 唯一（建议）：`(tenant_id, project_id, business_date, equipment_id, energy_type)`
  - 检查（建议）：`consumption >= 0`
- **[索引]**
  - `idx_fact_energy_daily_scope_date_equipment_type`：`(tenant_id, project_id, business_date, equipment_id, energy_type)`

### 2.5 `fact_cost_daily`（日成本事实表）

- **[用途]** 支持“昨天吨钢成本是多少”与成本构成分析；必须与口径版本绑定。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `business_date`（date，强制）
  - `equipment_id`（可选）
  - `cost_item`（成本项：raw_material/energy/labor/maintenance/other 等）
  - `amount`（numeric/float，强制）
  - `currency`（例如 CNY）
  - `lineage_version`（强制：引用 `metric_lineage.lineage_version`；若不做 FK，也必须同名字段以便联查）
  - `source_system`、`source_record_id`、`time_start/time_end`、`extracted_at`（建议）
- **[约束]**
  - 唯一（建议）：`(tenant_id, project_id, business_date, equipment_id, cost_item, lineage_version)`
  - 检查（建议）：`amount >= 0`
- **[索引]**
  - `idx_fact_cost_daily_scope_date_equipment_lineage`：`(tenant_id, project_id, business_date, equipment_id, lineage_version)`
  - `idx_fact_cost_daily_scope_date_cost_item`：`(tenant_id, project_id, business_date, cost_item)`

### 2.6 `fact_alarm_event`（报警/事件表）

- **[用途]** 支持“某时段报警事件”与异常追溯；天然 time_range 查询核心。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `event_time`（timestamp with time zone，强制）
  - `equipment_id`（可选）
  - `alarm_code`（字符串）
  - `severity`（字符串/枚举：info/warn/critical）
  - `message`（可选：注意脱敏；若包含敏感信息需按 RBAC 处理）
  - `source_system`、`source_record_id`（建议）
- **[约束]**
  - 非空：`event_time`
- **[索引]**
  - `idx_fact_alarm_event_scope_time`：`(tenant_id, project_id, event_time)`
  - 可选：`idx_fact_alarm_event_scope_equipment_time`：`(tenant_id, project_id, equipment_id, event_time)`

### 2.7 `fact_maintenance_workorder`（维修工单表）

- **[用途]** 支持设备维修历史查询（R3.3），并可作为建议与证据来源。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `workorder_no`（工单号，来自 EAM 或内部）
  - `equipment_id`（可选）
  - `status`（open/in_progress/closed/cancelled）
  - `created_time`（timestamp with time zone）
  - `closed_time`（timestamp with time zone，可选）
  - `fault_code`/`fault_desc`（可选，注意脱敏）
  - `source_system`、`source_record_id`（建议）
- **[约束]**
  - 唯一（建议）：`(tenant_id, project_id, workorder_no)`
  - 检查（建议）：`closed_time IS NULL OR closed_time >= created_time`
- **[索引]**
  - `idx_fact_maintenance_workorder_scope_workorder_no`：`(tenant_id, project_id, workorder_no)`
  - `idx_fact_maintenance_workorder_scope_equipment_created`：`(tenant_id, project_id, equipment_id, created_time)`

### 2.8 `metric_lineage`（指标口径仓库）

- **[用途]** 支撑“同名不同口径”治理；成本/指标计算必须绑定 `lineage_version`。
- **[关键字段]**
  - `id`（PK）
  - `tenant_id`、`project_id`（强制）
  - `metric_name`（例如 `cost_per_ton_steel`）
  - `lineage_version`（强制，字符串/整数；需稳定可追溯）
  - `formula`（建议：公式/表达式的存储形式；注意脱敏与安全）
  - `source_systems`（可选：数组/JSON，记录依赖数据源）
  - `owner`（责任人）
  - `created_at`
  - `is_active`（可选：当前是否推荐使用；历史版本仍可查）
- **[约束]**
  - 唯一（强制）：`(tenant_id, project_id, metric_name, lineage_version)`
- **[索引]**
  - `idx_metric_lineage_scope_metric_active`：`(tenant_id, project_id, metric_name, is_active)`（若启用）

### 2.9 `audit_log`（审计日志，append-only）

- **[用途]** 满足 R11.1/R11.2：记录 query/tool_call/response/error 等；按 `requestId` 聚合。
- **[关键字段（对齐 contracts 4.2）]**
  - `id`（PK；等价 `eventId`）
  - `event_type`（query/tool_call/approval/write_operation；L1 至少 query/tool_call）
  - `timestamp`
  - `request_id`（强制）
  - `tenant_id`、`project_id`（强制）
  - `session_id`（可选）
  - `user_id`、`role`
  - `resource`（访问对象/工具名/接口名）
  - `action_summary`（JSON：脱敏参数摘要）
  - `result_status`（success/failure）
  - `error_code`（可选：失败时）
  - `evidence_refs`（可选：evidenceId 列表，或 requestId 级引用）
- **[不可篡改策略（强制选型）]**
  - 首选：**DB 权限层**确保应用账户仅有 INSERT/SELECT，无 UPDATE/DELETE；审计员账户可 SELECT。
  - 备选：触发器阻断 UPDATE/DELETE（若权限体系难以落地）。
  - 不推荐：仅靠应用层约束（风险高，不满足“不可篡改”的强要求）。
- **[索引]**
  - `idx_audit_log_scope_request_time`：`(tenant_id, project_id, request_id, timestamp)`
  - `idx_audit_log_scope_time`：`(tenant_id, project_id, timestamp)`
  - 可选：`idx_audit_log_scope_event_type_time`：`(tenant_id, project_id, event_type, timestamp)`

## 3. Evidence 对齐策略（数据库如何支撑可追溯）

### 3.1 最小可追溯约定（表级）

- **[事实表 evidence 定位]**
  - 每条事实记录必须可被引用为：
    - `sourceLocator = {"table":"<table_name>","pk":"<id>"}`（概念模型；实际可以在应用层生成）
  - 若事实记录来自外部系统：
    - `sourceSystem` <= `source_system`
    - `sourceLocator` 允许扩展携带 `source_record_id`（不得包含敏感原值）。

### 3.2 time_range 查询能力

- **[事件类表]** 通过 `(tenant_id, project_id, event_time)` 索引直接支持区间查询。
- **[日事实表]** 通过 `(tenant_id, project_id, business_date, ...)` 索引支持按天范围；若需要更精细，使用 `time_start/time_end` 并建立相应索引（仅在确有需求时增加）。

## 4. 索引与性能策略（最小 + 可演进）

- **[最小原则]** 只为验收必需查询路径加索引：
  - 维表：`(tenant_id, project_id, unified_*_id)`
  - 日事实：`(tenant_id, project_id, business_date, equipment_id)`
  - 事件事实：`(tenant_id, project_id, event_time)`
  - 审计：`(tenant_id, project_id, request_id, timestamp)`
- **[分区策略（可选，按数据量启用）]**
  - `fact_alarm_event`、`audit_log` 若增长快，可按时间（例如月）分区。
  - 分区启用前提：迁移必须可回滚；且冒烟测试能验证分区存在与查询路径不回退。

## 5. 迁移与回滚策略（Task 5.2 对齐）

### 5.1 迁移工具与边界

- **[推荐]** 使用 Alembic（若后端采用 SQLAlchemy），或等价迁移体系。
- **[目录/命名（建议）]**
  - 迁移目录：`backend/**/migrations/`（以仓库实际为准）
  - 版本表：默认 Alembic 版本表；必须在同一数据库内可查询当前版本。

### 5.2 可回滚性原则（强制）

- **[强制验证]** `upgrade -> downgrade -> upgrade` 在真实 Postgres 上可重复通过。
- **[回滚边界]**
  - 允许回滚：创建/删除表、索引、约束。
  - 禁止不可逆变更：例如无法安全恢复的数据擦除型操作（本任务应避免）。

### 5.3 审计 append-only 的迁移落点

- **[必须在迁移层落地]**：权限（角色/用户）与表级权限控制，或触发器阻断更新删除。
- **[验收点]**：在冒烟测试中明确验证“UPDATE/DELETE 审计表失败”。

## 6. 数据库错误 -> 结构化错误码映射（稳定 code + 英文 message）

> 本节定义“映射策略蓝图”，实现由后续任务在应用层完成；本任务必须把映射口径写清楚，避免契约漂移。

- **[DB 连接失败]** -> `UPSTREAM_UNAVAILABLE`
  - **message（英文）** 示例：`"Postgres is unavailable"`
  - **retryable**：true
- **[查询超时]** -> `UPSTREAM_TIMEOUT`
  - message：`"Postgres query timed out"`
  - retryable：true
- **[唯一约束/重复键]** -> `CONTRACT_VIOLATION` 或 `VALIDATION_ERROR`（二选一，建议：
  - 用户输入导致冲突 -> `VALIDATION_ERROR`
  - 系统内部写入冲突/不一致 -> `CONTRACT_VIOLATION`
  ）
  - message：`"Unique constraint violation"`
  - retryable：false
- **[外键约束失败/引用不存在]** -> `VALIDATION_ERROR`
  - message：`"Foreign key constraint violation"`
  - retryable：false
- **[检查约束失败]** -> `VALIDATION_ERROR`
  - message：`"Check constraint violation"`
  - retryable：false
- **[权限不足（访问跨租户/跨项目）]**
  - 若在应用层/RBAC 检测到 -> `FORBIDDEN` 或 `AUTH_ERROR`（按接口口径）
  - message：`"Access denied"`
  - retryable：false
- **[未知 DB 异常]** -> `INTERNAL_ERROR`
  - message：`"Database error"`（避免泄露内部细节）
  - retryable：false

## 7. 测试口径（Task 5.3 对齐：Unit + Smoke，真实 Postgres）

### 7.1 单元测试（pytest -q）应覆盖的断言清单

- **[schema 可导入/可迁移]** 迁移脚本可加载并执行到目标版本。
- **[表存在性]** 9 张表全部存在。
- **[隔离字段存在性]** 每张表都存在 `tenant_id`、`project_id`。
- **[关键索引存在性]** 至少验证：
  - `fact_*` 的 `(tenant_id, project_id, business_date/event_time, ...)` 索引
  - `audit_log` 的 `(tenant_id, project_id, request_id, timestamp)` 索引
- **[关键约束]** 唯一约束（如 `metric_lineage`、维表 unified_id 等）存在。


- **[真实连接强制]** 从环境变量读取连接信息；缺失即失败（禁止 skip）。
- **[迁移链路]** 在真实 Postgres 上执行升级到目标版本。
- **[回滚验证]** 执行 `upgrade -> downgrade -> upgrade` 循环并断言版本与表/索引一致。
  - **[审计不可篡改]** 尝试 UPDATE/DELETE `audit_log` 并断言失败（错误消息需英文，便于检索）。

## 8. 全网最佳实践：本任务的推荐默认值（含引用来源）

### 8.1 多租户/多项目隔离：推荐启用 Postgres RLS（Row Level Security）作为“第二道保险”

- **[核心结论]**
  - 应用层“默认过滤 `tenant_id/project_id`”仍然必须保留。
  - 同时建议在 DB 层启用 RLS，让“漏写 WHERE 导致越权”在 DB 层直接失败（secure-by-default）。

- **[推荐做法]**
  - **使用 session 级变量（GUC）注入当前租户上下文**（例如 `app.current_tenant`），RLS policy 使用 `current_setting(...)` 读取。
  - 避免“每租户一个 DB role”的模式（可维护性与扩展性差），优先“单应用角色 + session 变量 + RLS”。

- **[RLS 常见坑（必须规避）]**
  - **表 owner 默认绕过 RLS**；必须显式启用 `ALTER TABLE ... FORCE ROW LEVEL SECURITY` 才能让 owner 也受策略约束。
  - **superuser / BYPASSRLS 角色永远绕过 RLS**；生产应用账号必须避免使用这些权限。
  - 应用连接账号 **不应是表 owner**（否则容易出现“策略没生效”的误判）。

- **[引用来源]**
  - AWS Prescriptive Guidance：基于 `current_setting('app.current_tenant')` 的 RLS 推荐示例
    - https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/rls.html
  - AWS Database Blog：强调 BYPASSRLS / owner 绕过与 `FORCE ROW LEVEL SECURITY` 等注意事项
    - https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/
  - Crunchy Data：推荐用 session variables 承载 tenant 上下文以配合连接池
    - https://www.crunchydata.com/blog/row-level-security-for-tenants-in-postgres
  - Nile：RLS 的“fail by default”安全收益与组合性（适合防止漏过滤）
    - https://www.thenile.dev/blog/multi-tenant-rls

### 8.2 审计 append-only（不可篡改）：推荐用“权限与所有者模型”落地，而不是只靠触发器

- **[核心结论]**
  - **优先选择 DB 权限模型**来保障 `audit_log` append-only：
    - 应用账号：仅 `INSERT`（写审计）+ 必要的 `SELECT`（如服务内部需要回查）；**禁止 UPDATE/DELETE**。
    - 审计员账号：仅 `SELECT`；并审计“审计查询行为”（应用层落库或单独审计事件）。
    - DDL 权限与表 owner：应由独立的迁移/DBA 角色持有，应用账号不持有。

- **[为什么不推荐只靠触发器]**
  - 触发器能记录 DML 变更，但对 **SELECT 审计无能为力**；SELECT 审计需要依赖系统日志/扩展（例如 pgaudit）或外部审计链路。
  - 任何“superuser/owner”都可以轻易篡改触发器或审计表，因此“不可篡改”的前提是 **应用账号不应拥有超权/所有权**。

- **[引用来源]**
  - PostgreSQL Wiki：触发器审计的局限（不能审计 SELECT、不能审计 DDL、owner/superuser 可绕过）以及“应用账号不应是 owner”的安全建议
    - https://wiki.postgresql.org/wiki/Audit_trigger
  - Severalnines：审计方案选型（系统日志、触发器、pgaudit 等），并提示 exhaustive logging 的成本与风险
    - https://severalnines.com/blog/postgresql-audit-logging-best-practices/

### 8.3 分区（Partitioning）：仅对高增长表按时间 RANGE 分区，并纳入回滚与运维策略

- **[适用对象]** 优先考虑：`audit_log`、`fact_alarm_event`（高写入、按时间查询/归档）。
- **[推荐策略]**
  - 以时间字段（`timestamp`/`event_time`）做 RANGE 分区（按月/按周取决于写入量与保留期）。
  - **保留期治理**：删除旧数据优先用“DROP/DETACH PARTITION”，避免逐行 DELETE。
  - 需要较少锁影响时，优先评估 `DETACH PARTITION CONCURRENTLY` 的限制与可行性。

- **[引用来源]**
  - PostgreSQL 官方文档：分区的增删维护、DETACH/CONCURRENTLY、以及 ATTACH 前通过 CHECK 约束避免扫描的建议
    - https://www.postgresql.org/docs/current/ddl-partitioning.html

### 8.4 主键选型（uuid vs bigint）：推荐“可排序的 UUID（优先）”，兼顾证据定位与写入性能

- **[本项目约束驱动]** Evidence 需要稳定定位（表 + 主键）且未来可能跨系统合并/引用，因此 uuid 的“全局唯一”优势更贴合。
- **[推荐默认值]**
  - **默认：uuid**。
  - **优先使用“时间有序”的 UUID 生成策略**（例如 UUIDv7 / 同类时间有序 ID），以降低随机 UUIDv4 在 B-Tree 索引上的页分裂与写放大风险。
  - 如果你确定“永远单库单写、只在库内产生 ID、极致写入吞吐优先”，才考虑 bigint；但这会削弱跨系统引用的一致性与可移植性。

## 9. 需要你确认的 3 个决策点（避免后续返工）

- **[主键类型]** 你希望所有表使用 `uuid` 还是 `bigint`？（最佳实践推荐：`uuid`，并优先选择时间有序 uuid 生成策略。）
- **[事实表的设备关联方式]** 事实表用 `equipment_id`（FK 到 `dim_equipment.id`）还是直接用 `unified_equipment_id`？（推荐：优先 FK，便于一致性；若更看重松耦合与快速落地，可先 unified_id。）
- **[审计 append-only 落地方式]** 你更偏好：
  - DB 权限策略（最佳实践推荐，合规更强；也更符合“owner/superuser 可绕过触发器审计”的安全现实）
  - 还是触发器阻断 UPDATE/DELETE（更自包含，但维护成本更高，且不解决 SELECT 审计）

 ## 10. 已确认的最终决策（可直接驱动后续子任务实现）

 - **[主键类型]** `uuid`（尽量采用时间有序生成策略；具体实现由后续子任务按仓库依赖选型）
 - **[隔离]** 应用层默认过滤 `tenant_id/project_id` + DB 层启用 RLS 兜底
 - **[事实表设备关联]** 选择 **1A**：事实表使用 `equipment_id` 外键（FK -> `dim_equipment.id`）
 - **[审计 append-only]** 选择 DB 权限 + 所有者模型（应用账号不为 owner，且禁止 UPDATE/DELETE）
 - **[分区]** 选择 **2A**：初始迁移即对 `audit_log` 与 `fact_alarm_event` 按时间做 RANGE 分区；保留期清理优先 DROP/DETACH PARTITION
