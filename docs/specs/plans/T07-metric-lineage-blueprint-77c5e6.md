# T07 指标口径仓库（Metric Lineage）：版本化口径 + 计算强绑定 lineage_version（执行蓝图）

本蓝图定义指标口径实体与版本化策略、计算时的口径引用与拒答/降级策略，并与对外 Evidence 合约中的 `lineageVersion` 字段对齐。

## 0. 关键决策（已确认）

- **版本号策略**：`lineage_version` 采用**语义化版本（SemVer，X.Y.Z）**。
- **Active 唯一性**：同一 `metric_key` 在同一 `tenantId/projectId` scope 下**强制最多一个 `active`**。
- **默认口径**：用户未指定版本时，允许在“唯一 active”情况下自动默认（但必须可审计、可解释；见 7.2）。

## 1. 权威约束对齐（必须遵守）

### 1.1 PRD（`docs/requirements.md`）
- **R7.3 指标口径仓库**
  - 必须记录：指标名、版本、计算公式、数据源、责任人。
  - 指标变更：必须创建新版本并保留历史版本。
  - 系统计算指标：必须引用指标口径版本。
  - 口径不一致：必须拒绝计算并提示。
- **R14.3 数据一致性**
  - 数据不一致：系统应拒绝返回并提示。

### 1.2 TDD（`docs/design.md`）
- **Evidence-First 不变式**：涉及计算必须绑定口径版本；不满足则降级。
- **证据链结构**：Lineage 需包含 `metric_name`、`lineage_version`、`formula_id`（内部结构），并在对外 Evidence 侧体现。
- **5.6 数据一致性拒答策略（强制）**
  - 同一指标多口径且无法确定口径版本：必须拒绝输出确定性结论，并提示需要指定口径或补齐口径条目。
  - 关键输入数据冲突且无法裁决：必须降级为“展示冲突数据与来源”，不得编造“正确值”。

### 1.3 Contracts（`docs/contracts/api-and-events-draft.md`）
- **Evidence 最小字段**包含 `lineageVersion?`，并有降级规则：
  - 任一条 Evidence `validation != verifiable`：必须输出 `warning`（推荐复用 `EVIDENCE_MISSING`/`EVIDENCE_MISMATCH` 等），最终输出不得包装为确定性结论。
- **结构化错误**：`ErrorResponse` 字段固定为 `code/message/details?/retryable/requestId`；其中 `message` 必须英文。
- **错误码映射**（本任务关注）：
  - 口径缺失 → `EVIDENCE_MISSING`
  - 口径冲突/口径不匹配 → `EVIDENCE_MISMATCH`

## 2. 任务边界与目标（Task 7 / 7.1 / 7.2）

### 2.1 交付目标（以“可审计、可追溯、可拒答”为核心）
- **口径实体**：明确“指标口径定义（definition）”与“口径版本（version）”的边界。
- **版本化策略**：保证历史可追溯与回滚能力（至少逻辑回滚/回查），并对“可用版本”有清晰约束。
- **计算绑定**：任何对外“计算型数值”必须绑定一个确定的 `lineage_version`，并写入 Evidence 的 `lineageVersion`。
- **拒答/降级**：口径缺失/冲突/不确定时，禁止输出确定性数值结论。

### 2.2 非目标（明确不做）
- 不提供任何代码实现或代码片段。
- 不扩展新的对外错误模型字段（以 `ErrorResponse` 5 字段为准）。
- 不改变 contracts 中 Evidence 字段集合（仅对齐与使用）。

## 3. 指标口径实体（Metric Lineage Entity）蓝图

> 目标：实现“同名指标但不同口径”可共存、可冻结、可追溯；并为计算链路提供唯一引用键。

### 3.1 核心概念与命名
- **Metric（指标）**：业务口径维度上的“指标标识”，例如 `ton_steel_cost`。
- **Lineage Version（口径版本）**：对指标的**可计算定义**的版本化快照，必须可被唯一引用。
- **Formula（公式）**：口径的一部分，用于描述计算逻辑与输入来源（可作为字段或关联对象）。

### 3.2 推荐的实体拆分（逻辑视图）
- **MetricDefinition（指标定义）**
  - `metric_key`：稳定键（建议用英文蛇形/短横线风格，避免中文作为主键）
  - `display_name`：展示名（可中文）
  - `domain`：指标域（成本/产量/能耗/质量等）
  - `owner`：责任人/责任团队（可用于审计与变更流程）
  - `description`：指标解释（可选）

