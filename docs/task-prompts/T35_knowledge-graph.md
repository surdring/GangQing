### Task 35 - 知识图谱增强（可选）：设备-故障-现象-备件-事件多跳关联（每跳可追溯）（Umbrella）

```markdown
# Context
你正在执行第 35 号任务：知识图谱增强（可选）。
角色：**技术负责人/架构师**。
目标是规划多跳关联的实体/关系 schema、每跳 Evidence 约束、缺证据降级策略，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 每跳关联必须有证据来源；缺证据必须降级为“已知关联与来源/不确定项”。
- **结构化错误**: 英文 message。
- **RBAC + 脱敏**: 图谱查询按角色与数据域；敏感关系脱敏。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R16.4）
- TDD: docs/design.md（14.1）
- tasks: docs/tasks.md（任务 35）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 35.1（图谱实体/关系 schema）
2) Task 35.2（多跳查询与证据链）
3) Task 35.3（降级语义）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/knowledge_graph_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 35.1 - 多跳链路：每跳 Evidence 引用与降级

```markdown
# Context
你正在执行子任务：35.1 - 多跳链路：每跳 Evidence 引用与降级。

# Critical Rules
- **每跳必须可追溯**。

# References
- tasks: docs/tasks.md（35.1）

# Execution Plan
1) 定义 GraphTraversalResult Pydantic 模型（含 hops 与 evidenceRefs）。
2) 缺证据时标记 hop 为 not_verifiable。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/knowledge_graph_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（每跳 evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
