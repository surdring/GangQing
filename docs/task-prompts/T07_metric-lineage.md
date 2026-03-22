### Task 7 - 指标口径仓库：版本化口径 + 指标计算必须绑定 `lineage_version`（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 7 号任务：指标口径仓库：版本化口径 + 指标计算必须绑定 `lineage_version`。
你的角色是 **技术负责人/架构师**。
你的目标是制定任务 7 的执行蓝图：规划指标口径实体、版本化策略、拒答/降级策略，以及与 Evidence 的 `lineage_version/lineageVersion` 字段与契约对齐。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 在此阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 你的输出必须聚焦于“怎么做/分几步/文件结构/契约是什么”。
- **Schema First (Pydantic)**: 后端对外 I/O、工具参数、Evidence、审计事件必须以 Pydantic 作为单一事实源。
- **Evidence-First**: 任何指标计算/聚合输出必须绑定明确的 `lineage_version`（或契约字段名 `lineageVersion`），并写入 Evidence；无法确定口径版本时必须拒答或降级。
- **拒答/降级策略（强制）**:
  - 口径缺失：不得输出确定性结论，必须拒答或降级为“展示数据与来源/不确定项”。
  - 口径冲突：不得“自动选一个版本”，必须拒答并要求用户/调用方指定版本。
- **Structured Errors（强制）**: 对外错误必须结构化：`code` + `message`（英文）+ `requestId` + `retryable` + `details?`。
- **RBAC & Audit（强制）**: 任何读取口径、工具调用、计算请求必须做权限检查并记录审计事件；日志/审计字段至少包含 `requestId`，可用时包含 `sessionId/taskId/stepId/toolName`。
- **Read-Only Default（强制）**: 本任务仅涉及口径元数据与只读查询；任何写操作按“草案→审批/多签→受控执行→回滚点→审计”治理（L4 预留）。
- **Real Integration (No Skip)**: 冒烟/集成测试必须连接真实服务（真实 Postgres）；配置缺失或依赖不可用必须失败，不得 skip。

