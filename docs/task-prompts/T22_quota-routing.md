### Task 22 - Token 预算/配额与模型路由（SLM/LLM）：可审计的路由原因与降级策略（Umbrella）

```markdown
# Context
你正在执行第 22 号任务：Token 预算/配额与模型路由（SLM/LLM）：可审计的路由原因与降级策略。
角色：**技术负责人/架构师**。
目标是规划配额模型（按用户/角色/场景）、路由规则（简单查询走小模型/模板化、复杂分析走大模型）、超额错误码与降级建议，以及审计字段。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **结构化错误（强制）**: 超额返回 `FORBIDDEN` 或 `SERVICE_UNAVAILABLE`（按 tasks 要求），英文 message。
- **可审计（强制）**: 路由原因必须可审计（不泄露 prompt/密钥）。
- **配置外部化（强制）**: 配额阈值、路由规则不得硬编码。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R15.4）
- TDD: docs/design.md（3.9/2.7.2）
- tasks: docs/tasks.md（任务 22）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 22.1（配额模型与错误码）
2) Task 22.2（路由规则与降级建议）
3) Task 22.3（审计与可观测字段）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/quota_routing_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 22.1 - 配额命中：返回 `FORBIDDEN`/`SERVICE_UNAVAILABLE` + 可执行降级建议

```markdown
# Context
你正在执行子任务：22.1 - 配额命中：返回 `FORBIDDEN`/`SERVICE_UNAVAILABLE` + 可执行降级建议。

# Critical Rules
- **错误结构化**。
- **message 英文**。

# References
- tasks: docs/tasks.md（22.1）
- PRD: docs/requirements.md（R15.4）

# Execution Plan
1) 定义配额计数维度。
2) 命中时返回结构化错误，并在 `details` 提供降级建议（去敏）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/quota_routing_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（全局约束保留）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（路由原因需审计）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
