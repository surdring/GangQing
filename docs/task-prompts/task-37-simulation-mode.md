# Task 37 - 沙箱仿真与培训模式（F4.5）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 37 组任务：沙箱仿真与培训模式（F4.5）：历史回放、参数滑块推演、风险提示与条款引用。
你的角色是 **技术负责人/架构师**。
你的目标是定义仿真模式隔离策略、回放数据集、推演输出 evidence 与风险提示机制。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default**: 仿真模式强隔离，禁止真实写入。
- **Evidence-First**: 推演输出必须 evidence 化，并引用规程条款/历史案例。
- **RBAC + 审计 + requestId**。
- **结构化错误**: message 英文。
- **Schema 单一事实源**: 前端仿真 UI I/O 用 Zod；后端仿真输出/审计用 Pydantic。
- **真实集成测试（No Skip）**。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F4.5、#272-276）
- TDD: `docs/技术设计文档-最佳实践版.md`（#2.3）
- tasks: `docs/tasks.md`（Task 37）

# Execution Plan
1) Task 37.1 - 后端：仿真模式开关与隔离（禁止真实写入）
2) Task 37.2 - 后端：历史回放数据集与推演输出（Evidence + 条款引用）
3) Task 37.3 - 前端：SIMULATION MODE UI 与风险可视化
4) Task 37.4 - 冒烟：simulation_mode_smoke_test.py + simulation_ui_smoke_test.mjs

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/simulation_mode_smoke_test.py && node web/scripts/simulation_ui_smoke_test.mjs`

# Output Requirement
输出规划（Markdown），不要写实现代码。
```

## Sub-task Prompts

### Task 37.1 - 仿真模式隔离：开关 + 拦截真实写入

```markdown
# Context
你正在执行子任务：37.1 - 仿真隔离。
你的目标是实现仿真模式开关，所有写操作在仿真模式必须被拦截并审计。

# Critical Rules
- **Read-Only Default**。
- **结构化错误**: message 英文。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 37）

# Execution Plan
1) 定义配置与开关。
2) 拦截写路径。

# Verification
- 单元：仿真模式拒绝写。

# Output Requirement
- 输出代码与测试。
```

### Task 37.2 - 历史回放与推演输出（Evidence + 条款引用）

```markdown
# Context
你正在执行子任务：37.2 - 回放与推演。
你的目标是实现历史回放数据读取、推演输出，并附带风险提示与条款引用。

# Critical Rules
- **Evidence-First**。
- **不可验证降级**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 37）

# Execution Plan
1) 定义推演输出模型。
2) 组装 evidence 与 clause refs。

# Verification
- 单元：evidence 字段齐全。

# Output Requirement
- 输出代码与测试。
```

### Task 37.3 - 前端：SIMULATION MODE UI 与风险可视化

```markdown
# Context
你正在执行子任务：37.3 - 仿真 UI。
你的目标是实现仿真模式 UI（水印/警示边框）、滑块推演与风险提示展示。

# Critical Rules
- **TypeScript Strict**。
- **Schema 单一事实源**: Zod 校验推演输出。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 37）

# Execution Plan
1) 定义输出 schema。
2) 实现 UI。

# Verification
- `npm test`。

# Output Requirement
- 输出代码与测试。
```

### Task 37.4 - 冒烟：仿真模式 E2E

```markdown
# Context
你正在执行子任务：37.4 - 仿真冒烟。
你的目标是验证真实链路：进入仿真模式->推演->输出 evidence/风险提示。

# Critical Rules
- **真实集成测试（No Skip）**。

# References
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`
- tasks: `docs/tasks.md`（Task 37）

# Execution Plan
1) 后端冒烟跑推演。
2) 前端冒烟验证 UI。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
