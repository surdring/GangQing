# Task 28 - Golden Dataset 与自动化评估（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 28 组任务：Golden Dataset 与自动化评估：覆盖术语/故障/SOP/指标口径/红线拦截 的回归体系。
你的角色是 **技术负责人/架构师**。
你的目标是定义金标准数据结构、版本管理、评估指标口径与验收门禁。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 评估数据与结果对外模型用 Pydantic；前端展示/配置用 Zod。
- **Evidence-First**: 评估样本必须包含期望 evidence 要点（至少来源与时间范围/口径版本），防止“只看文本不看证据”。
- **结构化错误**: 评估执行失败必须结构化（message 英文）。
- **配置外部化**: 评估阈值、数据集路径、外部服务地址配置化并校验。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实服务（后端 + 模型 + DB）；缺配置必须失败。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#37-39）
- TDD: `docs/技术设计文档-最佳实践版.md`（#13）
- tasks: `docs/tasks.md`（Task 28）

# Execution Plan
1) Task 28.1 - 金标准数据结构与版本管理
2) Task 28.2 - 评估执行器：跑样本->收集 SSE/证据链->打分
3) Task 28.3 - 报表与门禁阈值（准确率/拒答率/升级人工比例）
4) Task 28.4 - 冒烟：eval_golden_dataset_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/eval_golden_dataset_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 28.1 - Golden Dataset schema 与版本管理

```markdown
# Context
你正在执行子任务：28.1 - Golden Dataset schema。
你的目标是定义样本 schema（输入、期望意图、期望 evidence 要点、期望错误码等）与版本管理机制。

# Critical Rules
- **Schema 单一事实源**: schema 用 Pydantic。
- **Evidence-First**: 样本必须包含 evidence 断言点。

# References
- tasks: `docs/tasks.md`（Task 28）

# Execution Plan
1) 定义样本模型。
2) 定义版本与变更记录。

# Verification
- 单元：schema 校验。

# Output Requirement
- 输出代码与测试。
```

### Task 28.2 - 评估执行器：真实服务回归（不可 mock）

```markdown
# Context
你正在执行子任务：28.2 - 评估执行器。
你的目标是对每条样本发起真实请求（SSE），收集结构化事件与 evidence，并计算指标。

# Critical Rules
- **真实集成测试（No Skip）**: 必须连接真实服务，禁止 mock。
- **结构化错误**: message 英文。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#13.2）
- tasks: `docs/tasks.md`（Task 28）

# Execution Plan
1) 逐条样本发请求。
2) 断言 SSE 事件与 evidence schema。

# Verification
- 单元：指标计算。

# Output Requirement
- 输出代码与测试。
```

### Task 28.3 - 门禁：阈值与报表输出（结构化）

```markdown
# Context
你正在执行子任务：28.3 - 评估门禁。
你的目标是实现阈值判断与结构化报表输出，并在不达标时返回结构化错误。

# Critical Rules
- **结构化错误**: 阈值失败也要结构化。
- **配置外部化**: 阈值配置化。

# References
- PRD: `docs/产品需求.md`（评估与防护栏）
- tasks: `docs/tasks.md`（Task 28）

# Execution Plan
1) 定义阈值配置模型。
2) 生成报表并判断 pass/fail。

# Verification
- 单元：pass/fail 分支。

# Output Requirement
- 输出代码与测试。
```

### Task 28.4 - 冒烟：eval_golden_dataset_smoke_test.py

```markdown
# Context
你正在执行子任务：28.4 - Golden Dataset 冒烟。
你的目标是运行一小批样本验证真实服务可回归，并输出报表。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 28）

# Execution Plan
1) 读取样本与配置。
2) 发请求并生成报表。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（样本断言 evidence）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（通过真实请求覆盖）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
