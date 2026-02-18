# Task 22 - 生产工艺智库：参数设定辅助（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 22 组任务：生产工艺智库：参数设定辅助（F3.1）——相似批次检索 + Best Practice 复用 + 不确定项管理。
你的角色是 **技术负责人/架构师**。
你的目标是定义相似批次检索工具、建议输出的证据链与约束清单、以及缺数据时拒答/降级策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Evidence-First**: 建议必须列出约束清单与证据链（相似批次来源、时间窗口、指标口径版本、数据质量）。
- **不可验证降级/拒答**: 缺关键数据必须拒答或降级，不得输出确定性参数。
- **Read-Only Default**: 默认只读；不执行任何写操作。
- **Schema 单一事实源**: 建议输出与 evidence 用 Pydantic；前端展示用 Zod。
- **结构化错误**: message 英文。
- **真实集成测试（No Skip）**: 冒烟必须连接真实数据源并能检索到相似批次。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F3.1）
- TDD: `docs/技术设计文档-最佳实践版.md`（#3.2、#5）
- tasks: `docs/tasks.md`（Task 22）

# Execution Plan
1) Task 22.1 - 相似批次检索工具（事件/物料/设备/窗口）
2) Task 22.2 - 建议生成：约束清单 + evidence + 不确定项
3) Task 22.3 - 冒烟：process_advice_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/process_advice_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 22.1 - 工具：相似批次检索（只读）+ 参数校验

```markdown
# Context
你正在执行子任务：22.1 - 相似批次检索工具。
你的目标是实现检索工具，按设备/物料/事件/时间窗口检索相似批次。

# Critical Rules
- **Schema 单一事实源**: 工具参数 Pydantic。
- **Read-Only Default**: 只读查询。

# References
- tasks: `docs/tasks.md`（Task 22）

# Execution Plan
1) 定义输入参数（窗口/相似度阈值）。
2) 实现查询模板化。

# Verification
- 单元测试：输入校验/空结果。

# Output Requirement
- 输出代码与测试。
```

### Task 22.2 - 建议输出：约束清单 + evidence + 不确定项

```markdown
# Context
你正在执行子任务：22.2 - 建议输出与降级。
你的目标是生成参数建议时强制输出约束清单与 evidence；缺数据则拒答/降级。

# Critical Rules
- **Evidence-First**: 每条建议绑定 citations/time_range/lineage_version。
- **不可验证降级/拒答**: 缺关键输入不输出具体参数。

# References
- PRD: `docs/产品需求.md`（F3.1）
- tasks: `docs/tasks.md`（Task 22）

# Execution Plan
1) 定义输出模型（建议条目 + constraints + uncertainties）。
2) 实现门禁：缺数据 -> warning + 降级。

# Verification
- 单元测试：缺数据拒答。

# Output Requirement
- 输出代码与测试。
```

### Task 22.3 - 冒烟：process_advice_smoke_test.py

```markdown
# Context
你正在执行子任务：22.3 - 工艺建议冒烟。
你的目标是实现冒烟脚本，验证相似批次检索->建议->evidence 全链路。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 22）

# Execution Plan
1) seed/选择存在的批次数据。
2) 发起建议请求并断言 evidence。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（相似批次 citations/lineage/质量）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（明确只读）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（建议在实现时纳入）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
