### Task 21 - 模型并发控制与排队：队列满返回 `SERVICE_UNAVAILABLE`，并支持取消（Umbrella）

```markdown
# Context
你正在执行第 21 号任务：模型并发控制与排队：队列满返回 `SERVICE_UNAVAILABLE`，并支持取消。
角色：**技术负责人/架构师**。
目标是规划并发上限与队列策略、等待期间的 SSE `progress` 输出、取消传播（中断推理/工具调用）、以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **结构化错误（强制）**: 队列满返回 `SERVICE_UNAVAILABLE`（英文 message，含 requestId）。
- **取消传播（强制）**: 客户端取消必须向下传播并中断底层推理/工具调用。
- **Streaming（强制）**: 等待期间输出 `progress`。
- **配置外部化（强制）**: 并发/队列参数不得硬编码。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R9.2）
- TDD: docs/design.md（2.7.2）
- tasks: docs/tasks.md（任务 21）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 21.1（并发/队列模型与配置）
2) Task 21.2（SSE 进度与取消协议）
3) Task 21.3（冒烟：并发压入 + 取消）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/concurrency_cancel_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 21.1 - 并发控制：队列满返回 `SERVICE_UNAVAILABLE`

```markdown
# Context
你正在执行子任务：21.1 - 并发控制：队列满返回 `SERVICE_UNAVAILABLE`。

# Critical Rules
- **错误结构化**。
- **可观测**: 返回包含排队信息摘要（不泄露敏感）。

# References
- tasks: docs/tasks.md（21.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 实现并发信号量/队列。
2) 队列满时返回结构化错误。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/concurrency_cancel_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 21.2 - 取消传播：SSE 断开/显式 cancel

```markdown
# Context
你正在执行子任务：21.2 - 取消传播：SSE 断开/显式 cancel。

# Critical Rules
- **必须中断底层调用**。
- **审计**: 记录取消事件与阶段。

# References
- tasks: docs/tasks.md（21.2）
- contracts: docs/contracts/api-and-events-draft.md（6.1/6.2 取消）

# Execution Plan
1) 监听客户端断开。
2) 传播取消到推理与工具调用。

# Verification
- **Smoke**: `backend/scripts/concurrency_cancel_smoke_test.py` 覆盖取消场景。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局约束保留）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（取消也应审计）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
