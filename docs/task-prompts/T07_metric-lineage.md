### Task 7 - 指标口径仓库：版本化口径 + 指标计算必须绑定 `lineage_version`（Umbrella）

```markdown
# Context
你正在执行第 7 号任务：指标口径仓库：版本化口径 + 指标计算必须绑定 `lineage_version`。
角色：**技术负责人/架构师**。
目标是规划指标口径实体、版本化策略、拒答/降级策略，以及与 Evidence 的 `lineageVersion` 字段对齐。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First**: 涉及计算必须绑定 `lineage_version` 并写入 Evidence。
- **拒答策略（强制）**: 口径缺失/冲突时拒绝输出确定性结论（或降级展示数据与来源）。
- **结构化错误（强制）**: 口径冲突/缺失可映射到 `EVIDENCE_MISMATCH` 或 `EVIDENCE_MISSING`（以 contracts 为准）。

# References
- PRD: docs/requirements.md（R7.3/R14.3）
- TDD: docs/design.md（5.2/5.6）
- tasks: docs/tasks.md（任务 7）
- contracts: docs/contracts/api-and-events-draft.md（Evidence lineageVersion）

# Execution Plan
1) Task 7.1（指标口径实体与版本化）
- 字段：指标名、版本、公式、数据源、责任人。

2) Task 7.2（口径引用与拒答/降级）
- 任何指标计算必须引用指定版本；不确定则拒答或降级。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/metric_lineage_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 7.1 - 指标口径仓库实体与版本化策略

```markdown
# Context
你正在执行子任务：7.1 - 指标口径仓库实体与版本化策略。
目标是实现 metric_lineage 的数据模型与基础读写能力（按任务范围），并确保与 Evidence 对齐。

# Critical Rules
- **lineage_version 强制**: 任何计算型输出必须绑定。
- **结构化错误**: 缺口径/冲突时错误必须结构化且 `message` 英文。

# References
- PRD: docs/requirements.md（R7.3）
- tasks: docs/tasks.md（7.1）

# Execution Plan
1) 定义 Pydantic 模型（对外/对内）与数据库实体。
2) 实现查询/校验工具函数：按指标名+版本获取口径。

# Verification
- **Unit**: `pytest -q` 覆盖：缺口径拒答；口径冲突拒答。
- **Smoke**: `backend/scripts/metric_lineage_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（`lineageVersion`）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
