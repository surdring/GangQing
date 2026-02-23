# T06 可复现造数脚本：执行蓝图

本蓝图定义可复现 Postgres 造数数据集的覆盖范围、可追溯策略与异常/边界样本矩阵，使其可被冒烟/回归测试统一复用并支持 Evidence/降级/guardrail 验证。

## 1. 背景与目标

- **需求/设计约束**
  - 造数脚本必须满足 `docs/requirements.md#R7.2`（可复现 + 核心场景 + 异常/边界）。
  - 必须满足 `docs/requirements.md#R2.2` 与 `docs/design.md#3.3` 的 Evidence-First：可定位到**表/主键/时间范围**。
  - 必须满足 `docs/design.md#7.2` 的“真实集成测试”：冒烟测试连接**真实 Postgres**，禁止 skip/mocking；缺配置必须失败。
  - 必须满足 `docs/design.md#2.9` 的“配置外部化”：种子/规模/时间范围参数化，禁止硬编码。

- **任务 6 的产出定义（规划口径）**
  - 造数脚本（seed data generator）可在真实 Postgres 上生成一套“**可复现数据集**”，覆盖：
    - 成本、产量、能耗、故障/报警、维修工单。
    - 异常/边界：缺失值、延迟到达、重复记录、极端波动。
  - 数据集可被：
    - **单元测试**（`pytest -q`）使用：主要验证“确定性、参数校验、数据边界约束、证据定位字段是否齐备”。
    - **冒烟测试**（`backend/scripts/seed_data_smoke_test.py`）使用：端到端写入并可查询验证（真实 Postgres）。

## 2. 数据覆盖范围（表级清单）

以 `docs/design.md#2.6.1` 的最小数据模型为准，造数覆盖以下表：

- 维度表
  - `dim_equipment`
  - `dim_material`
- 事实表
  - `fact_production_daily`
  - `fact_energy_daily`
  - `fact_cost_daily`
  - `fact_alarm_event`
  - `fact_maintenance_workorder`
- 元数据/治理表
  - `metric_lineage`（用于成本/指标口径版本绑定与冲突/缺失场景）
- 审计表
  - `audit_log` **不由造数脚本直接写入**（保持只由系统审计链路写入的语义），但数据集设计需考虑其在后续 E2E 链路中的可查询性。

### 2.1 统一隔离字段口径（强制）

所有造数写入都必须显式指定：

- `tenant_id`
- `project_id`

原因：当前 schema 与测试基线强制要求隔离字段存在且 RLS 强制（见 `backend/tests/test_postgres_schema.py` 与 `backend/scripts/postgres_schema_smoke_test.py`）。

建议：数据集默认生成至少 2 组隔离域：

- `t1/p1`（主回归域）
- `t2/p2`（跨域隔离验证域，用于未来的越权/跨域测试）

以上两组隔离域为默认生成口径。

## 3. 可复现性与版本可追溯策略（Task 6.1）

### 3.1 “同种子同数据”的确定性策略

- **确定性输入**（全部参数化）
  - `seed`：随机种子
  - `dataset_id`：数据集 ID（建议是稳定字符串，如 `baseline-v1`）
  - `dataset_version`：数据集版本（语义版本或日期版本）
  - `start_date` / `end_date`：业务日期窗口（影响 *daily* 事实表的行数）
  - `scale`：规模系数（影响设备数、物料数、每日记录数、事件密度）
  - `tenant_ids` / `project_ids`：隔离域集合

- **确定性输出**
  - 对同一 `(seed, dataset_id, dataset_version, start_date, end_date, scale, tenants/projects)`：
    - 生成的每一行的主键、业务日期、关键数值字段应一致。

### 3.2 版本变更可追溯

建议将“版本”拆为两层：

- **脚本版本**：从代码版本（git commit）侧追溯（由 CI/日志/运行记录提供）。
- **数据集版本**：由运行参数显式声明并写入数据库的“运行记录”（见下）。

### 3.3 运行记录与证据链定位（Evidence-First）

为了满足“可定位到表/主键/时间范围”，造数需要具备**可被证据链引用的定位信息**。

- **最小证据定位字段（每条记录）**
  - `table_name`（隐含：所在表）
  - `primary_key`：表主键字段（如 `id`，或复合主键）
  - `business_time_range`：
    - daily 表：`business_date` 可映射为 `[date, date]`
    - event 表：`event_time` 可映射为 `[event_time, event_time]`

- **建议新增“dataset_run 运行记录表”的策略（不在本任务实现，仅定义口径）**
- **运行记录输出策略（本任务口径）**
  - 不新增运行记录表。
  - 冒烟测试与/或造数脚本在运行后输出一份 **row counts + 参数回显** 的结构化摘要到 stdout（可作为证据/可追溯记录的一部分）。

> 备注：本任务蓝图不要求立即改 schema，但需要先明确“证据链展示要引用哪些字段”。