# References
- PRD: docs/requirements.md（R7.3/R14.3）
- TDD: docs/design.md（5.2/5.6）
- tasks: docs/tasks.md（任务 7）
- contracts: docs/contracts/api-and-events-draft.md（Evidence lineageVersion / errors）
- api docs: docs/api/*.md

# Non-Goals
- 不在本任务中引入“写操作执行能力”；任何口径写入/更新仅限 L4 的草案与审批材料，不允许在 L1/L2 直接落库执行。
- 不在本任务中定义外部 ERP/MES/DCS 等系统的字段级映射细节；仅要求口径仓库能引用数据源并可追溯。

# Execution Plan
1) Task 7.1（指标口径实体与版本化）
- Goal: 定义 `metric_lineage` 的数据模型（含版本化字段与唯一性约束），为后续“计算必须绑定 `lineage_version`”提供权威来源。
- Key Decisions:
  - 版本策略（语义版本/递增整型/日期版本）只能选一种作为主策略，并在契约中固化。
  - 必须支持“同一指标多版本并存”，并能按“指定版本/最新版本（如允许）”进行查询。

2) Task 7.2（口径引用与拒答/降级）
- Goal: 将“计算必须绑定 `lineage_version`”落实为服务端强制校验规则，并与 Evidence / 错误模型对齐。
- Key Decisions:
  - 对“未指定版本”是否允许默认 latest：默认不允许；如允许必须在契约与审计中显式记录选择理由与版本。
  - 对“版本不存在/冲突”的行为：默认拒答（结构化错误），必要时可降级为“仅展示原始数据与来源”。

3) Task 7.3（对外契约与 Evidence 对齐）
- Goal: 明确对外 API / 工具调用 / Evidence 中 `lineage_version/lineageVersion` 的字段名、必填规则、填充时机与序列化一致性。

4) Task 7.4（测试与验收资产）
- Goal: 增加单元测试与真实服务冒烟测试，覆盖“成功绑定”“缺失版本拒答”“冲突版本拒答”“结构化错误字段完整性”。

# Deliverables Definition
- [ ] **Directory Structure**: 明确新增/修改的目录树（模型/CRUD/校验/脚本/测试）。
- [ ] **Environment Variables**: 明确本任务新增/依赖的环境变量，并说明缺失时的失败策略（英文错误消息）。
- [ ] **API & Tool Contracts**: 口径查询与口径绑定规则的输入/输出契约（Pydantic 模型），并与 `docs/contracts/api-and-events-draft.md` 对齐。
- [ ] **Evidence Contract Alignment**: 明确 Evidence 中 `lineage_version/lineageVersion` 的字段名、约束与填充时机（计算型结论必须具备，否则拒答/降级）。
- [ ] **RBAC Policy**: 明确“读取口径/执行计算/查看脱敏字段”的权限点与拒绝策略（`FORBIDDEN`/`AUTH_ERROR`）。
- [ ] **Error Model Mapping**: 明确缺口径/口径冲突/权限不足/契约校验失败等场景的错误码映射与 `retryable` 语义。
- [ ] **Observability & Audit**: 明确审计事件类型（query/tool.call/tool.result/response/error）与必填字段（至少 `requestId`，可用时补齐 `sessionId/taskId/stepId/toolName`）。
- [ ] **Verification Assets**: 明确单元测试与冒烟测试脚本（真实服务）。

# Verification Plan (整体验收)
- 自动化断言（必须可复现）：
  - 单元测试：覆盖口径版本解析、口径选择策略、拒答/降级分支、结构化错误字段完整性。
  - 冒烟测试：真实 FastAPI + 真实 Postgres（包含种子数据）链路下，覆盖“成功查询口径”“计算入口触发绑定校验”“失败路径返回结构化错误”。
- 约束一致性：
  - Evidence 中出现的 `lineage_version/lineageVersion` 必须能在口径仓库中定位到唯一版本。
  - 若无法定位，必须输出 `warning` 或结构化 `error`，不得输出确定性数值。

# Verification
- Automated Tests:
  - Unit: `pytest -q`
  - Smoke: `backend/scripts/metric_lineage_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 7.1 - 指标口径仓库实体与版本化策略

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：7.1 - 指标口径仓库实体与版本化策略。
你的角色是 **高级开发工程师**。
你的目标是实现 `metric_lineage` 的数据模型与基础能力（按任务范围），并确保与 Evidence 的 `lineage_version/lineageVersion` 对齐。

# Critical Rules
- **Schema First (Pydantic)**: 对外 I/O、Evidence、审计事件必须使用 Pydantic 作为单一事实源。
- **lineage_version 强制**: 任何指标计算型输出必须绑定明确口径版本；无法确定版本必须拒答或降级。
- **Structured Errors**: 对外错误必须结构化（`code/message/requestId/retryable/details?`），其中 `message` 必须为英文。
- **RBAC & Audit**: 口径查询与计算前置校验必须受 RBAC 约束，并记录审计（至少包含 `requestId`）。
- **Read-Only Default**: 本子任务不引入受控写执行路径；仅允许元数据的受控维护入口（若超出范围需在任务内明确拒绝）。
- **Real Integration (No Skip)**: 冒烟测试必须连真实 Postgres；配置缺失必须失败，不得 skip。

# References
- PRD: docs/requirements.md（R7.3）
- TDD: docs/design.md（5.2）
- tasks: docs/tasks.md（7.1）
- contracts: docs/contracts/api-and-events-draft.md（Evidence lineageVersion / errors）

# Target Files (to be confirmed by implementation)
- `backend/gangqing_db/metric_lineage.py`：MetricLineage Pydantic 模型、查询/绑定逻辑、RBAC & 审计写入
- `backend/gangqing_db/evidence.py`：Evidence 模型（`lineageVersion` 字段）
- `backend/gangqing_db/metric_lineage_scenario_mapping.py`：场景映射解析（如本任务需要）
- `backend/migrations/versions/0001_init_min_schema.py`：`metric_lineage` 表初始化（唯一性约束等）
- `backend/migrations/versions/0002_metric_lineage_semver_and_active_unique.py`：SemVer 校验与 active 唯一性索引
- `backend/migrations/versions/0003_metric_lineage_scenario_mapping.py`：scenario mapping 表（如启用场景绑定）
- `backend/tests/test_metric_lineage.py`：单元测试（存在/缺失/冲突/绑定决策/结构化错误）
- `backend/scripts/metric_lineage_smoke_test.py`：冒烟测试（真实 Postgres + migration + seed + 端到端）

# Environment Variables
- `GANGQING_DATABASE_URL`（强制）：指向真实 Postgres；缺失必须失败并输出英文错误消息。

# Execution Plan
1) 定义数据结构与契约
- 明确 `metric_lineage.lineage_version`（DB 字段）与 `MetricLineageRecord.lineageVersion`（对外 alias）的映射。
- 明确 `Evidence.lineageVersion`：
  - 该字段用于“指标口径版本”追溯，必须与 `metric_lineage.lineage_version` 同源。
  - 对计算型结论/绑定结果：必须填充；对纯原始数据证据：可为空，但不得伪造。
- 明确 `lineage_version` 取值规则：采用 SemVer（`X.Y.Z`），并与 DB 侧 check constraint 对齐。
- 明确唯一性约束：
  - `(tenant_id, project_id, metric_name, lineage_version)` 全量唯一。
  - `(tenant_id, project_id, metric_name)` 在 `is_active=true` 时唯一（避免多个 active 版本）。

2) 实现核心逻辑
- 实现按 `metric_name + lineage_version` 获取口径的查询函数。
- 实现“缺口径/冲突”的判定与结构化错误映射：
  - 缺失：`EVIDENCE_MISSING`（`retryable=false`）
  - 冲突/多 active：`EVIDENCE_MISMATCH`（`retryable=false`）

3) 编写测试用例
- 单元测试覆盖：存在/不存在/重复冲突/非法版本格式/权限不足（如适用）。
- 冒烟测试覆盖：真实 Postgres 下的端到端查询链路（可包含最小数据准备）。

# Verification
- **Unit**: `pytest -q`
  - 必须覆盖：缺口径拒答；口径冲突拒答；结构化错误字段完整性（`code/message/requestId/retryable`）。
- **Smoke**: `backend/scripts/metric_lineage_smoke_test.py`
  - 必须连接真实 Postgres；缺少必要环境变量时必须失败并给出清晰英文错误。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Task 7.2 - 口径引用绑定与拒答/降级策略落地

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：7.2 - 口径引用绑定与拒答/降级策略落地。
你的角色是 **高级开发工程师**。
你的目标是把“指标计算必须绑定 `lineage_version`”落实为可执行的校验与行为：未指定版本/版本不存在/版本冲突时拒答或降级，并确保与 Evidence/错误契约一致。

# Critical Rules
- **Schema First (Pydantic)**: 对外 I/O、Evidence、审计事件必须以 Pydantic 为单一事实源。
- **Evidence-First**: 任何计算型输出必须写入 Evidence 并包含 `lineage_version/lineageVersion`。
- **拒答/降级（强制）**:
  - 未指定版本且无法推断：拒答（提示需要指定版本）。
  - 指定版本不存在：拒答或降级（按产品策略），不得编造。
  - 版本冲突：拒答，必须要求显式指定。
- **Structured Errors**: `code/message/requestId/retryable/details?`，其中 `message` 英文。
- **RBAC & Audit**: 口径绑定校验与拒答/降级必须记录审计，字段含 `requestId`。
- **Real Integration (No Skip)**: 冒烟/集成测试必须连真实服务；配置缺失必须失败，不得 skip。

# References
- PRD: docs/requirements.md（R7.3/R14.3）
- TDD: docs/design.md（5.6）
- tasks: docs/tasks.md（7.2）
- contracts: docs/contracts/api-and-events-draft.md（Evidence lineageVersion / errors）

# Target Files (to be confirmed by implementation)
- `backend/gangqing_db/metric_lineage.py`：`bind_metric_lineage_for_computation` 绑定决策与拒答/降级（核心）
- `backend/gangqing_db/metric_lineage_scenario_mapping.py`：scenarioKey 解析（若按场景绑定）
- `backend/gangqing_db/evidence.py`：Evidence `lineageVersion` 字段填充一致性
- `backend/tests/test_metric_lineage.py`：单测覆盖绑定成功/失败与结构化错误
- `backend/scripts/metric_lineage_smoke_test.py`：真实服务冒烟覆盖失败路径（缺失 lineageVersion）与场景绑定成功

# Environment Variables
- `GANGQING_DATABASE_URL`（强制）：指向真实 Postgres；缺失必须失败并输出英文错误消息。

# Execution Plan
1) 明确“绑定规则”与输入来源
- 定义 `MetricLineageBindingRequest.lineageVersion` 的来源：
  - 用户显式指定（首选）。
  - 通过 `scenarioKey` 映射得到（可选）。
  - 默认 active（默认禁止；仅在明确开启 `allow_default_active=true` 时允许，并必须写审计）。

2) 实现校验与行为
- 在计算入口处强制校验：若未满足绑定规则，则返回结构化错误或触发降级输出（以契约为准）。
- 生成 Evidence 时强制填充 `lineage_version/lineageVersion`（若走降级，Evidence 中必须明确不确定项）。

3) 编写测试
- 单元测试覆盖：未指定版本、版本不存在、版本冲突、合法绑定成功。
- 冒烟测试覆盖：真实服务链路下的成功与失败路径。

# Verification
- **Unit**: `pytest -q`
  - 覆盖：拒答/降级策略；结构化错误字段完整性；Evidence lineage 字段存在性。
- **Smoke**: `backend/scripts/metric_lineage_smoke_test.py`
  - 覆盖：成功路径 + 至少 1 个失败路径（未指定版本或冲突版本）。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---
### Task 7.3 - 对外契约与 Evidence 对齐（`lineageVersion` 一致性）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：7.3 - 对外契约与 Evidence 对齐（`lineageVersion` 一致性）。
你的角色是 **高级开发工程师**。
你的目标是把“指标口径版本”在后端 Pydantic、前端 Zod（如适用）、以及文档契约中对齐为**单一事实源**与一致的序列化字段（`lineageVersion`），并确保所有对外输出可被契约校验。

# Critical Rules
- **Schema First**:
  - 后端：对外 I/O、Evidence、错误模型使用 Pydantic。
  - 前端：对外 I/O、SSE 事件、错误响应使用 Zod 运行时校验（若本子任务涉及前端改动）。
- **Evidence-First**: 任何计算型结论必须携带 `Evidence.lineageVersion` 且能在 `metric_lineage` 仓库中定位到唯一记录。
- **Structured Errors**: 对外错误必须结构化（`code/message/requestId/retryable/details?`），`message` 必须英文。
- **Contract Validation (No Skip)**: 契约校验必须可自动化执行；真实服务不可用或配置缺失必须失败，不得 skip。

# References
- TDD: docs/design.md（3.3/5.2/6.1）
- contracts: docs/contracts/api-and-events-draft.md
- web schemas: web/schemas/*

# Target Files (to be confirmed by implementation)
- `backend/gangqing_db/evidence.py`：Evidence `lineageVersion` 字段（alias/命名）与校验规则
- `backend/gangqing_db/metric_lineage.py`：MetricLineageRecord/Query/BindingRequest 中 `lineageVersion` 的 alias 一致性
- `docs/contracts/api-and-events-draft.md`：对外契约中 Evidence 与错误模型字段命名约束（如需补齐/修订）
- `web/schemas/errorResponse.ts`：结构化错误 schema（如需与 docs/contracts 对齐）
- `web/schemas/sseEnvelope.ts`：SSE Envelope schema（若本任务需要在 SSE 中承载/校验 Evidence 更新）
- `web/tests/contractSchemas.test.ts`：前端契约测试（如需新增断言）
- `backend/scripts/contract_validation_smoke_test.py`：后端契约验证冒烟（如需扩展覆盖 Evidence 字段）

# Environment Variables
- `GANGQING_DATABASE_URL`（如运行后端契约冒烟涉及 DB）：缺失必须失败并输出英文错误消息。

# Execution Plan
1) 统一字段命名与别名策略
- 明确对外 JSON 字段一律为 `lineageVersion`（camelCase）。
- 明确后端内部字段使用 `lineage_version`（snake_case），并通过 Pydantic alias 显式映射。

2) 统一契约描述与实现的一致性
- 确认 `docs/contracts/api-and-events-draft.md` 中 Evidence 的 `lineageVersion` 与后端 `Evidence` 模型一致。
- 若前端有 Evidence 展示/解析：确认 Zod schema 中同名字段一致。

3) 增加契约断言
- 后端：通过 Pydantic `model_dump(by_alias=True)` 的断言确保输出字段名正确。
- 前端（如适用）：通过 Zod parse 断言确保事件/错误/证据结构可解析。

# Verification
- **Unit**:
  - `pytest -q`（覆盖 Evidence/MetricLineage 的 alias 与序列化字段一致性）
- **Smoke**:
  - `backend/scripts/contract_validation_smoke_test.py`（扩展/确认包含 Evidence lineageVersion 字段的契约校验）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```
### Task 7.4 - 测试与验收资产（Unit + Smoke + Contract）

# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：7.4 - 测试与验收资产（Unit + Smoke + Contract）。
你的角色是 **高级开发工程师**。
你的目标是补齐本任务组的自动化验收资产：单元测试覆盖关键拒答/降级分支，冒烟测试覆盖真实 Postgres 端到端链路，并确保契约校验脚本覆盖 `lineageVersion` 等关键字段。

# Critical Rules
- **Real Integration (No Skip)**: 冒烟必须连真实 FastAPI + 真实 Postgres；配置缺失必须失败，不得 skip。
- **Evidence-First**: 测试必须断言关键输出携带 Evidence（含 `lineageVersion` 与可定位 sourceLocator/timeRange）。
- **Structured Errors**: 测试必须断言错误响应包含 `code/message/requestId/retryable`，且 `message` 为英文。

# References
- TDD: docs/design.md（6.4/7.*）
- scripts: backend/scripts/*.py

# Target Files (to be confirmed by implementation)
- `backend/tests/test_metric_lineage.py`：补齐/加强单元测试覆盖
- `backend/scripts/metric_lineage_smoke_test.py`：冒烟测试（真实 DB + migrations + seed + 查询/绑定失败路径）
- `backend/scripts/contract_validation_smoke_test.py`：契约验证冒烟（必要时扩展覆盖 Evidence lineageVersion）

# Environment Variables
- `GANGQING_DATABASE_URL`（强制）：缺失必须失败并输出英文错误消息。

# Execution Plan
1) 单元测试增强
- 覆盖：
  - `get_metric_lineage`：显式版本成功/缺失返回 `EVIDENCE_MISSING`/重复冲突返回 `EVIDENCE_MISMATCH`。
  - `bind_metric_lineage_for_computation`：用户指定成功；缺失版本且 `allow_default_active=false` 必须失败；scenarioKey 成功；deprecated 拒绝。
  - 结构化错误：`to_response()` 输出字段完整且 `requestId` 存在。

2) 冒烟测试完善
- 扩展 `metric_lineage_smoke_test.py` 覆盖至少 1 个失败路径（未指定 lineageVersion 且默认不允许）。

3) 契约验证覆盖
- 确认/扩展 contract 验证脚本：Evidence 中 `lineageVersion` 字段命名与可解析性。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/metric_lineage_smoke_test.py`
- **Contract Smoke**: `backend/scripts/contract_validation_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（`lineage_version/lineageVersion`）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？

---

### Checklist（Umbrella 自检）
- [x] 是否包含 `# Critical Rules` 且明确禁止输出实现代码？
- [x] 是否包含覆盖任务 7 的完整 `# Execution Plan`（含子任务拆解与依赖）？
- [x] 是否定义了交付物定义（目录结构/ENV/API 契约/Evidence 对齐/RBAC/错误模型/审计）？
- [x] 是否包含最终的整体验收计划（Unit + Smoke，真实服务，不可 skip）？
