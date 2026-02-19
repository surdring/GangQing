### Task 34 - 数据质量评估前置：缺失/漂移/异常/延迟评分，低质量拒绝确定性结论（Umbrella）

```markdown
# Context
你正在执行第 34 号任务：数据质量评估前置。
角色：**技术负责人/架构师**。
目标是规划数据质量评分模型、阈值与拒答/降级策略、Evidence 中的 `dataQualityScore` 与问题列表，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: `dataQualityScore` 与质量问题必须进入 Evidence。
- **低质量拒绝确定性结论（强制）**: 低于阈值必须拒答或降级为“仅展示数据与来源/不确定项”。
- **结构化错误（强制）**: 低质量拒答使用结构化错误码（按 tasks/design，可能为 `EVIDENCE_MISSING` 或 domain 错误码），英文 message。
- **配置外部化（强制）**: 阈值/权重/算法不得硬编码。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R16.3）
- TDD: docs/design.md（5.5）
- tasks: docs/tasks.md（任务 34）
- contracts: docs/contracts/api-and-events-draft.md（Evidence dataQualityScore）
- api docs: docs/api/data-api.md

# Execution Plan
1) Task 34.1（评分模型与 issues 结构）
2) Task 34.2（拒答/降级策略与 SSE warning）
3) Task 34.3（配置化权重与算法）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/data_quality_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 34.1 - 数据质量评分：issues 列表 + dataQualityScore

```markdown
# Context
你正在执行子任务：34.1 - 数据质量评分：issues 列表 + dataQualityScore。

# Critical Rules
- **评分与 issues 必须结构化**。
- **message 英文**（issues 中的 message 也必须英文）。

# References
- tasks: docs/tasks.md（34.1）
- api docs: docs/api/data-api.md

# Execution Plan
1) 定义 QualityReport Pydantic 模型。
2) 实现缺失/异常/漂移/质量码评分。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/data_quality_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？（含 issues.message）
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（dataQualityScore）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