## 4. 数据集分层与命名（baseline + anomaly packs）

为避免“一个数据集既要稳定回归又要覆盖所有异常”导致难以维护，建议分层：

- **Baseline Pack（默认回归集）**
  - 目标：稳定、覆盖核心查询路径。
  - 内容：完整维表 + 90 天 daily 事实 + 少量事件/工单。

Baseline 默认窗口长度的作用：

- **对可测性的影响**：窗口越长，越容易覆盖“趋势/对比/环比/异常波动”等场景，尤其是 spike/变化率类异常的稳定触发。
- **对性能与稳定性的影响**：窗口越长，写入与查询越慢，CI 与本地冒烟测试的执行时间与波动更大。
- **对随机性噪声的影响**：窗口越短，小样本下偶然波动更明显，可能导致异常检测类断言不够稳定。

- **Anomaly Packs（异常包，可按开关启用）**
  - 目标：触发降级/guardrail/数据质量评分/一致性拒答策略。
  - 内容：在 baseline 基础上叠加异常样本（见第 5 节矩阵）。

每个 pack 都必须：

- 可通过参数开关启用/禁用（配置外部化）。
- 在启用时仍保持确定性（同 seed 下异常注入位置与数值一致）。

## 5. 异常/边界样本矩阵（Task 6.2）

下表定义“要生成什么异常”以及“用于验证什么系统行为”。这里的“验证行为”用于指导未来 `seed_data_smoke_test.py` 与相关 guardrail/降级测试。

### 5.1 缺失值（Missing Values）

- **样本定义**
  - daily 事实表中：关键数值字段出现 NULL（例如 `quantity/consumption/amount`）
  - 维表中：可选属性缺失（不破坏主键/唯一约束）

- **覆盖表**
  - `fact_production_daily`
  - `fact_energy_daily`
  - `fact_cost_daily`

- **预期验证点**
  - Evidence 中必须能指出缺失发生在哪些表/哪些主键/哪些日期。
  - 对“数值类结论”应触发“不确定/降级”路径（对应 `docs/requirements.md#R14.4` 与 `docs/design.md#5.1.2`）。

### 5.2 延迟到达（Late Arriving Data）

- **样本定义**
  - 同一 `business_date` 的数据在 `created_at` 上表现为“明显晚到”（例如晚于业务日数天）。

- **覆盖表**
  - `fact_production_daily`
  - `fact_energy_daily`
  - `fact_cost_daily`

- **预期验证点**
  - 证据链中的 `extracted_at` 与记录的 `created_at` 可对比，支持“数据延迟提示/质量评分”。

### 5.3 重复记录（Duplicates）

- **样本定义**
  - 制造“业务语义重复但不违反唯一约束”的重复：
    - 例如同一设备同一天出现两条 production 记录，但通过不同 `id` 区分（不触碰唯一约束时）；或在允许的维度上做重复。
  - 或者制造“本应唯一但出现重复”的场景：
    - **注意**：若直接违反 DB unique 约束会导致写入失败，适合作为“造数脚本错误路径/回滚验证”，但不适合作为默认 anomaly pack。

- **覆盖表**
  - `fact_production_daily`
  - `fact_energy_daily`

- **预期验证点**
  - 触发一致性冲突提示：降级为“展示冲突数据与来源”，不得编造单一正确值（见 `docs/design.md#5.6`）。

### 5.4 极端波动（Spikes / Step Changes）

- **样本定义**
  - 在连续日序列中注入突增/突降（例如成本或能耗突然跃迁），满足“变化率异常”。

- **覆盖表**
  - `fact_energy_daily`
  - `fact_cost_daily`
  - 可选：`fact_production_daily`（产量异常波动）

- **预期验证点**
  - 触发 guardrail 或降级策略验证（对应 `docs/requirements.md#R14.4` 与 `docs/design.md#5.1.3` 的 L3+ 一致性/变化率校验预留）。
  - Evidence 必须定位到异常日期范围与对应记录主键集合。

### 5.5 维表缺映射 / 引用缺失（EVIDENCE_MISMATCH / EVIDENCE_MISSING 预埋）

- **样本定义**
  - 事实表引用一个不存在的维表 ID：会触发 FK 约束失败，适合作为“写入失败路径”验证。
  - 更推荐：制造“语义映射缺失”的异常：
    - `dim_equipment` 中存在设备，但缺少统一 ID 映射字段的可用值或映射冲突（需在不违反当前 schema 约束的前提下设计）。

- **覆盖表**
  - `dim_equipment`
  - `fact_*`（间接体现）

- **预期验证点**
  - 后续语义层/证据链可触发 `EVIDENCE_MISMATCH` 或 `EVIDENCE_MISSING` 的拒答/降级。

### 5.6 事件/工单边界

