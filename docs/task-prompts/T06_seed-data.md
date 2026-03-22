### Task 6 - 实现可复现造数脚本（Umbrella）

```markdown
# Context
你正在执行第 6 号任务：实现可复现造数脚本（覆盖异常/边界，用于降级与 guardrail 验证）。
角色：**技术负责人/架构师**。
目标是规划造数数据集的覆盖范围、可复现性策略、异常/边界样本、与冒烟/回归使用方式，并明确测试口径。

# Critical Rules (核心约束)
- **NO CODE IMPLEMENTATION**: 在此阶段**禁止**输出任何具体实现代码。
- **PLANNING ONLY**: 仅输出执行蓝图与验收口径（怎么做/分几步/产物是什么/如何验收）。
- **Schema First (Pydantic)**:
  - 造数脚本参数、数据集配置、写入摘要、数据版本标识等必须有 Pydantic 模型与校验。
  - 若造数产物需要被 API/测试/工具复用，必须以模型作为单一事实源，避免“口头约定”。
- **Structured Errors (English Message)**:
  - 任何可预期失败（配置缺失/DB 不可达/权限不足/契约违背）必须映射为稳定 `code` + 英文 `message`，并携带 `requestId`（或脚本侧 `runId`，并可映射回 `requestId`）。
- **Evidence-First**:
  - 造数必须为“证据链演示”提供锚点（可定位到表名、主键/自然键、时间范围、数据版本、口径版本/lineage_version）。
- **Real Integration (No Mock, No Skip)**:
  - 冒烟/集成必须连接真实 Postgres（以及任务链路依赖的真实服务）；缺少配置或服务不可用 => **必须失败**（不得 `skip`）。
- **Config Externalization & Fast-Fail**:
  - DB 连接、seed、规模、时间范围、dataset_version、异常覆盖开关必须外部化（环境变量/CLI 参数/配置文件）。
  - 禁止交互式询问配置；关键配置缺失必须快速失败，并输出清晰英文错误。
- **Read-Only Default (Scope-limited Write)**:
  - 系统整体默认只读；造数属于“测试数据写入”，必须在明确开关与环境边界下执行（例如仅允许 dev/test 环境）。
  - 所有写入必须可审计/可追溯，且具备幂等策略（同 seed + dataset_version 可重复执行并得到一致结果）。
- **Context & Isolation**:
  - 若造数/校验逻辑涉及 `tenantId/projectId` 维度，必须明确隔离策略与最小数据域（避免跨域污染）。

# References
- PRD: docs/requirements.md（R7.2/R14.4）
- TDD: docs/design.md（2.6.2、2.9、7.2、7.5）
- tasks: docs/tasks.md（任务 6）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 6.1（造数脚本框架与种子策略）
- Goal: 建立造数脚本统一入口与可复现机制（同 seed + dataset_version => 同数据）。
- Key Decisions:
  - 造数入口形式：`python -m ...` / `backend/scripts/seed_data.py`（以仓库约定为准）。
  - 幂等策略：清理后重建 vs upsert（必须可解释并可验证）。
  - 运行标识：`run_id`/`request_id` 的生成与贯穿（日志/写入摘要/审计）。
- Deliverables: 造数 CLI、配置/参数模型、写入摘要输出规范。

2) Task 6.2（异常/边界覆盖）
- Goal: 将异常/边界要求固化为“可回归触发”的最小样本集。
- Coverage (至少):
  - 缺失值（NULL/空值）
  - 延迟到达（事件时间早于入库时间，跨日/跨月边界）
  - 重复记录（同业务键重复/冲突）
  - 极端波动（短窗口剧烈变化，用于 guardrail）
- Deliverables: Dataset Profile（异常清单->表/字段/约束->可查询锚点）。

3) Task 6.3（数据集用于测试）
- Goal: 冒烟/回归/契约测试统一依赖该造数数据集，并对失败场景给出明确英文错误。
- Deliverables: 端到端冒烟脚本/回归接入方式、关键断言清单。

# Deliverables Definition
- [ ] **Seed Script CLI**: 统一入口（可重复运行），支持 seed/规模/时间范围/dataset_version/异常覆盖开关，并输出写入摘要（每表记录数、关键主键范围、异常样本锚点）。
- [ ] **Dataset Profile**: 异常/边界覆盖清单（每类异常至少 1 个最小样本），明确落表、字段、约束、查询方式与预期触发的 guardrail/降级路径。
- [ ] **Evidence Anchors**: Evidence 展示最小锚点（表名、主键/自然键、时间范围、dataset_version、lineage_version/口径版本）。
- [ ] **Smoke/Regression Wiring**: 冒烟与回归统一依赖该数据集；配置缺失/DB 不可达/权限不足必须显式失败并输出英文错误。

# Verification
- Automated (Unit): `pytest -q`（覆盖：可复现性、异常样本存在性、配置缺失失败路径）
- Automated (Smoke): `backend/scripts/seed_data_smoke_test.py`（覆盖：真实 Postgres 写入+可查询断言）

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 6.1 - 造数脚本：可复现与异常/边界覆盖

```markdown
# Context
你正在执行子任务：6.1 - 造数脚本：可复现与异常/边界覆盖。
目标是实现造数脚本，把最小数据模型填充为可开发、可冒烟、可回归的数据集。

