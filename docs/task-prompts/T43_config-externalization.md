### Task 43 - 配置外部化与配置校验：`.env.example` 完整列举 + 启动快速失败（英文错误）（Umbrella）

```markdown
# Context
你正在执行第 43 号任务：配置外部化与配置校验。
角色：**技术负责人/架构师**。
目标是规划统一配置加载机制、配置 schema 校验、关键配置缺失的快速失败策略（英文错误）、以及 `.env.example` 文档化要求。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **配置外部化（强制）**: URL/端口/超时/重试/API Key 禁止硬编码。
- **Schema 单一事实源（强制）**:
  - 前端配置用 Zod schema 校验。
  - 后端配置用 Pydantic（或统一配置模块）校验。
- **缺配置必须失败（强制）**: 不得 skip，不得 silent default。
- **结构化错误（强制）**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R14.5）
- TDD: docs/design.md（2.9）
- tasks: docs/tasks.md（任务 43）
- contracts: docs/contracts/api-and-events-draft.md
- env: .env.example

# Execution Plan
1) Task 43.1（统一配置加载：前端/后端）
2) Task 43.2（schema 校验与错误消息规范）
3) Task 43.3（`.env.example` 完整性与文档同步）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/config_validation_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 43.1 - 配置加载与 schema 校验：缺配置快速失败（英文错误）

```markdown
# Context
你正在执行子任务：43.1 - 配置加载与 schema 校验：缺配置快速失败（英文错误）。

# Critical Rules
- **不得硬编码**。
- **错误 message 英文**。

# References
- tasks: docs/tasks.md（43.1）
- TDD: docs/design.md（2.9）

# Execution Plan
1) 后端实现配置模型与加载。
2) 前端实现配置 schema 与加载。
3) 缺配置直接抛错并使测试失败。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/config_validation_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？（配置错误也应结构化或清晰异常）
- [x] 证据链要求与字段？（不适用，但全局规则保留）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？（如配置涉及审计开关也需）
- [x] Schema（Zod/Pydantic）？（本任务核心）
- [x] 真实集成测试 No Skip？
