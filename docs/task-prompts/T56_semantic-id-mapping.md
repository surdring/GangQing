### Task 56 - （L1+）统一语义层（实体与 ID 映射）：设备/物料/批次/订单统一 ID 映射与冲突治理（Umbrella）

```markdown
# Context
你正在执行第 56 号任务：统一语义层（实体与 ID 映射）。
角色：**技术负责人/架构师**。
目标是规划统一 ID 映射表、冲突检测与版本化、跨系统聚合前置条件、以及映射缺失/冲突的错误码与证据链语义。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Isolation（强制）**: 映射必须按 tenant/project 隔离；跨隔离访问返回 `AUTH_ERROR`。
- **Evidence-First（强制）**: 映射结果与版本信息必须可追溯并进入 Evidence（摘要）。
- **结构化错误（强制）**: 映射缺失/冲突返回 `EVIDENCE_MISMATCH`（或按 contracts），英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R16.1）
- TDD: docs/design.md（5.3）
- tasks: docs/tasks.md（任务 56）
- contracts: docs/contracts/api-and-events-draft.md（2.3 Semantic API）
- api docs: docs/api/semantic-api.md

# Execution Plan
1) Task 56.1（映射表与版本化）
2) Task 56.2（冲突检测与拒答/降级）
3) Task 56.3（跨系统聚合门禁：必须基于统一 ID）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/semantic_id_mapping_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 56.1 - 统一 ID 映射：冲突治理与 `EVIDENCE_MISMATCH`

```markdown
# Context
你正在执行子任务：56.1 - 统一 ID 映射：冲突治理与 `EVIDENCE_MISMATCH`。

# Critical Rules
- **冲突必须拒绝聚合**。
- **错误结构化**。

# References
- tasks: docs/tasks.md（56.1）

# Execution Plan
1) 定义映射实体 schema（Pydantic）。
2) 实现冲突检测与错误映射。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/semantic_id_mapping_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（映射版本 evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
