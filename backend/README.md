# backend

本目录仅用于承载 Postgres schema 迁移与测试脚本（Task 5.1）。

## 分区表维护指南

本仓库在初始化迁移中对以下表启用 RANGE 分区（按时间字段）：

- `audit_log`（`timestamp`）
- `fact_alarm_event`（`event_time`）

### 新增分区（示例）

以“按月分区”为例，新增 2026-03 的分区（注意：示例 SQL 需要在具备 DDL 权限的迁移/DBA 账号下执行）：

```sql
CREATE TABLE audit_log_2026_03
PARTITION OF audit_log
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE fact_alarm_event_2026_03
PARTITION OF fact_alarm_event
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

### 归档/删除旧分区（推荐）

优先使用分区级操作，避免逐行 `DELETE`：

- **直接删除**（不可恢复）：

```sql
DROP TABLE IF EXISTS audit_log_2024_01;
DROP TABLE IF EXISTS fact_alarm_event_2024_01;
```

- **先分离再归档**（可将分区迁移到冷库/对象存储后再删除）：

```sql
ALTER TABLE audit_log DETACH PARTITION audit_log_2024_01;
ALTER TABLE fact_alarm_event DETACH PARTITION fact_alarm_event_2024_01;
```

### 注意事项

- 分区维护操作属于 **写操作/DDL**，必须遵循项目的审批与审计要求。
- 若启用了 RLS，新增分区表后应确认其继承了父表的 RLS 配置与策略（Postgres 的分区表行为以实际版本为准，建议在冒烟脚本中做 schema 级断言）。
- 若未来将“创建新分区”自动化，建议通过迁移脚本/运维脚本统一管理，并为其补齐回滚策略。