# Critical Rules (核心约束)
- **Schema First (Pydantic)**: 造数参数/配置/写入摘要必须有模型与校验。
- **Reproducibility**: 同 `seed` + `dataset_version` => 输出一致；变更必须可追溯。
- **Real Integration (No Skip)**: 必须写入真实 Postgres；缺少配置或 DB 不可达 => 测试必须失败（不得 `skip`）。
- **Structured Errors (English Message)**: 失败必须有稳定错误码与英文 `message`（便于日志检索）。
- **Config Externalization & Fast-Fail**: DB 连接、seed、规模、时间范围、dataset_version 必须来自环境变量或 CLI 参数；关键配置缺失必须快速失败。
- **Idempotency**: 重复执行必须安全且结果一致（明确清理/幂等策略）。

# References
- PRD: docs/requirements.md（R7.2）
- TDD: docs/design.md（2.6.2、2.9）
- tasks: docs/tasks.md（6.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
## Target Files
- `backend/scripts/seed_data.py`（或等价脚本入口；以仓库最终落盘为准）
- `backend/gangqing_db/settings.py`（如需要新增/补齐造数相关配置项的加载与校验）
- `backend/tests/test_seed_data_reproducibility.py`（或等价单测文件；以仓库最终落盘为准）

1) 定义配置与参数契约（Pydantic）
- 明确：`database_url`、`seed`、`scale`、`time_range`、`dataset_version`、`enable_edge_cases` 等。

2) 实现造数入口（可复现 + 幂等）
- 写入维度表与事实表的最小闭环数据。
- 输出写入摘要（每表行数、关键主键范围、异常样本锚点）。

3) 提供最小“证据链锚点”映射
- 为后续 Evidence 展示预留：表名、主键/自然键、时间字段范围、dataset_version。

# Verification
- **Unit**: `pytest -q` 覆盖：
  - 同 `seed` + `dataset_version` 的可复现性
  - 缺少关键配置时失败（英文错误信息可检索）
- **Smoke**: `backend/scripts/seed_data_smoke_test.py`

# Output Requirement
交付方式：输出可审查的实现与验证证据。
- 必须列出所有修改/新增文件路径。
- 必须给出验证命令与关键输出摘要（文本）。
- 若文件较大：允许仅粘贴“关键片段 + 明确文件路径”，但必须保证审查者可在仓库中定位到完整落盘内容。
```

---

### Task 6.2 - 异常/边界数据集：覆盖清单与落库规则

```markdown
# Context
你正在执行子任务：6.2 - 异常/边界数据集：覆盖清单与落库规则。
你的目标是把“异常/边界覆盖”从口头要求变成可执行、可回归的最小数据集规范与落库实现，并确保每类异常都能被测试稳定触发。

# Critical Rules (核心约束)
- **Schema First (Pydantic)**: 异常样本生成规则、关键字段约束、dataset_version 标识必须有模型/校验。
- **Evidence-First**: 每类异常样本必须能定位到表 + 主键/自然键 + 时间范围 + dataset_version。
- **Real Integration (No Skip)**: 必须写入真实 Postgres；配置缺失或 DB 不可达 => 必须失败（不得 `skip`）。
- **Config Externalization**: 异常覆盖开关、规模、时间范围必须参数化。
- **Structured Errors (English Message)**: 失败必须输出稳定 `code` 与英文 `message`。

