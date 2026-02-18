# Task 21 - L3 物理边界与变化率 guardrail（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 21 组任务：L3 物理边界与变化率 guardrail：关键参数一致性校验与降级。
你的角色是 **技术负责人/架构师**。
你的目标是定义规则库形式、触发策略、降级输出（warning + 不确定项）、审计记录与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Evidence-First**: guardrail 触发必须写入 evidence（触发规则、阈值版本、输入数据源与时间范围）。
- **不可验证降级**: 越界必须输出 `warning` 并降级为“仅展示数据与来源/需人工复核”。
- **结构化错误**: message 英文（错误与警告对象字段结构化）。
- **RBAC + 审计 + requestId**: 触发必须审计，关联 requestId。
- **Schema 单一事实源**: 对外 guardrail 事件/输出用 Pydantic；前端展示用 Zod。
- **真实集成测试（No Skip）**: 冒烟必须连接真实数据源并触发至少一条 guardrail。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#39）
- TDD: `docs/技术设计文档-最佳实践版.md`（#3.2）
- tasks: `docs/tasks.md`（Task 21）

# Execution Plan
1) Task 21.1 - 规则库与版本化（区间/变化率）
2) Task 21.2 - guardrail 执行器与降级策略（warning 事件）
3) Task 21.3 - 前端展示：降级提示与证据链联动
4) Task 21.4 - 冒烟：guardrail_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/guardrail_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 21.1 - 规则库：物理区间/变化率模型（Pydantic）与版本化

```markdown
# Context
你正在执行子任务：21.1 - 规则库模型。
你的目标是定义规则模型（参数名、区间、变化率、适用范围、版本）并支持查询。

# Critical Rules
- **Schema 单一事实源**: 规则与输出模型 Pydantic。
- **配置外部化**: 规则不硬编码在代码里（可落 DB 或配置文件并校验）。

# References
- tasks: `docs/tasks.md`（Task 21）

# Execution Plan
1) 定义规则 schema。
2) 实现加载/查询。

# Verification
- 单元测试：规则解析与版本选择。

# Output Requirement
- 输出代码与测试。
```

### Task 21.2 - guardrail 执行与降级：warning + evidence

```markdown
# Context
你正在执行子任务：21.2 - guardrail 执行与降级。
你的目标是对关键参数做一致性校验，越界则降级输出 warning，并写入 evidence。

# Critical Rules
- **不可验证降级**: 越界不得输出确定性建议。
- **Evidence-First**: 记录触发规则版本与输入数据源/time_range。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#3.2）
- tasks: `docs/tasks.md`（Task 21）

# Execution Plan
1) 执行器输入：数据点/时间序列。
2) 输出：warning 事件 + evidence 更新。

# Verification
- 单元测试：触发/不触发、边界值。

# Output Requirement
- 输出代码与测试。
```

### Task 21.3 - 前端：降级态展示（仅展示数据与来源/需人工复核）

```markdown
# Context
你正在执行子任务：21.3 - 前端降级态展示。
你的目标是把 guardrail warning 与 evidence 结合展示，并提示用户需要人工复核。

# Critical Rules
- **Schema 单一事实源**: 前端事件与 evidence 用 Zod。

# References
- tasks: `docs/tasks.md`（Task 21）

# Execution Plan
1) 定义 warning 事件 schema。
2) UI 显示降级原因与引用。

# Verification
- `npm test`（如涉及前端）通过。

# Output Requirement
- 输出代码与测试。
```

### Task 21.4 - 冒烟：guardrail_smoke_test.py

```markdown
# Context
你正在执行子任务：21.4 - guardrail 冒烟。
你的目标是实现冒烟脚本，制造越界数据并验证 warning/evidence。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 21）

# Execution Plan
1) 写入/选择越界样本（通过 seed 数据）。
2) 发起分析请求并断言 warning。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（guardrail 触发证据）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
