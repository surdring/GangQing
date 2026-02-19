### Task 32 - 物理边界/变化率一致性校验（关键数值防幻觉）：越界阻断或降级（Umbrella）

```markdown
# Context
你正在执行第 32 号任务：物理边界/变化率一致性校验（关键数值防幻觉）。
角色：**技术负责人/架构师**。
目标是规划关键数值的合理区间/变化率阈值、版本化管理、命中行为（阻断或降级）、证据链记录规则版本，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Guardrail 强制**: 越界必须阻断（`GUARDRAIL_BLOCKED`）或降级为“仅展示数据与来源”（按设计与风险分级）。
- **Evidence-First（强制）**: 命中规则必须写入 Evidence（ruleId/thresholdVersion 摘要 + timeRange）。
- **结构化错误（强制）**: 英文 message，包含 `retryable/requestId`。
- **配置外部化（强制）**: 阈值与版本不得硬编码。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R17.3/R14.4）
- TDD: docs/design.md（5.1.3）
- tasks: docs/tasks.md（任务 32）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 32.1（阈值模型：区间/变化率/版本）
2) Task 32.2（命中行为：阻断 vs 降级）
3) Task 32.3（证据与审计：规则命中记录）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/physical_guardrail_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 32.1 - 物理阈值与变化率规则：版本化与可追溯记录

```markdown
# Context
你正在执行子任务：32.1 - 物理阈值与变化率规则：版本化与可追溯记录。

# Critical Rules
- **阈值必须版本化**。
- **Evidence 记录阈值版本摘要**。

# References
- tasks: docs/tasks.md（32.1）

# Execution Plan
1) 定义规则 schema。
2) 实现校验与记录。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/physical_guardrail_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（阈值命中 Evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
