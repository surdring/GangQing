### Task 6 - 实现可复现造数脚本（Umbrella）

```markdown
# Context
你正在执行第 6 号任务：实现可复现造数脚本（覆盖异常/边界，用于降级与 guardrail 验证）。
角色：**技术负责人/架构师**。
目标是规划造数数据集的覆盖范围、可复现性策略、异常/边界样本、与冒烟/回归使用方式，并明确测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **PLANNING ONLY**: 本段仅输出执行蓝图与验收口径，不输出任何具体实现代码。
- **Schema First**:
  - 后端：对外 I/O、脚本参数、证据对象（如 Evidence）使用 Pydantic 作为单一事实源。
- **Structured Errors**: 对外错误必须结构化（`code`/`message`/`requestId`/`retryable`/`details?`），其中 `message` 必须为英文。
- **Evidence-First**: 造数必须支持证据链演示（可定位到表/主键/时间范围/口径版本）。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实 Postgres；配置缺失或服务不可用 => 测试必须失败（不得 skip）。
- **配置外部化**: 种子/规模/时间范围/数据版本通过配置或参数化，禁止硬编码。
- **Read-Only Default**: 默认只读；仅允许在“种子数据/测试环境”范围内写入，且必须有明确的运行开关与审计字段贯穿。

# References
- PRD: docs/requirements.md（R7.2/R14.4）
- TDD: docs/design.md（2.6.2）
- tasks: docs/tasks.md（任务 6）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 6.1（造数脚本框架与种子策略）
- 同种子同数据；版本变更可追溯。

2) Task 6.2（异常/边界覆盖）
- 缺失值、延迟到达、重复记录、极端波动。

3) Task 6.3（数据集用于测试）
- 冒烟/回归统一使用该数据集；依赖缺失必须失败。

# Deliverables Definition
- [x] **Seed Script CLI**: 统一入口（可重复运行），支持 seed/规模/时间范围/数据版本标识，并能输出写入摘要（记录数、关键主键范围）。
- [x] **Dataset Profile**: 异常/边界覆盖清单（每类异常至少一个最小样本），并明确落在哪些表、对应哪些字段。
- [x] **Evidence Anchors**: 用于证据链展示的最小锚点信息（表名、主键/自然键、时间字段范围、数据版本）。
- [x] **Smoke/Regression Wiring**: 冒烟与回归测试统一依赖该数据集，且对配置缺失/DB 不可达显式失败。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/seed_data_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 6.1 - 造数脚本：可复现与异常/边界覆盖

```markdown
# Context
你正在执行子任务：6.1 - 造数脚本：可复现与异常/边界覆盖。
目标是实现造数脚本，把最小数据模型填充为可开发、可冒烟、可回归的数据集。

# Critical Rules
- **可复现性**: 同 seed 输出一致。
- **真实集成测试（No Skip）**: 造数必须写入真实 Postgres，配置缺失必须失败。
- **Structured Errors**: 失败必须有稳定错误码与英文 message，便于日志检索。
- **配置外部化**: DB 连接、seed、规模、时间范围必须来自环境变量或 CLI 参数。

# References
- PRD: docs/requirements.md（R7.2）
- tasks: docs/tasks.md（6.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
## Target Files
- `backend/scripts/seed_data.py`（或等价脚本入口；以仓库最终落盘为准）
- `backend/gangqing_db/settings.py`（如需要新增/补齐造数相关配置项的加载与校验）
- `backend/tests/test_seed_data_reproducibility.py`（或等价单测文件；以仓库最终落盘为准）

1) 实现造数入口：支持 seed 与规模参数。
2) 覆盖异常样本：缺失/重复/延迟/极端波动。

# Verification
- **Unit**: `pytest -q` 覆盖：同 seed 一致性（允许通过“可注入 RNG/seed”实现）。
- **Smoke**: `backend/scripts/seed_data_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 6.2 - 异常/边界数据集：覆盖清单与落库规则

```markdown
# Context
你正在执行子任务：6.2 - 异常/边界数据集：覆盖清单与落库规则。
你的目标是把“异常/边界覆盖”从口头要求变成可执行、可回归的最小数据集规范与落库实现，并确保每类异常都能被测试稳定触发。

# Critical Rules
- **Schema First**: 异常样本的生成规则、关键字段约束、数据版本标识必须在代码侧有明确模型/校验（Pydantic）。
- **Evidence-First**: 每类异常样本必须能定位到具体表与主键（或自然键）与时间范围，便于证据链展示。
- **真实集成测试（No Skip）**: 必须写入真实 Postgres；配置缺失或 DB 不可达 => 测试必须失败。
- **配置外部化**: 异常覆盖开关（是否生成某类异常）、规模、时间范围必须参数化。
- **Structured Errors**: 失败必须输出稳定 `code` 与英文 `message`。

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

# Critical Rules
- **真实集成测试（No Skip）**: 测试必须连接真实 Postgres；缺少连接配置或 DB 不可达 => 必须失败（不得 skip）。
- **配置外部化**: DB 连接参数、seed、数据版本、时间范围必须来自环境变量或参数。
- **Structured Errors**: 测试失败的错误必须可定位（英文 message + 稳定 code 或明确异常类型）。
- **可观测性**: 日志/输出必须包含可关联字段（至少包含 requestId 或等价 runId，用于定位一次造数与测试运行）。

# References
- PRD: docs/requirements.md（R7.2/R14.4）
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
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？（全局规则已包含）
- [x] 是否包含证据链要求与字段？（强调可定位与 time_range）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（与审计关联在全局规则中保留）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
