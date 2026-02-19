### Task 31 - 工艺参数优化建议（决策辅助）：基于历史相似批次与约束清单输出建议（Umbrella）

```markdown
# Context
你正在执行第 31 号任务：工艺参数优化建议（决策辅助）。
角色：**技术负责人/架构师**。
目标是规划“相似批次检索/约束清单/建议输出结构/不确定降级”，并确保建议必须引用历史案例与证据。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 建议类结论必须至少 1 条可追溯引用（历史批次/规程/工单等）。
- **不可验证降级（强制）**: 缺数据必须明确不确定并输出 `warning`。
- **Guardrail（强制）**: 建议不得越过物理边界/红线（与任务 30/32 协同）。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R4.1）
- TDD: docs/design.md（3.8）
- tasks: docs/tasks.md（任务 31）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 31.1（相似批次检索：输入/输出契约）
2) Task 31.2（建议输出：范围/理由/引用/不确定项）
3) Task 31.3（冒烟：建议生成与引用可追溯）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/process_optimization_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 31.1 - 建议输出结构：参数范围 + 理由 + 历史案例引用

```markdown
# Context
你正在执行子任务：31.1 - 建议输出结构：参数范围 + 理由 + 历史案例引用。

# Critical Rules
- **必须引用证据**。
- **低置信度必须建议人工复核**。

# References
- tasks: docs/tasks.md（31.1）

# Execution Plan
1) 定义 Pydantic 建议模型（含 `confidence/uncertainties/evidenceRefs`）。
2) 实现生成与降级。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/process_optimization_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（建议引用）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
