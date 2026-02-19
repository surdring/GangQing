### Task 37 - 写操作草案生成（ACTION_PREPARE）：约束清单、目标函数、影响评估与可编辑草案（Umbrella）

```markdown
# Context
你正在执行第 37 号任务：写操作草案生成（ACTION_PREPARE）。
角色：**技术负责人/架构师**。
目标是规划“草案”数据模型、可编辑结构、约束清单/目标函数/影响评估字段、审计与证据链要求，并确保只生成草案不执行。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default（强制）**: 本任务只允许生成草案，禁止执行写入。
- **审批链（强制）**: 草案后续必须走审批/多签；草案生成需记录版本与参数摘要。
- **Evidence-First（强制）**: 草案的关键假设/约束/预期效果必须可追溯到数据与来源；不可验证必须标注不确定。
- **结构化错误**: 英文 message。
- **RBAC + 审计 + requestId**。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R5.2）
- TDD: docs/design.md（3.6.2）
- tasks: docs/tasks.md（任务 37）
- contracts: docs/contracts/api-and-events-draft.md（Draft/Approval）

# Execution Plan
1) Task 37.1（草案 schema：Draft + Constraint + Objective + Impact）
2) Task 37.2（草案生成：可编辑 + 冲突标注）
3) Task 37.3（审计与证据：草案生成参数摘要）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/action_prepare_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 37.1 - 草案生成：只生成 Draft，不执行

```markdown
# Context
你正在执行子任务：37.1 - 草案生成：只生成 Draft，不执行。

# Critical Rules
- **禁止执行**。
- **草案必须可编辑**。

# References
- tasks: docs/tasks.md（37.1）

# Execution Plan
1) 定义 Draft Pydantic 模型与持久化实体。
2) 生成草案并返回结构化结果。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/action_prepare_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（草案约束/影响需 evidence）
- [x] 只读默认与审批链？（只生成草案）
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