# References
- PRD: docs/requirements.md（R14.4）
- TDD: docs/design.md（2.6.2）
- tasks: docs/tasks.md（6.2）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
## Target Files
- `backend/scripts/seed_data.py`（扩展异常样本生成逻辑；以仓库最终落盘为准）
- `backend/tests/test_seed_data_edge_cases.py`（新增/扩展单元测试；以仓库最终落盘为准）

1) 定义异常/边界覆盖清单（最小可回归）
- 缺失值：关键字段为 NULL / 空字符串等。
- 延迟到达：事件时间早于入库时间，且时间跨度覆盖边界（如跨天/跨月）。
- 重复记录：同自然键重复、或同一业务键不同版本并存（按项目口径）。
- 极端波动：数值字段在短时间窗口内剧烈变化，用于 guardrail 验证。

2) 设计落库规则与幂等策略
- 同一 seed + dataset_version 重复执行：结果一致；若允许重跑，必须先清理再写入或使用 upsert（以项目口径为准）。
- 必须输出写入摘要：每类异常写入多少条、关键主键范围。

3) 编写单元测试（不依赖 mock）
- 断言每类异常至少生成 1 条，并满足约束（例如 NULL 字段确实为 NULL）。
- 断言错误路径：缺少必需配置时抛出清晰英文错误并失败。

# Verification
- **Unit**: `pytest -q`（至少覆盖：每类异常样本存在性 + 关键字段断言 + 配置缺失失败路径）
- **Smoke**: `backend/scripts/seed_data_smoke_test.py`（落库后能查询到异常样本的最小断言）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Task 6.3 - 造数数据集接入冒烟/回归：真实 Postgres 端到端校验

```markdown
# Context
你正在执行子任务：6.3 - 造数数据集接入冒烟/回归：真实 Postgres 端到端校验。
你的目标是让“冒烟/回归测试”以统一方式调用造数数据集，并在真实 Postgres 上完成端到端断言（成功路径 + 关键失败路径）。

# Critical Rules (核心约束)
- **Real Integration (No Skip)**: 测试必须连接真实 Postgres；缺少连接配置或 DB 不可达 => 必须失败（不得 `skip`）。
- **Config Externalization & Fast-Fail**: DB 连接参数、seed、dataset_version、时间范围必须来自环境变量或参数；缺失必须快速失败。
- **Structured Errors (English Message)**: 测试失败必须可定位（英文 message + 稳定 code 或明确异常类型）。
- **Observability**: 输出必须包含可关联字段（至少包含 `run_id`/`request_id`）。

# References
- PRD: docs/requirements.md（R7.2/R14.4）
- TDD: docs/design.md（7.2、7.5）
- tasks: docs/tasks.md（6.3）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
## Target Files
- `backend/scripts/seed_data_smoke_test.py`（新增或完善；以仓库最终落盘为准）
- `backend/scripts/postgres_schema_smoke_test.py`（如需复用/串联；以仓库最终落盘为准）

1) 统一冒烟入口
- 确保冒烟脚本会：加载配置 -> 连接 DB -> 执行造数 -> 验证关键表与关键样本存在。

2) 增加失败路径断言（不可 skip）
- 缺少必要环境变量：脚本必须退出失败，并输出清晰英文错误。
- DB 不可达：脚本必须退出失败，并输出清晰英文错误。

3) 回归可复用性
- 支持传入 seed/dataset_version，使同一数据集可在多次 CI/本地运行中复用并可定位。

# Verification
- **Smoke**: `backend/scripts/seed_data_smoke_test.py`
- **Unit**: `pytest -q`（至少覆盖：配置校验失败路径与错误信息为英文）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检）
- [ ] 是否所有错误 `message` 都是英文？
- [ ] 是否包含结构化错误模型字段（`code/message/requestId/retryable/details?`）？
- [ ] 是否包含证据链锚点要求与字段（可定位表/键/时间范围/dataset_version/lineage_version）？
- [ ] 是否包含只读默认与“测试环境受限写入”的边界说明？
- [ ] 是否包含隔离维度（tenantId/projectId）与避免跨域污染的要求（如适用）？
- [ ] 是否包含 Schema（Pydantic）与契约对齐要求？
- [ ] 是否包含真实集成测试且不可 skip 的要求？
