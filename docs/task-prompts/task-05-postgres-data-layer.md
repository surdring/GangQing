# Task 5 - 建设 Postgres 数据层（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 5 组任务：建设 Postgres 数据层（最小数据模型 + 可复现造数 + 异常/边界覆盖）。
你的角色是 **技术负责人/架构师**。
你的目标是定义最小数据模型、造数策略、迁移/回滚要求、以及与 Evidence/审计联动的验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Evidence-First**: 后续所有数值结论必须能映射到数据源与时间范围；数据层必须支持该追溯。
- **Schema 单一事实源**: 对外 I/O/Evidence/审计事件用 Pydantic；前端用 Zod。
- **RBAC + 审计 + requestId**: 数据访问必须可按角色限制字段/域，并可审计。
- **配置外部化**: Postgres DSN/连接池/超时不得硬编码。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实 Postgres；缺配置必须失败并输出英文错误。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#40-47）
- TDD: `docs/技术设计文档-最佳实践版.md`（#8、#8.3）
- tasks: `docs/tasks.md`（Task 5）

# Execution Plan
1) Task 5.1 - 最小数据模型与表清单
- 设备/物料维表、产量/能耗/成本事实表、报警事件、维修工单、指标口径、审计日志。

2) Task 5.2 - 造数脚本（可复现）
- 固定种子、可重复生成；包含缺失/延迟/极端波动数据用于降级与 guardrail 验证。

3) Task 5.3 - 迁移与回滚策略（如采用 Alembic）
- 若引入迁移工具，必须验证 upgrade/downgrade 循环。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/postgres_seed_and_query_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 5.1 - 定义 Postgres 最小数据模型（迁移/建表）

```markdown
# Context
你正在执行子任务：5.1 - 定义 Postgres 最小数据模型。
你的目标是创建最小表结构，覆盖 L1 场景（成本/产量/能耗/报警/维修/口径/审计）。

# Critical Rules
- **Read-Only Default**: 工具层默认只读，但数据层允许建表/造数属于工程初始化，不属于业务写操作闭环。
- **Evidence-First**: 表字段设计必须支持 time_range、lineage_version 追溯。
- **真实集成测试（No Skip）**: 必须连接真实 Postgres 执行迁移/建表。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#8.3）
- tasks: `docs/tasks.md`（Task 5）

# Execution Plan
1) 选择迁移方式（Alembic 或 SQL 脚本）并外部化配置。
2) 建表并补齐必要索引。
3) 定义与审计/证据链相关的关键字段（时间、版本、来源）。

# Verification
- 冒烟：建表成功且可查询。

# Output Requirement
- 输出迁移/SQL、配置与测试脚本。
```

### Task 5.2 - 造数脚本：固定种子、可复现、含异常边界

```markdown
# Context
你正在执行子任务：5.2 - 造数脚本。
你的目标是生成可复现测试数据，覆盖正常与异常边界（缺失、延迟、极端波动）。

# Critical Rules
- **Evidence-First**: 数据必须能支持“不可验证降级”与 guardrail 的测试场景。
- **真实集成测试（No Skip）**: 造数必须写入真实 Postgres。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#8.2）
- tasks: `docs/tasks.md`（Task 5）

# Execution Plan
1) 设计固定 seed 与数据集版本号。
2) 写入维表与事实表。
3) 注入异常样本：缺失、延迟、重复、极端值。

# Verification
- 冒烟：`backend/scripts/postgres_seed_and_query_smoke_test.py` 成功且能查询到异常样本。

# Output Requirement
- 输出造数脚本与冒烟测试。
```

### Task 5.3 - 冒烟测试：seed + query（真实 Postgres）

```markdown
# Context
你正在执行子任务：5.3 - seed + query 冒烟测试。
你的目标是实现 `backend/scripts/postgres_seed_and_query_smoke_test.py`，验证真实数据库可用、造数可跑、关键查询可执行。

# Critical Rules
- **真实集成测试（No Skip）**: 缺少 Postgres 配置或连接失败，测试必须失败并给出英文错误。
- **配置外部化**: DSN/超时不得硬编码。

# References
- tasks: `docs/tasks.md`（Task 5）

# Execution Plan
1) 读取配置并连接数据库。
2) 执行 seed。
3) 执行关键查询并断言结果结构。

# Verification
- `pytest -q` 通过。
- 冒烟脚本运行通过。

# Output Requirement
- 输出脚本与相关配置/测试。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（通过数据层设计支持追溯）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（作为硬约束写入）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
