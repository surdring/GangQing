### Task 30 - 规程合规检查与红线拦截（强制）：命中返回 `GUARDRAIL_BLOCKED` 并附规程引用（Umbrella）

```markdown
# Context
你正在执行第 30 号任务：规程合规检查与红线拦截（强制）。
角色：**技术负责人/架构师**。
目标是规划规程规则库（条款/红线阈值/版本）、命中行为（拦截/警告）、引用输出（规程引用 + Evidence）、以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Guardrail 强制**:
  - 违反红线 => 必须拦截并返回 `GUARDRAIL_BLOCKED`。
  - 接近红线 => 输出 `warning` 事件。
- **Evidence-First（强制）**: 拦截/警告必须引用规程条款与版本，形成 Evidence。
- **结构化错误（强制）**: `GUARDRAIL_BLOCKED` 错误结构化，英文 message。
- **RBAC + 审计（强制）**: 命中规则写审计，记录 ruleId 与原因摘要。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R4.2）
- TDD: docs/design.md（3.8）
- tasks: docs/tasks.md（任务 30）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 30.1（规则表示：条款/阈值/版本）
2) Task 30.2（命中行为：拦截与 warning）
3) Task 30.3（Evidence 与审计：ruleId/引用）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/sop_compliance_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 30.1 - 合规规则库：条款引用、版本化与可追溯输出

```markdown
# Context
你正在执行子任务：30.1 - 合规规则库：条款引用、版本化与可追溯输出。

# Critical Rules
- **规则必须版本化**。
- **Evidence 必须包含条款定位**。

# References
- tasks: docs/tasks.md（30.1）
- PRD: docs/requirements.md（R4.2）

# Execution Plan
1) 定义规则 schema（Pydantic）。
2) 定义引用格式：文档名/章节/条款号。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/sop_compliance_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（规程引用）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