- **MetricLineageVersion（指标口径版本）**
  - `metric_key`
  - `lineage_version`：版本号（语义化版本 SemVer，`X.Y.Z`，见 4.1）
  - `status`：`draft|active|deprecated|retired`（至少要能区分“可用于计算”的 active）
  - `formula`：公式表达（文本/结构化 DSL/引用 ID 均可，但必须可追溯）
  - `inputs`：输入依赖清单（数据源系统 + 表/接口/字段/过滤口径摘要）
  - `data_sources`：数据源声明（用于 Evidence sourceLocator 的一致性）
  - `created_by/created_at`：变更审计字段
  - `change_reason`：变更原因（可审计）

### 3.3 唯一引用与查找键（强制）
- 指标计算时引用键必须是：
  - `metric_key` + `lineage_version`
- 禁止仅用 `metric_key` 在“存在多个 active 或历史版本”情况下进行隐式选择。

## 4. 版本化策略（Versioning Strategy）蓝图

### 4.1 版本号策略（已确认：语义化版本 SemVer）

#### 4.1.1 SemVer 规则映射到“指标口径”语义（推荐落地口径）

参考：Semantic Versioning 2.0.0（semver.org）关键点：
- 版本号形态：`X.Y.Z`。
- 已发布版本内容**不得修改**，任何调整都必须发新版本。
- **标记弃用（deprecate）应作为 backward-compatible 变更**，通常体现在 **minor** 版本中，并在后续 major 版本中移除。

将其映射到指标口径：
- **MAJOR（X）**：对“指标公共口径 API”产生**不兼容**变更（会改变历史可比性或含义）。
  - 示例：从“含税成本”变为“不含税成本”；从“日口径”变为“班次口径”；或公式含义改变导致同比/环比不可直接对比。
- **MINOR（Y）**：新增兼容能力或**引入弃用标记**。
  - 示例：新增维度支持/输入源补充但不改变既有含义；将旧口径标为 `deprecated` 并提供迁移建议。
- **PATCH（Z）**：仅修复实现/配置错误且**不改变口径含义**（在严格口径治理下应极少发生；一旦会影响含义，应升级为 MINOR/MAJOR）。

约束：
- `lineage_version` 必须是**不可变**的发布标识；一旦发布不得覆盖。

### 4.2 版本状态机与可用性
-- `draft`：可编辑，不允许对外计算引用。
-- `active`：允许用于计算；一个 `metric_key` 在同一 scope（tenant/project）下**最多一个 active（强制）**。
-- `deprecated`：用于**受控迁移期**，默认不建议新计算引用（见 4.4）。
-- `retired`：仅**禁止新计算**；复算/对账是否允许由合规策略决定（本项目默认允许，除非明确禁止）。

### 4.3 兼容性与回滚
- **回滚原则**：回滚不是“覆盖旧版本”，而是“把某个旧版本重新设为 active”或“发布一个新版本恢复旧口径”。
- **对账/复算**：历史查询必须支持按指定 `lineage_version` 重放（即使当前 active 已变化）。

### 4.4 `deprecated` 最佳实践（全网结论收敛）

#### 4.4.1 `deprecated` 的定义（建议在本项目口径中固化）

结合 SemVer 与业界“契约/数据合约”演进实践：
- `deprecated` 表示**仍然可用**，但**不建议新使用**，并且必须提供迁移路径。
- `deprecated` 不是立即移除，而是“公告 + 支持期 + sunset”。

#### 4.4.2 `deprecated` 的最小治理流程（推荐）

参考外部最佳实践（例如公开 API deprecation policy 的通用做法）：
- **公告（Announcement）**：发布变更说明，明确：
  - 弃用原因
  - 替代版本（推荐迁移到哪个 `lineage_version`）
  - 迁移指南（业务影响、差异点、校验方式）
- **支持期（Support Period）**：在公告后保留旧版本可用一段时间（业界常见最低为“月级”，例如 30 天或 3 个月；具体由你们组织节奏决定）。
- **Sunset（终止）**：支持期结束后，旧版本对“新计算”应返回拒答/错误；对“历史复算/对账”是否保留取决于审计与合规要求（见 4.4.3）。

本项目已确认：
- **支持期（Support Period）= 90 天**（自公告日起计算）。

#### 4.4.3 `deprecated` 在本项目的执行口径（建议默认值）

- **新计算（New Computation）**：
  - 默认 **不允许**使用 `deprecated` 进行新计算。
  - 行为：要求用户指定非 deprecated 的版本；否则拒答。
  - 错误码：若用户明确指定 deprecated 且策略不允许 → `EVIDENCE_MISMATCH`（口径与策略不匹配）。

- **复算/对账（Recompute / Reconciliation）**：
  - 默认 **允许**使用 `deprecated` 进行“历史复算/对账回放”（因为口径可追溯是审计核心）。
  - 必须在 Evidence 中标注 `lineageVersion` 且 `validation` 不得因此变为不可验证；同时输出 `warning` 提示“该口径已弃用，仅用于复算”。

