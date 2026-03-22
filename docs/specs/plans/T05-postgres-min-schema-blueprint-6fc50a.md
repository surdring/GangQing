# T05（L1）Postgres 最小数据模型：执行蓝图与验收口径

本蓝图用于在 L1（最小闭环：只读查询）阶段定义并规划一套“可迁移、可回滚、可审计、可隔离、可支撑 Evidence”的最小 Postgres 数据模型，并明确子任务执行顺序与可自动化验收口径。

## 1. 范围与非目标

### 1.1 范围（L1 必需）

- **维表**：`dim_equipment`、`dim_material`
- **事实表**：`fact_production_daily`、`fact_energy_daily`、`fact_cost_daily`、`fact_alarm_event`、`fact_maintenance_workorder`
- **口径仓库**：`metric_lineage`、`metric_lineage_scenario_mapping`
- **审计表**：`audit_log`

### 1.2 非目标（本任务禁止/不覆盖）

- 不输出任何迁移脚本/SQL/ORM 代码片段。
- 不引入任何业务写能力（除审计表 append-only 写入属于“存证写入”，不等价于业务写操作）。
- L1 不将 PostgreSQL RLS 作为硬依赖（详见 4.4），不以启用/正确配置 RLS 作为阻塞迁移的前置条件。

## 2. 权威参考与现状基线（对齐仓库事实）

### 2.1 权威参考

- `docs/design.md`：2.6 数据层、2.8 审计、2.9 配置外部化、4.4.1 RLS 决策
- `docs/contracts/api-and-events-draft.md`：ErrorResponse、Evidence、Audit Event 最小契约
- `docs/tasks.md`：任务 5 范围与验证命令
- `.env.example`：`GANGQING_DATABASE_URL` 与超时/健康检查配置

### 2.2 当前迁移/测试基线（已存在）

- 迁移链路（Alembic）：
  - `0001_init_min_schema`
  - `0002_metric_lineage`（lineage_version semver + active unique）
  - `0003_ml_scn_map`（scenario mapping）
- 冒烟脚本：`backend/scripts/postgres_schema_smoke_test.py`
  - 强制真实 Postgres
  - 强制 `upgrade -> downgrade -> upgrade`
  - 断言表/索引/约束/分区/pgcrypto/审计 append-only

备注：`reports/` 目录当前未发现与 T05 schema 直接对应的验收日志文件（仅有 T09 contract validation 相关）。本任务计划的验收材料应在后续落盘到 `reports/`（不在本“规划-only”产物内落盘）。

## 3. 全局强制约束（L1）

### 3.1 隔离（Isolation）

- **强制字段**：所有业务表（维表/事实表/口径仓库/审计表）必须包含：
  - `tenant_id`（string/text，NOT NULL）
  - `project_id`（string/text，NOT NULL）
- **查询默认过滤**：应用层所有查询必须默认叠加 `tenant_id`、`project_id`；检测到跨域访问必须拒绝并审计。
- **索引覆盖**：所有高频查询路径的索引必须把 `(tenant_id, project_id, ...)` 作为前缀。

### 3.2 Evidence-First（数值事实可追溯）

- 所有数值类事实必须能够：
  - 定位到**具体表**与**稳定主键**（`table` + `primary_key`）
  - 支持按 `time_range`（窗口）过滤
- **来源预留**：维表与事实表均预留：
  - `source_system`（可空）
  - `source_record_id`（可空）

### 3.3 结构化错误（DB 相关）

- DB 相关错误必须映射到稳定错误码与英文 `message`，并可与对外契约一致（至少 `code/message/requestId/retryable/details?`）。
- 错误码枚举需对齐 `docs/contracts/api-and-events-draft.md` 的最小集合；DB 层允许存在更细分内部码，但对外必须收敛映射。

### 3.4 配置外部化

- Postgres 连接串必须来自环境变量：`GANGQING_DATABASE_URL`（缺失即快速失败）。
- 超时、健康检查、连接池策略等不得硬编码。

