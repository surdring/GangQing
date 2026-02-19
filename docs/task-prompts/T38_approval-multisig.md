### Task 38 - 审批与多签（approval）：按变更类型路由审批人，拒绝必须有原因并可追溯（Umbrella）

```markdown
# Context
你正在执行第 38 号任务：审批与多签（approval）。
角色：**技术负责人/架构师**。
目标是规划审批状态机（pending/approved/rejected/expired/withdrawn）、路由规则（工艺红线/安全连锁触发多签）、审计事件与证据链引用。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default（强制）**: 未审批通过禁止进入执行。
- **RBAC + 审计（强制）**: 每个审批动作写审计（approval）；拒绝必须记录原因（去敏）。
- **结构化错误（强制）**: 无权限/状态不合法必须结构化返回，英文 message。
- **配置外部化（强制）**: 审批路由规则与超时不得硬编码。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R5.3）
- TDD: docs/design.md（3.6.3）
- tasks: docs/tasks.md（任务 38）
- contracts: docs/contracts/api-and-events-draft.md（Approval/Audit）

# Execution Plan
1) Task 38.1（审批状态机与 schema）
2) Task 38.2（路由与多签规则）
3) Task 38.3（审计与查询）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/approval_multisig_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 38.1 - 审批状态机：submit/approve/reject/withdraw

```markdown
# Context
你正在执行子任务：38.1 - 审批状态机：submit/approve/reject/withdraw。

# Critical Rules
- **拒绝必须有原因**（英文 message + 结构化 details）。
- **审计必须完整**。

# References
- tasks: docs/tasks.md（38.1）

# Execution Plan
1) 定义 Approval Pydantic 模型与状态转移规则。
2) 实现审批动作端点与审计写入。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/approval_multisig_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（审批引用草案与证据）
- [x] 只读默认与审批链？（本任务核心）
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
