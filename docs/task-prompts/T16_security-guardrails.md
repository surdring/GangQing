### Task 16 - 高风险意图/提示词注入防护：策略化拦截 + 审计留痕（Umbrella）

```markdown
# Context
你正在执行第 16 号任务：高风险意图/提示词注入防护：策略化拦截 + 审计留痕。
角色：**技术负责人/架构师**。
目标是规划注入检测（直接/间接）、输出安全校验、越权/写意图拦截策略、证据链记录规则 ID 与原因摘要，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Guardrail 强制**:
  - 越权/敏感查询 => `FORBIDDEN`
  - 写操作倾向/红线 => `GUARDRAIL_BLOCKED`
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。
- **审计留痕（强制）**: 记录命中规则 ID 与原因摘要（禁止敏感细节），并可按 `requestId` 检索。
- **Read-Only Default（强制）**。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R10.1/R10.3/R17.2）
- TDD: docs/design.md（4.1/4.2/3.10）
- tasks: docs/tasks.md（任务 16）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 16.1（注入检测：直接/间接）
2) Task 16.2（策略化拦截：越权/写意图/敏感信息）
3) Task 16.3（证据链与审计：规则 ID 记录）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/security_guardrail_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 16.1 - 注入检测与输出安全校验

```markdown
# Context
你正在执行子任务：16.1 - 注入检测与输出安全校验。
目标是识别注入特征并拒绝/降级，避免泄露系统提示词或敏感信息。

# Critical Rules
- **输出不得包含系统提示词**。
- **审计**: 记录检测命中。

# References
- tasks: docs/tasks.md（16.1）
- PRD: docs/requirements.md（R10.1/R10.3）

# Execution Plan
1) 定义注入特征规则集（可配置）。
2) 在输入与输出阶段分别做校验。

# Verification
- **Unit**: `pytest -q` 覆盖：注入样本被拦截。
- **Smoke**: `backend/scripts/security_guardrail_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 16.2 - 拦截与证据链记录：规则 ID + 原因摘要

```markdown
# Context
你正在执行子任务：16.2 - 拦截与证据链记录：规则 ID + 原因摘要。

# Critical Rules
- **结构化错误**: `GUARDRAIL_BLOCKED`/`FORBIDDEN`。
- **证据链**: 记录规则 ID 与原因摘要（不含敏感细节）。

# References
- tasks: docs/tasks.md（16.2）
- contracts: docs/contracts/api-and-events-draft.md（Evidence/Audit）

# Execution Plan
1) 拦截时输出结构化错误，并在 evidence/audit 中记录 ruleId。
2) SSE 流中输出 `warning` 或 `error`（按策略）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/security_guardrail_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（记录 ruleId 与降级）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
