### Task 36 - 只读默认门禁强化：识别写意图并强制进入草案/审批流程（禁止直接执行）（Umbrella）

```markdown
# Context
你正在执行第 36 号任务：只读默认门禁强化。
角色：**技术负责人/架构师**。
目标是规划“写意图识别 -> 只读默认拦截 -> 草案/审批入口”的强制门禁，覆盖 API/工具双层，且可审计可回放。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default（强制）**: 任何不明确或高风险请求按只读处理；写意图必须进入草案/审批链路。
- **结构化错误（强制）**: 拦截返回 `GUARDRAIL_BLOCKED` 或 `FORBIDDEN`（按 contracts），英文 `message`，字段齐全。
- **RBAC + 审计 + requestId（强制）**: 拦截规则 ID 与原因摘要写审计，按 `requestId` 可聚合。
- **配置外部化（强制）**: 门禁开关/策略规则不得硬编码。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R5.1）
- TDD: docs/design.md（1.7/3.6.1）
- tasks: docs/tasks.md（任务 36）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 36.1（写意图识别与分类对齐）
2) Task 36.2（门禁拦截与响应：草案/审批引导）
3) Task 36.3（审计取证：ruleId + reason）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/read_only_default_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 36.1 - 写意图门禁：拦截并引导进入草案/审批

```markdown
# Context
你正在执行子任务：36.1 - 写意图门禁：拦截并引导进入草案/审批。

# Critical Rules
- **禁止执行写操作**。
- **结构化错误/提示**: 返回结构化错误或结构化“需要审批”的响应（按实现约定）。

# References
- tasks: docs/tasks.md（36.1）
- contracts: docs/contracts/api-and-events-draft.md（只读默认/写操作）

# Execution Plan
1) 将 ACTION_* 意图统一走只读默认门禁。
2) 输出可执行引导：生成草案的入口与所需权限。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/read_only_default_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（门禁命中也需 evidence/audit 记录摘要）
- [x] 只读默认与审批链？（本任务核心）
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
