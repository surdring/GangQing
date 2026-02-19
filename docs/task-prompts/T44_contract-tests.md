### Task 44 - 契约测试体系：前端 Zod + 后端 Pydantic + SSE 事件 schema 自动断言（Umbrella）

```markdown
# Context
你正在执行第 44 号任务：契约测试体系。
角色：**技术负责人/架构师**。
目标是规划契约测试覆盖对象（REST 响应、SSE 事件、Evidence、错误模型）、测试门禁策略（不一致阻止合并/发布），以及单元/冒烟测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源（强制）**: 前端 Zod、后端 Pydantic，且对外输出前必须 schema 断言。
- **结构化错误（强制）**: 错误模型字段齐全，英文 message。
- **真实集成测试（No Skip）**: 契约冒烟必须连真实服务；缺配置必须失败。

# References
- PRD: docs/requirements.md（R9.3）
- TDD: docs/design.md（7.4）
- tasks: docs/tasks.md（任务 44）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# Execution Plan
1) Task 44.1（后端 Pydantic 契约断言：REST/SSE）
2) Task 44.2（前端 Zod 事件/响应解析断言）
3) Task 44.3（门禁：CI 阻断策略）

# Verification
- Unit: `pytest -q && npm -C web test`
- Smoke: `backend/scripts/contract_tests_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 44.1 - SSE/REST 契约断言：失败即 `CONTRACT_VIOLATION`

```markdown
# Context
你正在执行子任务：44.1 - SSE/REST 契约断言：失败即 `CONTRACT_VIOLATION`。

# Critical Rules
- **输出前必须校验**。
- **失败必须可定位**: `details` 给出字段路径摘要（去敏）。

# References
- tasks: docs/tasks.md（44.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 为 REST 响应与 SSE 事件定义 Pydantic 模型。
2) 在输出前做校验，失败映射 `CONTRACT_VIOLATION`。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/contract_tests_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（契约覆盖 Evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？（契约失败也需审计）
- [x] Schema（Zod/Pydantic）？（本任务核心）
- [x] 真实集成测试 No Skip？
