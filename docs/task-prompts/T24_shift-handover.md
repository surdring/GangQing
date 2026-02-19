### Task 24 - 智能交接班：班次摘要、异常与未闭环事项、关键操作追溯（Umbrella）

```markdown
# Context
你正在执行第 24 号任务：智能交接班：班次摘要、异常与未闭环事项、关键操作追溯。
角色：**技术负责人/架构师**。
目标是规划班次摘要的输入数据（审计/事件模型）、摘要结构、可追溯字段（谁/何时/为何），以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 摘要中的关键结论必须可追溯（引用审计事件/事件模型）。
- **RBAC + 审计（强制）**: 交接班报告生成与查询必须权限检查并审计。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R2.5/R11.1）
- TDD: docs/design.md（2.8.1）
- tasks: docs/tasks.md（任务 24）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 24.1（摘要数据源：审计 + 事件）
2) Task 24.2（摘要结构与 Evidence 引用）
3) Task 24.3（冒烟：生成与查询）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/shift_handover_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 24.1 - 交接班摘要：基于审计/事件的可追溯汇总

```markdown
# Context
你正在执行子任务：24.1 - 交接班摘要：基于审计/事件的可追溯汇总。

# Critical Rules
- **不允许凭空生成**: 必须引用审计/事件证据。

# References
- tasks: docs/tasks.md（24.1）
- PRD: docs/requirements.md（R2.5）

# Execution Plan
1) 定义报告 schema（Pydantic）。
2) 汇总异常/未闭环/参数调整/遗留待办，并附 evidence 引用。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/shift_handover_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
