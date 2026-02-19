### Task 28 - 纠错反馈闭环：点赞/点踩、纠错提交、审核入库、纳入 Golden Dataset（Umbrella）

```markdown
# Context
你正在执行第 28 号任务：纠错反馈闭环：点赞/点踩、纠错提交、审核入库、纳入 Golden Dataset。
角色：**技术负责人/架构师**。
目标是规划反馈数据模型、与 `requestId`/Evidence 绑定、审核流程（只读默认下的受控写入预留）、以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 反馈必须绑定 `requestId` 与 evidence 引用；无依据标注 `unverified`。
- **Read-Only Default（强制）**: 任何写入（入库/发布）必须走审批/审核链路（本任务至少实现“待审核队列”）。
- **RBAC + 审计（强制）**: 提交/审核动作写审计。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R15.5）
- TDD: docs/design.md（3.9）
- tasks: docs/tasks.md（任务 28）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 28.1（反馈提交：like/dislike/correction）
2) Task 28.2（审核：approve/reject，入库策略）
3) Task 28.3（纳入 Golden Dataset 的接口/流程对齐）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/feedback_loop_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 28.1 - 反馈提交：绑定 requestId + evidence 引用

```markdown
# Context
你正在执行子任务：28.1 - 反馈提交：绑定 requestId + evidence 引用。

# Critical Rules
- **必须绑定证据**。
- **审计**。

# References
- tasks: docs/tasks.md（28.1）

# Execution Plan
1) 定义反馈 Pydantic 模型。
2) 实现提交端点与落库。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/feedback_loop_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（反馈绑定 evidence）
- [x] 只读默认与审批链？（审核链路）
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
