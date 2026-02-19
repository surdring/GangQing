### Task 39 - 受控执行与回滚：执行前创建回滚点，失败自动回滚或熔断（Umbrella）

```markdown
# Context
你正在执行第 39 号任务：受控执行与回滚。
角色：**技术负责人/架构师**。
目标是规划受控执行网关、幂等 key、执行前回滚点、失败回滚/熔断策略、以及审计与结构化执行结果。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **写操作治理（强制）**: 仅允许“草案 -> 审批/多签 -> 受控执行 -> 回滚点 -> 审计”。
- **Kill Switch（强制）**: 写能力可熔断。
- **结构化错误（强制）**: 执行失败必须结构化，英文 message。
- **审计（强制）**: 执行产生 `write_operation` 审计事件，可按 requestId 聚合。
- **配置外部化（强制）**。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R5.4）
- TDD: docs/design.md（3.6.4）
- tasks: docs/tasks.md（任务 39）
- contracts: docs/contracts/api-and-events-draft.md（Execution/Rollback/Kill Switch）

# Execution Plan
1) Task 39.1（执行前置检查：权限/审批状态/白名单/Kill Switch）
2) Task 39.2（回滚点与回滚流程）
3) Task 39.3（审计与幂等）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/controlled_execute_and_rollback_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 39.1 - 受控执行：前置检查 + 幂等 key + 结构化结果

```markdown
# Context
你正在执行子任务：39.1 - 受控执行：前置检查 + 幂等 key + 结构化结果。

# Critical Rules
- **禁止越过审批**。
- **执行前必须创建回滚点**。

# References
- tasks: docs/tasks.md（39.1）

# Execution Plan
1) 定义 ExecutionRequest/ExecutionResult Pydantic 模型。
2) 实现前置检查与执行记录。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/controlled_execute_and_rollback_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（执行与回滚需 evidence/audit）
- [x] 只读默认与审批链？（本任务核心）
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
