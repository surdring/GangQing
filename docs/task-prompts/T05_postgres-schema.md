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

# References
- PRD: docs/requirements.md（R7.1/R11.1/R11.2）
- TDD: docs/design.md（2.6.1/2.8.1）
- tasks: docs/tasks.md（任务 5）

# Execution Plan
1) Task 5.1（表结构与索引）
- 维表：设备/物料。
- 事实表：产量/能耗/成本/报警事件/维修工单。
- 元数据表：指标口径仓库（metric_lineage）、审计日志（audit_log）。

2) Task 5.2（迁移与回滚策略）
- 迁移必须可回滚；验证 upgrade->downgrade->upgrade（如采用 Alembic）。

3) Task 5.3（测试口径）
- 单元测试：模型/迁移脚本可导入与基础约束。
- 冒烟测试：真实 DB 中验证表/索引存在。

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

# Critical Rules
- **Isolation**: 所有核心表包含 scope 字段，并具备索引支持过滤。
- **只读默认**: 该任务只涉及数据库 schema 迁移，不引入业务写操作能力。
- **真实集成测试（No Skip）**: 冒烟脚本必须连接真实 Postgres，配置缺失必须失败。

# References
- PRD: docs/requirements.md（R7.1）
- tasks: docs/tasks.md（5.1）

# Execution Plan
1) 新增迁移脚本：创建表与索引。
2) 确保审计表 append-only 语义（至少通过应用层约束 + 权限控制策略）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/postgres_schema_smoke_test.py`
- **Rollback**（如适用）: 验证 upgrade->downgrade->upgrade 成功。

# Output Requirement
输出所有新增/修改文件完整内容 + 测试命令与关键输出。
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