### 3.5 真实集成测试（No Skip）

- 冒烟/回滚验证必须连接真实 Postgres；缺少配置必须失败；禁止跳过。

## 4. 表级契约（最小字段清单 + 约束 + 索引意图）

> 说明：以下为“对外可审计/可迁移/可隔离/可支撑 Evidence”的最小字段集与约束意图；不包含任何实现代码。

### 4.1 维表

#### 4.1.1 `dim_equipment`

- **用途**：设备统一实体（跨系统统一 ID 的最小落点）。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`（NOT NULL）。
- **业务键**：`unified_equipment_id`（NOT NULL）。
- **最小字段**：
  - `name`（NOT NULL）
  - `line_id`（可空）
  - `area`（可空）
  - `source_system`/`source_record_id`（可空）
  - `created_at`、`updated_at`（NOT NULL，服务端默认填充）
- **唯一性约束**：`(tenant_id, project_id, unified_equipment_id)`。
- **索引意图**：支持 `scope + unified_equipment_id` 查询。

#### 4.1.2 `dim_material`

- **用途**：物料统一实体。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`。
- **业务键**：`unified_material_id`。
- **最小字段**：
  - `name`（NOT NULL）
  - `category`（可空）
  - `source_system`/`source_record_id`（可空）
  - `created_at`、`updated_at`（NOT NULL）
- **唯一性约束**：`(tenant_id, project_id, unified_material_id)`。
- **索引意图**：支持 `scope + unified_material_id` 查询。

### 4.2 口径仓库（Metric Lineage Repository）

#### 4.2.1 `metric_lineage`

- **用途**：指标定义/口径版本仓库；计算类结论必须绑定 `lineage_version`。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`。
- **最小字段**：
  - `metric_name`（NOT NULL）
  - `lineage_version`（NOT NULL，建议 semver `MAJOR.MINOR.PATCH`）
  - `status`（NOT NULL，默认 `active`；用于展示/治理）
  - `formula`（可空）
  - `source_systems`（可空，JSON 数组/对象的摘要）
  - `owner`（可空）
  - `created_at`（NOT NULL）
  - `is_active`（NOT NULL，默认 true；用于“唯一活跃版本”约束）
- **唯一性约束**：`(tenant_id, project_id, metric_name, lineage_version)`。
- **版本化策略**：
  - **变更即新版本**：任意口径/公式/数据源变化 => 新 `lineage_version` 记录。
  - **活跃版本唯一**：同一 scope + metric_name 在任意时刻最多一个 `is_active=true`。
- **索引意图**：
  - 支持按 `scope + metric_name + lineage_version` 精确检索。
  - 支持按 `scope + metric_name` 找到当前活跃版本（部分索引/唯一约束）。

#### 4.2.2 `metric_lineage_scenario_mapping`

- **用途**：将业务场景（`scenario_key`）映射到默认 `lineage_version`，减少前端/编排层必须显式指定版本的交互成本。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`。
- **最小字段**：
  - `metric_name`（NOT NULL）
  - `scenario_key`（NOT NULL）
  - `lineage_version`（NOT NULL）
  - `status`（NOT NULL，默认 `active`）
  - `owner`（可空）
  - `created_at`（NOT NULL）
  - `is_active`（NOT NULL，默认 true；用于“同场景唯一活跃映射”）
- **唯一性约束**：`(tenant_id, project_id, metric_name, scenario_key, lineage_version)`。
- **活跃唯一策略**：同一 `(scope, metric_name, scenario_key)` 在任意时刻最多一个 `is_active=true`。
- **索引意图**：支持 `scope + metric_name + scenario_key` 快速找到默认版本。

### 4.3 事实表（Facts）

#### 4.3.1 `fact_production_daily`

