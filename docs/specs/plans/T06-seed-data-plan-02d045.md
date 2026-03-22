# T06 造数脚本决策建议（最佳实践对齐版，已确认）

本文件基于全网公开最佳实践与当前仓库实现现状，对任务 6 的 3 个关键决策点给出推荐选型与验收口径，目标是让造数“可复现、可重复运行、可定位样本、可在 dev/test 受控写入、可用于回归与 guardrail 演示”。

## 0. 已确认的最终结论（本任务按此执行）

- 幂等策略：**dataset_version 前缀 cleanup-rebuild（事实表）+ 维表 insert-if-not-exists**（不引入 upsert-update 语义）
- 写入门禁：**双门禁**（`GANGQING_ENV` 仅允许 `dev/test` + 显式写入开关）
- duplicate 口径：**(equipment, event_time, alarm_code)** 作为稳定判重键

## 0.1 范围与权威约束对齐（必须遵守）

- 权威来源
  - PRD：`docs/requirements.md`（R7.2、R14.4）
  - TDD：`docs/design.md`（2.6.2、2.9、7.2、7.5；Error/Evidence 约束）
  - 任务清单：`docs/tasks.md`（任务 6）
  - 契约草案：`docs/contracts/api-and-events-draft.md`
- 强制约束
  - **Schema First（Pydantic）**：造数参数/配置/写入摘要/证据锚点均以 Pydantic 为单一事实源。
  - **Structured Errors（英文 message）**：对外输出稳定 `code` + 英文 `message` + `requestId/runId`。
  - **Evidence-First**：必须输出可查询锚点，能定位到表名 + 主键/自然键 + 时间范围 + `dataset_version`（以及 `lineage_version` 如适用）。
  - **Real Integration（No Mock/No Skip）**：冒烟/集成必须连接真实 Postgres；配置缺失或服务不可用必须失败。
  - **Read-Only Default（Scope-limited Write）**：造数属于测试写入，必须受控执行且不污染非 dev/test。
  - **Isolation**：tenant/project 必须显式，并用于所有写入/清理/查询验证。

## 0.2 现状梳理（基于仓库脚本的事实）

- 现有入口
  - `backend/scripts/seed_data.py`
    - 已有 Pydantic：`SeedConfig`、`SeedEdgeCasesConfig`。
    - 已有 deterministic 生成：`generate_seed_payload(params)`（纯函数、无 DB）。
    - 写入策略（现状）：事实表按 `dataset_version` 前缀清理再插入；插入使用 `ON CONFLICT DO NOTHING`。
    - 已输出 edge 锚点（edge evidence）。
  - `backend/scripts/seed_data_smoke_test.py`
    - 真实 Postgres 写入与可查询断言；验证 missing/delay/extreme/duplicate。

## 1. 参考的外部最佳实践摘要（用于支撑选型）

- **Idempotent seeds（可重复运行）**
  - 核心原则：跑两次=跑一次（不会新增重复行、不会产生不可解释漂移）。
  - 常见实现：
    - Upsert（Postgres `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING`）
    - Conditional insert（存在即不插）
    - Truncate/cleanup + reload（dev 环境可接受“清理后重建”，但在共享环境要谨慎）
  - 参考：BlobForge seeding guide（Idempotent Seeders：Upsert/Conditional/Truncate & Reload）。

- **Deterministic identifiers（确定性主键/自然键）**
  - 为了让 upsert 与关联数据稳定，需要“同输入生成同 ID”。
  - 常见做法：从稳定字符串生成 deterministic UUID（如 UUID v5 或 hash-based）。
  - 参考：bitcrowd（Idempotent seeds: upsert + deterministic UUID from string/index）。

- **Seed 数据需要版本化、自动化、按环境分层**
  - 种子文件应被版本控制；schema 变更时 seeds 同 PR 更新。
  - dev 数据与 test 数据应区分（test 更小、更可预测；dev 更丰富）。
  - 参考：Neon（Version seeds、Structure by environment、Make seeds incremental & idempotent）。

- **避免“migration 管理的动态 seed”**
  - 动态/临时测试数据更适合独立 seeding 逻辑而非迁移内管理。
  - 参考：Microsoft EF Core（limitations：测试用临时数据、依赖 DB state、大数据等不适合 migration-managed seeding）。

## 1.1 数据集覆盖范围（基础场景 + 异常/边界）

