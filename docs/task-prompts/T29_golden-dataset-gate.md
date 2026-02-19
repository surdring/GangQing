### Task 29 - Golden Dataset 回归与发布门禁：模型/Prompt/工具链变更触发全量评估（Umbrella）

```markdown
# Context
你正在执行第 29 号任务：Golden Dataset 回归与发布门禁：模型/Prompt/工具链变更触发全量评估。
角色：**技术负责人/架构师**。
目标是规划 Golden Dataset 的数据结构、评估指标（准确率/拒答率/升级人工比例）、报告产物、以及“指标下降阻断发布”的门禁策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 评估样本与结论必须可追溯到输入、期望输出与证据（至少记录来源与版本）。
- **契约一致性（强制）**: 评估输出报告必须结构化并可被机器解析；错误模型字段齐全。
- **真实集成测试（No Skip）**: 回归测试必须连接真实服务（模型/工具/数据库），配置缺失必须失败。
- **配置外部化（强制）**: 阈值、样本集路径、运行模式不得硬编码。

# References
- PRD: docs/requirements.md（R17.1）
- TDD: docs/design.md（3.10）
- tasks: docs/tasks.md（任务 29）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 29.1（Golden Dataset 结构与版本化）
2) Task 29.2（评估运行器：真实服务端到端）
3) Task 29.3（发布门禁：阈值与差异样本清单）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/golden_dataset_regression_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 29.1 - Golden Dataset：样本结构、版本证据与可追溯输出

```markdown
# Context
你正在执行子任务：29.1 - Golden Dataset：样本结构、版本证据与可追溯输出。

# Critical Rules
- **样本必须可追溯**: 记录输入、期望、证据引用（如适用）。
- **不允许 skip**。

# References
- tasks: docs/tasks.md（29.1）
- PRD: docs/requirements.md（R17.1）

# Execution Plan
1) 定义样本 schema（Pydantic）与版本字段。
2) 定义报告 schema（含差异样本清单）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/golden_dataset_regression_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（评估证据/版本）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？（评估运行也要可审计）
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