- **用途**：日产量（可用于趋势、对比、汇总）。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`。
- **时间轴**：`business_date`（DATE，NOT NULL）
  - 可选窗口：`time_start`/`time_end`（TIMESTAMPTZ，可空，用于 Evidence timeRange 与更细粒度窗口）
- **关联维度**：`equipment_id`（可空，引用 `dim_equipment.id`；RESTRICT）
- **最小事实字段**：
  - `quantity`（NUMERIC，NOT NULL，`>=0`）
  - `unit`（NOT NULL）
  - `source_system`/`source_record_id`（可空）
  - `extracted_at`（可空；用于 Evidence extracted_at）
  - `created_at`（NOT NULL）
- **唯一性约束**：`(tenant_id, project_id, business_date, equipment_id)`。
- **索引意图**：支持 `scope + date_range (+ equipment)`。

#### 4.3.2 `fact_energy_daily`

- **用途**：日能耗（按能源类型）。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`。
- **时间轴**：`business_date`（DATE）+ 可选 `time_start/time_end`。
- **关联维度**：`equipment_id`（可空，RESTRICT）。
- **最小事实字段**：
  - `energy_type`（NOT NULL）
  - `consumption`（NUMERIC，NOT NULL，`>=0`）
  - `unit`（NOT NULL）
  - `source_system`/`source_record_id`、`extracted_at`、`created_at`
- **唯一性约束**：`(tenant_id, project_id, business_date, equipment_id, energy_type)`。
- **索引意图**：支持 `scope + date_range + equipment + energy_type`。

#### 4.3.3 `fact_cost_daily`