- 基础业务数据（最小可用闭环）
  - 维表：`dim_equipment`、`dim_material`
  - 口径仓库：`metric_lineage`
  - 事实表：`fact_production_daily`、`fact_energy_daily`、`fact_cost_daily`、`fact_alarm_event`、`fact_maintenance_workorder`
- 异常/边界最小样本集（每类至少 1 个可定位锚点）
  - missing：关键字段缺失（现状示例：`fact_production_daily.equipment_id` 为 NULL）
  - delay：`extracted_at > time_end`（production）/ `created_at > event_time`（alarm）
  - duplicate：按已确认判重键出现重复（alarm）
  - extreme：生产/能耗等出现显著越界数值（阈值口径后续以 `lineage_version` 固化）

## 1.2 可复现性与幂等（验收口径补充）

- 输入：`seed + dataset_version + tenant_id + project_id + start_date + days + scale params + edge toggles`
- 输出
  - 生成层：同输入 => `generate_seed_payload` 输出一致（字段值、顺序、`source_record_id`）。
  - 写入层：同输入重复执行后，DB 内该 `dataset_version` 范围的数据保持一致（至少可按行数/锚点/关键自然键集合断言）。

## 2. 决策点 1：幂等策略（cleanup-rebuild vs upsert）推荐

### 2.1 当前仓库事实

- 当前实现是“**事实表按 dataset_version 前缀清理** + **插入时 ON CONFLICT DO NOTHING**”的混合策略。
- 维表为 insert-if-not-exists；`metric_lineage` 在 scope 内全量清理后插入。

### 2.2 推荐选型（结合 GangQing 约束）

**推荐：继续以“dataset_version 前缀 cleanup + reload”为主策略（事实表），并保持维表 insert-if-not-exists；避免在本任务阶段引入复杂 upsert 更新语义。**

理由（对齐最佳实践 + 你们项目硬约束）：
- 本任务目标是“可复现造数用于测试/降级/guardrail 验证”，属于典型的 **test dataset**，最佳实践允许在 dev/test 做受控 cleanup-rebuild。
- 你们还有强约束：
  - **No Mock/No Skip**：会在真实 Postgres 上反复跑；cleanup-rebuild 能保证环境“回到确定状态”。
  - **Evidence Anchors**：需要稳定锚点；cleanup-rebuild 能避免历史遗留数据干扰锚点定位。
- Upsert（DO UPDATE）适合“静态参考数据/小规模 lookup 表”，但对事实表会引入：
  - 更新逻辑复杂（哪些字段可更新？如何处理 NULL/边界样本？）
  - 容易造成“跑一次和跑两次的数据不同但又不报错”的隐性漂移。

### 2.3 幂等验收口径（必须）

- 同 `seed + dataset_version + tenant_id + project_id + 其它参数`：重复运行 2 次后，
  - 该 `dataset_version` 前缀的数据行数一致
  - 关键边界样本（missing/delay/duplicate/extreme）锚点仍存在且可定位
- 更换 `dataset_version`：
  - 只影响新版本前缀范围
  - 不得删除/影响其他版本数据

## 3. 决策点 2：写入门禁（dev/test + 显式 allow-write）推荐

### 3.1 当前仓库事实

- 当前脚本只要能连接 DB 就会执行 delete/insert；未检查 `GANGQING_ENV`，也没有显式写入开关。

### 3.2 推荐选型

**推荐：双门禁（环境 + 显式开关）**

- 门禁 1：`GANGQING_ENV` 仅允许 `dev/test`
- 门禁 2：显式写入开关（例如 `GANGQING_SEED_WRITE_ENABLED=true` 或 CLI `--allow-write`）

理由（对齐你们“只读默认 + scope-limited write”）：
- 造数属于“测试写入”，应当明确区分于生产运行路径。
- 双门禁能显著降低误操作风险（把真实/共享库当成测试库 seed 了）。
- 这也是各类工程实践里对 destructive 操作的通用做法：默认拒绝，明确 opt-in。

### 3.3 门禁失败的错误口径

- 不满足门禁：返回结构化错误（推荐 `FORBIDDEN` 或 `GUARDRAIL_BLOCKED`），英文 `message`，并携带脚本侧 `run_id`。

## 4. 决策点 3：duplicate 口径（如何“可回归触发”）推荐

### 4.1 当前仓库事实

- duplicate 目前仅在 alarm 表制造“额外多条记录”，但 `alarm_code` 可能不同，因此并不对应一个稳定的业务判重键。

