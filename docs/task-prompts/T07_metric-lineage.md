### Task 7 - 指标口径仓库：版本化口径 + 指标计算必须绑定 `lineage_version`（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 7 号任务：指标口径仓库：版本化口径 + 指标计算必须绑定 `lineage_version`。
你的角色是 **技术负责人/架构师**。
你的目标是制定任务 7 的执行蓝图：规划指标口径实体、版本化策略、拒答/降级策略，以及与 Evidence 的 `lineage_version/lineageVersion` 字段对齐。

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

# Execution Plan
1) Task 7.1（指标口径实体与版本化）
- 字段：指标名、版本、公式、数据源、责任人。

2) Task 7.2（口径引用与拒答/降级）
- 任何指标计算必须引用指定版本；不确定则拒答或降级。

# Deliverables Definition
- [ ] **Directory Structure**: 明确新增/修改的目录树（模型/CRUD/校验/脚本/测试）。
- [ ] **API & Tool Contracts**: 口径查询与口径绑定规则的输入/输出契约（Pydantic 模型），并与 `docs/contracts/api-and-events-draft.md` 对齐。
- [ ] **Evidence Contract Alignment**: 明确 Evidence 中 `lineage_version/lineageVersion` 的字段名、约束与填充时机。
- [ ] **Error Model Mapping**: 明确缺口径/口径冲突/权限不足等场景的错误码映射与 `retryable` 语义。
- [ ] **Observability & Audit**: 明确审计事件类型与必填字段（至少 `requestId`）。
- [ ] **Verification Assets**: 明确单元测试与冒烟测试脚本（真实服务）。

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
- `backend/`：`metric_lineage` 相关 Pydantic 模型、数据访问层、校验逻辑、错误映射
- `backend/migrations/`：如需补齐表结构/索引/约束
- `backend/tests/`：单元测试（拒答/冲突/校验）
- `backend/scripts/metric_lineage_smoke_test.py`：冒烟测试（真实服务链路）

# Execution Plan
1) 定义数据结构与契约
- 定义 Pydantic 模型：MetricLineage（读模型/写模型如适用）、查询入参、错误细节结构。
- 明确 `lineage_version` 的取值规则（例如语义版本/递增整型）与唯一性约束（`metric_name + lineage_version`）。

2) 实现核心逻辑
- 实现按 `metric_name + lineage_version` 获取口径的查询函数。
- 实现“缺口径/冲突”的判定与结构化错误映射（`EVIDENCE_MISSING` / `EVIDENCE_MISMATCH` 以 contracts 为准）。

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
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
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
- `backend/`：指标计算入口/服务层（或工具编排层）中加入口径版本绑定校验
- `backend/tests/`：单元测试（拒答/降级/错误模型/证据字段）
- `backend/scripts/metric_lineage_smoke_test.py`：冒烟测试扩展（覆盖未指定版本与冲突版本）

# Execution Plan
1) 明确“绑定规则”与输入来源
- 定义请求/函数入参中 `lineage_version` 的来源（用户显式指定 / 默认策略 / 禁止隐式推断）。

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

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（`lineage_version/lineageVersion`）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
