# Task 29 - 数据质量评估前置（Data Sanitation）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 29 组任务：数据质量评估前置：缺失/漂移/异常/造假风险/口径一致性 的检测与分级。
你的角色是 **技术负责人/架构师**。
你的目标是定义数据质量规则、评分模型、Evidence 展示字段与告警策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Evidence-First**: Evidence 中必须展示数据质量等级与影响说明。
- **结构化错误**: message 英文。
- **Schema 单一事实源**: 质量评估结果对外模型 Pydantic；前端展示 Zod。
- **配置外部化**: 质量规则阈值配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实数据库并覆盖异常样本。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#155-158）
- tasks: `docs/tasks.md`（Task 29）

# Execution Plan
1) Task 29.1 - 质量规则库与评分模型
2) Task 29.2 - 评估执行器与 Evidence 字段输出
3) Task 29.3 - 看板/告警接口（可选）
4) Task 29.4 - 冒烟：data_quality_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/data_quality_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 29.1 - 质量规则模型（缺失/漂移/异常）与评分

```markdown
# Context
你正在执行子任务：29.1 - 质量规则与评分。
你的目标是定义质量规则与评分结果模型。

# Critical Rules
- **Schema 单一事实源**: 模型 Pydantic。
- **配置外部化**: 阈值不硬编码。

# References
- tasks: `docs/tasks.md`（Task 29）

# Execution Plan
1) 定义规则与等级。
2) 计算评分。

# Verification
- 单元：等级边界。

# Output Requirement
- 输出代码与测试。
```

### Task 29.2 - Evidence：输出质量等级与不确定项

```markdown
# Context
你正在执行子任务：29.2 - Evidence 质量字段。
你的目标是在 evidence 中输出质量等级与影响，并在低质量时触发 warning/降级。

# Critical Rules
- **Evidence-First**: 质量等级必须随 evidence 输出。
- **不可验证降级**: 低质量不得输出确定性数值。

# References
- PRD: `docs/产品需求.md`（数据质量前置）
- tasks: `docs/tasks.md`（Task 29）

# Execution Plan
1) 扩展 Evidence 模型。
2) 在生成回答前评估质量。

# Verification
- 单元：低质量 -> warning。

# Output Requirement
- 输出代码与测试。
```

### Task 29.4 - 冒烟：data_quality_smoke_test.py

```markdown
# Context
你正在执行子任务：29.4 - 数据质量冒烟。
你的目标是连接真实数据库并验证质量评估与 evidence 字段。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 29）

# Execution Plan
1) 选择包含异常的 seed 数据。
2) 发起评估并断言 evidence.

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（质量等级）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（建议在实现中加入）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