### 4.2 推荐口径（以“可回归触发”为第一目标）

**推荐：把 duplicate 样本定义为“同一 scope + 同一 equipment + 同一 event_time + 同一 alarm_code”重复出现的多条事件**。

理由：
- 测试/回归最怕“看似重复但判重键不固定”，导致不同运行/不同查询口径下结果漂移。
- 选择 `equipment_id + event_time + alarm_code` 的组合，能让：
  - 去重逻辑、聚合逻辑在 SQL/工具层可稳定复现
  - 证据锚点更明确（“这是同一业务事件被重复上报/重复入库”）

### 4.3 duplicate 样本的验收口径

- 对该 `dataset_version`：至少存在 1 组重复键（按上述组合）
- 且该组重复键的记录数 `>= 2`
- 必须能通过脚本输出的锚点直接定位到该组（避免“随机查到”）

## 5. 对现有实现的最小改动方向（仅定义策略，不含代码）

- 幂等：保持现有“prefix cleanup + reload”的主策略；补齐“清理行数/写入摘要”可验收字段。
- 门禁：新增双门禁；失败 fast-fail + 结构化错误。
- duplicate：将 alarm duplicate 样本的 `alarm_code` 固定到同一值（在 duplicate 分支），从而形成稳定重复键。

## 5.1 Pydantic 产物（脚本参数/写入摘要/锚点）

- 现有模型（保持单一事实源）：`SeedConfig`、`SeedEdgeCasesConfig`
- 本任务需补齐/规范化的输出模型（计划口径；具体实现后续进行）
  - `SeedRunContext`：脚本侧 `run_id`（以及可选的 `request_id` 贯穿字段）
  - `SeedWriteSummary`
    - 每表插入行数
    - 每表清理行数（若采用清理策略）
    - 正常样本锚点 + 4 类异常锚点列表
  - `EdgeEvidenceAnchor`
    - `table`
    - `primary_key`（或自然键）
    - `time_range`（或关键时间字段）
    - `dataset_version`
    - `tenant_id/project_id`
    - `lineage_version`（如适用）

## 5.2 Evidence Anchors（证据锚点）验收

- 每次造数完成必须输出
  - `dataset_version`、`tenant_id`、`project_id`
  - 造数时间范围（由 `start_date + days` 得到）
  - 正常样本锚点至少 1 条
  - missing/delay/duplicate/extreme 锚点各至少 1 条
- 锚点可查询性
  - 给定锚点中的 `table + primary_key`（或自然键）必须能在同 tenant/project 下查到该行。
  - 给定 `source_record_id` 前缀必须能检索到对应异常行集合。

## 5.3 错误与门禁失败口径（脚本侧）

- 典型失败场景与稳定错误码（需与契约草案保持一致）
  - 参数不合法：`VALIDATION_ERROR`
  - 缺少必需配置：`VALIDATION_ERROR` 或 `AUTH_ERROR`（以仓库现状为准，但需统一）
  - DB 不可达：`UPSTREAM_UNAVAILABLE`
  - 环境门禁不允许写入：`FORBIDDEN` 或 `GUARDRAIL_BLOCKED`
  - 契约/引用违背：`CONTRACT_VIOLATION`

## 5.4 测试与验收（No Mock/No Skip）

- 冒烟测试（Smoke，真实 Postgres）最小断言
  - 必需配置缺失时必须失败且错误为结构化模型（英文 message）。
  - 写入成功后：基础表行数 > 0。
  - 4 类异常锚点各至少 1 条可查询。
  - 输出包含写入摘要与锚点列表。
- 单元测试（Unit，纯函数）最小断言
  - 同 `SeedConfig` 调用 `generate_seed_payload` 两次输出一致。
  - 更换关键输入（seed/dataset_version/days/tenant/project）输出必须变化且可解释。
  - edge toggles 关闭时对应 edge 前缀记录数为 0。

## 5.5 里程碑与产物（计划口径）

- M1：Dataset Profile（覆盖矩阵 + 锚点规范 + 验收口径）
- M2：Repro/Idempotency 验收固化（单测 + 冒烟）
- M3：Guardrail/降级复用准备（极端/缺失/延迟/重复样本可稳定触发演示）

## 6. 最终选项（已确认）

- 幂等策略：**cleanup-rebuild（事实表）+ 维表 insert-if-not-exists**
- 写入门禁：**双门禁（dev/test + 显式 allow-write）**
- duplicate 口径：**(equipment, event_time, alarm_code)**