- **用途**：日成本事实（成本项拆分），**强制绑定口径版本**。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`。
- **时间轴**：`business_date`（DATE）+ 可选 `time_start/time_end`。
- **关联维度**：`equipment_id`（可空，RESTRICT）。
- **最小事实字段**：
  - `cost_item`（NOT NULL）
  - `amount`（NUMERIC，NOT NULL，`>=0`）
  - `currency`（NOT NULL）
  - `lineage_version`（NOT NULL；Evidence/Lineage 对齐关键）
  - `source_system`/`source_record_id`、`extracted_at`、`created_at`
- **唯一性约束**：`(tenant_id, project_id, business_date, equipment_id, cost_item, lineage_version)`。
- **索引意图**：
  - `scope + date_range + equipment + lineage_version`
  - `scope + date_range + cost_item`

#### 4.3.4 `fact_alarm_event`（高频事件）

- **用途**：报警/事件流（可用于时间对齐、异常追溯）。
- **隔离字段**：`tenant_id`、`project_id`。
- **时间轴**：`event_time`（TIMESTAMPTZ，NOT NULL）
- **主键策略**：`(id, event_time)` 复合主键（支持分区表）。
- **关联维度**：`equipment_id`（可空，RESTRICT）。
- **最小事实字段**：
  - `alarm_code`（可空）
  - `severity`（可空）
  - `message`（可空；注意与对外错误 message 无关）
  - `source_system`/`source_record_id`
  - `created_at`
- **分区策略（L1 最小）**：RANGE 按 `event_time` 分区；至少存在一个默认分区（例如 `p0`）保障可写入/可测试。
- **索引意图**：
  - `scope + event_time`（time_range 查询）
  - `scope + equipment_id + event_time`

#### 4.3.5 `fact_maintenance_workorder`

- **用途**：维修工单（设备诊断、维修历史）。
- **主键**：`id`（UUID）。
- **隔离字段**：`tenant_id`、`project_id`。
- **时间轴**：`created_time`（TIMESTAMPTZ，NOT NULL）
- **最小事实字段**：
  - `workorder_no`（NOT NULL；业务唯一键）
  - `status`（NOT NULL）
  - `closed_time`（可空，且 `closed_time >= created_time`）
  - `fault_code`/`fault_desc`（可空）
  - `source_system`/`source_record_id`、`created_at`
- **唯一性约束**：`(tenant_id, project_id, workorder_no)`。
- **索引意图**：
  - `scope + workorder_no`
  - `scope + equipment_id + created_time`

### 4.4 审计表（Append-only，主存证）

#### 4.4.1 `audit_log`

- **用途**：审计事件主存证；支持按 `request_id` 聚合导出事件链。
- **隔离字段**：`tenant_id`、`project_id`（NOT NULL）。
- **时间轴**：`timestamp`（TIMESTAMPTZ，NOT NULL，默认 now）。
- **主键策略**：`(id, timestamp)` 复合主键（支持分区表）。
- **最小字段**（对齐 contracts 4.2）：
  - `event_type`（NOT NULL；至少覆盖 `query/tool_call`；L4 预留 `approval/write_operation`）
  - `request_id`（NOT NULL；必须贯穿）
  - `session_id`（可空）
  - `user_id`、`role`（可空）
  - `resource`（可空）
  - `action_summary`（可空，JSON；必须脱敏）
  - `result_status`（NOT NULL；`success|failure`）
  - `error_code`（可空；失败时记录稳定码）
  - `evidence_refs`（可空，JSON 数组；evidenceId 列表）
- **分区策略（L1 最小）**：RANGE 按 `timestamp` 分区；至少存在默认分区（例如 `p0`）。
- **索引意图**：
  - `scope + request_id + timestamp`
  - `scope + timestamp`
  - `scope + event_type + timestamp`

#### 4.4.2 Append-only 不可篡改策略（必须可执行/可验证）

- **策略选择（L1 采用双保险）**：
  - DB 侧：触发器阻断 UPDATE/DELETE（可在默认分区上验证）
  - 权限层：应用账号仅授予 `SELECT/INSERT`；禁止 `UPDATE/DELETE/DDL`
- **验证口径**：冒烟脚本必须能证明 UPDATE/DELETE 被阻断（且不会污染测试数据）。

### 4.5 RLS（L1 决策）

- **决策**：L1 阶段不把 RLS 作为硬依赖；主策略为应用层默认过滤 + 跨域拒绝 + 可审计。
- **兼容现状**：当前迁移中已包含 RLS policy（依赖会话 GUC：`app.current_tenant`、`app.current_project`）。
  - L1 蓝图要求：应用层必须保证不依赖 RLS 的“正确性”来实现隔离（即使未来关闭/未配置 RLS，也必须通过应用层过滤保证隔离）。
  - L2+ 预留：若启用 RLS 作为第二道防线，需要明确连接生命周期内设置会话变量的责任边界与审计。

## 5. Evidence 对齐规则（从 DB 到 Evidence）

### 5.1 Evidence.sourceLocator（最小可定位）

- 事实表/维表证据最小定位：
  - `table=<table_name>`
  - `primary_key=<id>`（或分区表的 `id`）
- 若存在来源系统：增加 `source_system/source_record_id` 以便回查。

### 5.2 Evidence.timeRange（强制）

- 日粒度事实（production/energy/cost）：
  - timeRange 优先使用 `time_start/time_end`（若存在且合法）；否则使用 `business_date` 映射为 **UTC 自然日窗口**。
- 事件事实（alarm/workorder）：
  - timeRange 以 `event_time` 或 `created_time` 为锚点；窗口大小由查询模板/产品交互定义（例如 ±0 或上下文窗口）。

### 5.3 口径绑定

- `fact_cost_daily.lineage_version` 必须可在 `metric_lineage` 中找到对应记录；若找不到应在上层映射为 `EVIDENCE_MISSING`。

## 6. 迁移与回滚策略（规划口径）

### 6.1 工具与目录（权威路径）

- 迁移目录：`backend/migrations/**`
- Alembic 配置：`backend/alembic.ini`
- DB 访问模块：`backend/gangqing_db/**`

### 6.2 可回滚性（强制验收）

- 必须提供自动化证据：`upgrade -> downgrade -> upgrade` 循环成功。
- 回滚失败必须映射为稳定错误码（建议 `MIGRATION_ROLLBACK_FAILED`/对外映射策略见 7）。

## 7. DB 错误映射原则（对齐 contracts）

### 7.1 映射目标

- 对外：统一 `ErrorResponse`（`code/message(英文)/requestId/retryable/details?`）。
- details：仅允许结构化摘要，禁止泄露连接串、SQL、rows、堆栈。

### 7.2 建议映射表（L1 最小）

- **配置缺失**：`CONFIG_MISSING`（对外允许暴露；英文 `message` 必须可检索）。
- **连接失败/不可达**：`UPSTREAM_UNAVAILABLE`（retryable=true）
- **查询超时/取消**：`UPSTREAM_TIMEOUT`（retryable=true）
- **唯一/外键/CHECK 约束冲突**：`VALIDATION_ERROR`（retryable=false）
- **迁移失败**：`MIGRATION_FAILED`（对外允许暴露；英文 `message` 必须可检索）

> 备注：既然允许对外暴露 `CONFIG_MISSING`、`MIGRATION_FAILED` 等 code，则必须在 `docs/contracts/api-and-events-draft.md` 的错误码枚举中补齐它们（并明确 HTTP 状态码映射规则），避免契约漂移。

## 8. 验收口径（自动化，可复制执行）

### 8.1 单元测试（Unit）

- 命令：`pytest -q`
- 覆盖要点：
  - 迁移模块可导入
  - 结构化错误映射（英文 message + 稳定 code + requestId 透传）
  - 配置缺失快速失败（缺 `GANGQING_DATABASE_URL` 必须失败）

### 8.2 冒烟测试（Smoke，真实 Postgres）

- 命令：`backend/scripts/postgres_schema_smoke_test.py`
- 覆盖要点（必须全部 PASS）：
  - upgrade/downgrade/upgrade 循环
  - 期望 head 版本一致
  - 表/列/主键/唯一/外键/CHECK/索引存在
  - 索引覆盖隔离字段（tenant_id/project_id）
  - 分区表与默认分区存在
  - pgcrypto 扩展存在
  - 审计 append-only（UPDATE/DELETE 被阻断）

## 9. 子任务执行蓝图（Task 5.1~5.3）

### 9.1 Task 5.1（表结构与索引）

- **产物**：逐表字段/约束/索引/分区策略确认单（以本蓝图第 4 章为准）。
- **关键检查**：
  - 每张表都含 `tenant_id/project_id`
  - 每张事实表都有可用于 time_range 的时间轴字段
  - 每张事实表都有可引用的稳定主键（UUID）

### 9.2 Task 5.2（迁移与回滚策略）

- **产物**：迁移链路与回滚可验证证据（以 8.2 冒烟脚本为准）。
- **关键检查**：upgrade->downgrade->upgrade 必须稳定。

### 9.3 Task 5.3（测试口径与证据）

- **产物**：
  - 单测 + 冒烟测试通过的可追溯输出
  - （后续）`reports/YYYY-MM-DD_T05_postgres-schema.md` 验收日志（包含命令与 PASS 证据）

## 10. 已确认的关键决策（L1）

1. **业务时区策略**：`business_date` 映射到 Evidence.timeRange 时，统一按 **UTC 自然日**。
2. **severity/status 枚举**：在 L1 就引入 CHECK 枚举约束。
3. **对外错误码暴露**：允许对外暴露 `CONFIG_MISSING`、`MIGRATION_FAILED` 等内部码（并要求 contracts 同步枚举与状态码映射）。

### 10.1 枚举值清单（契约化，L1）

#### 10.1.1 `fact_alarm_event.severity`

- **允许值**：`low | medium | high | critical`
- **空值策略**：允许为 `NULL`（当来源系统未提供严重度时），但若不为空必须满足允许值集合。

#### 10.1.2 `fact_maintenance_workorder.status`

- **允许值**：`open | in_progress | closed | cancelled`
- **空值策略**：不允许为 `NULL`（最小闭环要求工单必须有可归档状态）。