- **retired 的触发条件（仅建议，不强制）**：
  - 只有在合规要求（例如必须删除某口径或来源）或严重缺陷导致不可再用于复算时，才进入 `retired`。

- **与 SemVer 的对应**：
  - 引入弃用标记：通过 minor 版本发布（例如从 `1.2.0` 开始标记 `1.1.*` 为 deprecated）。
  - 真正移除（不允许新计算/或完全不可用）：应体现在 major 版本治理策略中。

## 5. 口径引用规则（Binding Rules）与 Evidence 对齐

### 5.1 计算链路强绑定规则（强制）
当且仅当满足以下条件，才允许输出“确定性计算结论（数值）”：
- 请求已明确或系统可确定一个唯一的 `lineage_version`。
- 该 `lineage_version` 处于允许计算的状态（建议仅 `active`）。
- 计算所依赖的输入数据具有可追溯 Evidence（至少能构造 `sourceSystem/sourceLocator/timeRange`）。

### 5.2 Evidence 写入规则（强制）
- 任何计算型 Evidence：必须写入 `lineageVersion=<lineage_version>`。
- 如果某条结论依赖多条 Evidence：
  - 允许每条 Evidence 都带 `lineageVersion`（推荐），或至少在关键结论 Evidence 上带。
  - 但不得出现“结论使用 lineage_version=A，而证据链中出现 lineage_version=B 且未解释”的情况。

### 5.3 与 Contracts 的 `validation` 对齐（强制语义）
- `verifiable`：口径版本明确且一致；证据可追溯。
- `not_verifiable`：无法确定口径版本或证据不足。
- `mismatch`：口径冲突（多口径、口径与输入不匹配、或请求指定版本不存在/不一致）。

## 6. 拒答与降级策略（强制）

### 6.1 拒答优先级（从高到低）
1) **口径缺失**：找不到 `metric_key + lineage_version` 或当前 scope 下无任何可用版本。
  - 行为：拒绝输出确定性数值；输出结构化错误或 warning。
  - 映射：`EVIDENCE_MISSING`。

2) **口径冲突/不唯一**：
  - 同一 `metric_key` 存在多个候选口径版本且无法唯一确定（例如多个 active、或用户未指定且系统无法选择）。
  - 行为：拒绝输出确定性数值；要求用户指定版本或澄清。
  - 映射：`EVIDENCE_MISMATCH`（因“口径不一致/不匹配”）。

3) **口径与输入数据冲突**：
  - 例如公式声明需要某数据源，但实际可用数据来自不同源且口径不可比；或同一时间窗输入存在互斥冲突且无法裁决。
  - 行为：降级为“展示冲突数据与来源”，禁止合成“正确值”。
  - 映射：`EVIDENCE_MISMATCH`（并在 Evidence `validation=mismatch`）。

### 6.2 对外输出形态建议（不改变 contracts 前提下）
- **REST 场景**：
  - 若用户请求的是“必须给出数值”的计算接口：返回 `ErrorResponse(code=EVIDENCE_*)`。
  - 若允许部分成功：可返回 200 + 业务体（不在本任务定义），同时伴随可检索审计事件与 evidence chain 标记。
- **SSE 场景**（推荐对齐 contracts）：
  - 输出 `warning`（`warning.payload.code=EVIDENCE_*`，中文提示即可）
  - 若无法继续：输出 `error`（ErrorResponse，英文 message）+ `final(status=error)`

> 注：本仓库 contracts 允许 warning.message 中文，但 error.message 必须英文。

## 7. 口径解析与选择（决策树蓝图）

### 7.1 输入来源（优先级）
1) 用户显式指定 `lineage_version`（最高优先级）。
2) 请求显式指定 `scenario_key`，并通过“口径映射表（7A）”解析到 `lineage_version`。
3) 上下文约束（例如“财务月结口径”“生产日报口径”）解析出 `scenario_key`（必须命中受控枚举）后，再通过映射表解析到版本；否则不得猜测。
4) 默认版本（仅当该指标在当前 scope 下“唯一 active”且策略允许默认）。

### 7.2 决策规则（强制安全）

- 若 1) 不存在或版本不可用：按 `EVIDENCE_MISSING`/`EVIDENCE_MISMATCH` 拒答。
- 若 2) 指定 `scenario_key` 但映射表缺失/冲突：按 7A.4 规则拒答。
- 若落入 4) 但发现不唯一：必须拒答并要求用户指定版本。
- 若落入 4)（唯一 active 自动默认）：必须满足：
  - 审计中记录“采用默认版本”的决策理由（例如 `decision=default_active`）。
  - 对外可解释：在最终答复或 evidence 面板中明确“本次使用口径版本 X.Y.Z（默认 active）”。
  - 若该唯一 active 为 `deprecated`：按 4.4.3 处理（默认不允许新计算）。

