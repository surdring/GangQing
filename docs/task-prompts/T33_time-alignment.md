### Task 33 - 事件模型与时间对齐深化：更多链路使用锚点事件/窗口对齐，并可视化展示（Umbrella）

```markdown
# Context
你正在执行第 33 号任务：事件模型与时间对齐深化。
角色：**技术负责人/架构师**。
目标是规划锚点事件/窗口对齐的对齐规则、失败语义（`EVIDENCE_MISSING` 或 `warning`）、证据链展示对齐规则与时间窗口，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 对齐后的结论必须可追溯：锚点事件、窗口、对齐规则版本。
- **结构化错误（强制）**: 对齐失败返回 `EVIDENCE_MISSING`（或按 contracts），英文 message。
- **SSE（强制）**: 对齐失败可通过 `warning` 事件提示降级。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R16.2）
- TDD: docs/design.md（5.4）
- tasks: docs/tasks.md（任务 33）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 33.1（事件模型与对齐规则 schema）
2) Task 33.2（证据链展示：锚点事件/窗口/规则版本）
3) Task 33.3（失败与降级：EVIDENCE_MISSING/warning）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/time_alignment_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 33.1 - 时间对齐：锚点事件 + 窗口对齐 + 证据展示

```markdown
# Context
你正在执行子任务：33.1 - 时间对齐：锚点事件 + 窗口对齐 + 证据展示。

# Critical Rules
- **对齐规则可版本化**。
- **Evidence 必须包含锚点与窗口**。

# References
- tasks: docs/tasks.md（33.1）

# Execution Plan
1) 定义对齐输入/输出 Pydantic 模型。
2) 将对齐规则摘要写入 Evidence。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/time_alignment_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（对齐规则/窗口）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