- **样本定义**
  - `fact_alarm_event`：
    - 同一设备短时间内大量事件（事件风暴）
    - 不同 severity/类型分布
  - `fact_maintenance_workorder`：
    - 长周期未关闭工单
    - `closed_time < created_time` 的“非法”样本应由 DB check 约束阻止（用于写入失败路径验证）

- **预期验证点**
  - 事件风暴用于压力与分页/过滤能力验证（未来）。
  - 工单时间非法用于“写入失败 + 明确错误信息（英文 message）”验证（未来）。

## 6. 参数与配置外部化（Task 6.1 + Critical Rules）

### 6.1 统一参数集合（建议最小集合）

- `GANGQING_DATABASE_URL`（当前测试基线已使用）
- `GANGQING_SEED_DATA_SEED`
- `GANGQING_SEED_DATA_DATASET_ID`
- `GANGQING_SEED_DATA_DATASET_VERSION`
- `GANGQING_SEED_DATA_START_DATE`
- `GANGQING_SEED_DATA_END_DATE`
- `GANGQING_SEED_DATA_SCALE`
- `GANGQING_SEED_DATA_PACKS`（如：`baseline,missing,late,spike`）
- `GANGQING_SEED_DATA_TENANTS` / `GANGQING_SEED_DATA_PROJECTS`（支持多组）

> 注意：本节只定义口径；具体采用 env 还是 CLI 参数，由实现阶段决定，但必须满足“禁止硬编码”。

### 6.2 缺配置失败策略（No Skip）

- 冒烟测试与造数脚本必须：
  - 缺少 `GANGQING_DATABASE_URL` => 直接失败，输出清晰英文错误。
  - 连接失败 => 直接失败（映射为上游不可用/超时类错误）。

## 7. 数据生成口径（数值范围、单位、时间窗口）

### 7.1 时间窗口

- daily 表以 `business_date` 为主轴，覆盖 `[start_date, end_date]`。
- event 表以 `event_time` 生成，建议覆盖同一窗口内的多个时间点，并可在 anomaly pack 中生成“聚集”事件。

### 7.2 单位与范围（建议）

为支持后续 guardrail，需要定义“合理区间”的口径（即便 L3+ 才强制）：

- `fact_production_daily.quantity`：非负，范围随 `scale` 线性变化。
- `fact_energy_daily.consumption`：非负，范围随 `quantity` 与 energy_type 分布变化。
- `fact_cost_daily.amount`：非负，并与 `quantity/consumption` 相关（即使是模拟，也应保持弱相关，便于趋势分析）。

> 关键点：异常包中的 spike 必须能在统计上明显偏离 baseline，足以触发“变化率/区间”检测。

## 8. 测试使用方式（Task 6.3）

### 8.1 单元测试（`pytest -q`）应覆盖的断言口径

- **确定性**：同参数运行两次，抽样校验关键表的行 hash/汇总一致。
- **边界**：
  - 最小窗口（如 1 天）
  - 多租户/多项目生成
  - scale 较小/较大
- **异常注入稳定性**：启用某 anomaly pack 时，异常位置与值稳定。

> 约束提醒：仓库规则要求“真实服务集成测试禁用 mock”，但单元测试允许通过可控实现隔离；此处建议尽量将确定性验证做成纯函数级别（实现阶段再定）。

### 8.2 冒烟测试（`backend/scripts/seed_data_smoke_test.py`）应覆盖的端到端链路

冒烟测试必须连接真实 Postgres，并至少验证：

- **成功路径**
  - 迁移到 head（如需要）
  - 运行造数
  - 对每张核心表执行 SELECT 验证：
    - 行数大于 0（baseline pack）
    - 关键字段非空/符合约束（对 baseline 的子集）
    - 隔离域过滤生效（t1/p1 与 t2/p2 互不污染）

- **失败路径（缺配置/连接失败）**
  - 缺 `GANGQING_DATABASE_URL` => 明确失败（英文 message）

- **异常包验证（最小集合）**
  - 启用 `missing`：至少能查到 1 条缺失样本，并输出定位信息（表/主键/日期）
  - 启用 `late`：至少能查到 1 条 `created_at` 晚到样本
  - 启用 `spike`：至少能查到 1 段连续日期的突变样本

## 9. 风险与控制点

- **约束/触发器导致写入失败**：
  - 设计 anomaly pack 时避免默认触发 DB unique/FK/check 约束；约束违例应作为“显式失败包”单独开关。

- **与 RLS 的交互不清晰**：
  - schema smoke test 使用 `set_config('app.current_tenant','t1',true)`；造数与测试应统一采用相同方式设置上下文或显式写入隔离字段，避免误判“查不到数据”。

- **数据过大导致 CI 运行过慢**：
  - 通过 `scale` 与窗口参数控制。
  - baseline 默认规模建议保持在“秒级插入 + 秒级查询”范围。

## 10. 需要你确认的 3 个关键决策

为保证实现阶段不发生契约漂移，当前已确认的口径如下：

1. **Baseline 默认窗口长度**：90 天