## 7A. 口径映射表（业务场景 -> lineage_version）最佳实践（建议新增治理对象）

> 目的：将“默认/隐式选择”变成“显式、可审计、可回滚”的策略对象，避免模型/Agent 自行猜测口径。

### 7A.1 为什么需要映射表

在企业指标治理中，口径往往不仅由指标名决定，还受“用途/场景”约束（例如月结财务、生产日报、经营分析、对外披露）。如果没有映射表：
- 系统只能用“唯一 active 默认”，一旦业务上需要多个并存口径，就会频繁触发 `EVIDENCE_MISMATCH` 拒答。
- 更严重的是，系统可能被迫做“隐式猜测”，这违反本项目 Evidence-First 与拒答策略。

### 7A.2 映射表应表达什么（最小字段建议）

映射表不是口径定义本身，而是“选择策略”的可审计声明，建议至少包含：
- `metric_key`
- `scenario_key`：场景键（例如 `finance_month_close`、`ops_daily_report`）
- `lineage_version`
- `scope`：绑定到 `tenantId/projectId`（隔离强制）
- `status`：`active|deprecated|retired`（策略对象也要版本化/可停用）
- `owner`/`change_reason`/`effective_time_range?`（何时生效）

### 7A.3 场景如何进入系统（建议两条路径）

- **路径 1（显式）**：前端或调用方在请求中带 `scenario_key`（更可控）。
- **路径 2（半显式）**：从对话上下文解析出场景，但必须通过“受控枚举 + 映射表命中”来确定；
  - 若无法命中，必须澄清或拒答，不得猜测。

本项目已确认：
- **在请求层显式承载 `scenario_key`**（路径 1 为主）；路径 2 仅作为对话场景下的辅助手段，且必须受控枚举。

### 7A.4 冲突与缺失处理（强制映射到 contracts）

- **缺失**：用户表述了场景但映射表无条目。
  - 行为：拒答确定性结论；提示补齐映射表或手工指定 `lineage_version`。
  - 错误码：`EVIDENCE_MISSING`。

- **冲突**：同一 `metric_key + scenario_key` 命中多个有效条目，或条目指向多个版本且无法裁决。
  - 行为：拒答，并提示需要治理/收敛（这属于“口径冲突”）。
  - 错误码：`EVIDENCE_MISMATCH`。

### 7A.5 审计与回滚（建议）

- 每次计算必须在审计中记录：
  - 命中方式：`user_specified|scenario_mapping|default_active`
  - 若为 `scenario_mapping`：记录 `scenario_key` 与命中条目版本（映射表自身也应版本化/有变更历史）。
- 回滚策略：回滚映射表条目（策略回滚）优先于回滚指标口径定义本身（定义是不可变的，策略可变）。

## 8. 审计与可观测性对齐（本任务关注点）

### 8.1 审计必记字段（与 requestId 关联）
- 本次计算使用的：
  - `metric_key`
  - `lineage_version`
  - 版本状态（active/deprecated 等）
  - 公式标识/摘要（脱敏且可追溯）
- 决策原因：
  - 是用户指定/场景映射（scenario_key）/默认选择
  - 若拒答：拒答原因分类（missing/mismatch/inputs_conflict）

### 8.2 结构化错误 details 建议（不得含敏感信息）
- `metricKey`
- `requestedLineageVersion`（若有）
- `availableLineageVersions`（可选，若不泄露敏感；否则仅给数量）
- `scope` 不应出现在 ErrorResponse（contracts 明确禁止额外字段），但可写入结构化日志/审计。

## 9. 与 Semantic API 的关系（接口层面约束）

- `docs/api/semantic-api.md` 提供 `GET /api/v1/semantic/kpis/{kpi_id}/lineage`：
  - 本任务的口径仓库与 lineage 查询应支持：
    - 按 KPI/指标查询可用版本集合
    - 在前端/对话澄清时用于“让用户选择版本”
  - 但本蓝图不要求新增或修改 API，只要求策略能对齐此能力。

## 10. 验证（按任务要求，不在本蓝图执行）

- Unit：`pytest -q`
- Smoke：`backend/scripts/metric_lineage_smoke_test.py`

> 注意：本蓝图为“规划产物”，不包含任何实现与测试执行。

## 11. 已确认的治理决策（用于后续实现收敛）

1) `deprecated` 支持期（Support Period）= **90 天**（自公告日起）。
2) `retired` 语义 = **仅禁止新计算**（复算/对账默认允许，除非合规明确禁止）。
3) 在请求层**显式承载 `scenario_key`**（作为口径选择主路径）。
