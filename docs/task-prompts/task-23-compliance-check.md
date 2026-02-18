# Task 23 - 规程合规检查（红线校验）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 23 组任务：规程合规检查（F3.2）：指令/建议的红线校验与越界拦截（输出可追溯条款引用）。
你的角色是 **技术负责人/架构师**。
你的目标是定义红线规则库、拦截输出结构（条款引用 + 风险说明 + evidence）、以及与 ACTION_PREPARE/EXECUTE 的联动策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Read-Only Default**: 任何涉及写/执行的意图必须拦截或进入草案->审批链。
- **Evidence-First**: 拦截原因必须可追溯（条款引用、规则版本、触发输入）。
- **RBAC + 审计 + requestId**: 合规检查与拦截必须审计。
- **结构化错误**: 拦截/拒绝必须结构化（message 英文）。
- **Schema 单一事实源**: 对外合规检查输出必须 Pydantic；前端展示 Zod。
- **真实集成测试（No Skip）**: 冒烟必须连接真实规则库数据源并覆盖至少一条拦截路径。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F3.2、#119-120）
- tasks: `docs/tasks.md`（Task 23）

# Execution Plan
1) Task 23.1 - 红线规则库：条款版本化与可检索
2) Task 23.2 - 合规检查执行器：输入建议/指令 -> 输出拦截结果
3) Task 23.3 - Evidence：条款引用与触发上下文
4) Task 23.4 - 冒烟：compliance_check_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/compliance_check_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 23.1 - 红线规则库：条款/版本/适用范围

```markdown
# Context
你正在执行子任务：23.1 - 红线规则库。
你的目标是建立规则库数据结构（条款、版本、阈值、适用范围）并支持查询。

# Critical Rules
- **Schema 单一事实源**: 规则模型 Pydantic。
- **配置外部化**: 规则不硬编码。

# References
- tasks: `docs/tasks.md`（Task 23）

# Execution Plan
1) 设计表结构或配置格式。
2) 实现加载与查询。

# Verification
- 单元测试：版本选择。

# Output Requirement
- 输出代码与测试。
```

### Task 23.2 - 合规检查执行器：越界拦截 + 风险说明

```markdown
# Context
你正在执行子任务：23.2 - 合规检查执行器。
你的目标是对输入建议/指令执行规则检查，越界时输出结构化拦截结果。

# Critical Rules
- **结构化错误/拦截对象**: message 英文；details 结构化。
- **Read-Only Default**: 命中红线不得进入执行。

# References
- PRD: `docs/产品需求.md`（F3.2）
- tasks: `docs/tasks.md`（Task 23）

# Execution Plan
1) 定义输入模型（建议/指令 + 上下文）。
2) 输出模型（allowed=false + reasons[] + clause_refs[]）。

# Verification
- 单元测试：命中/未命中。

# Output Requirement
- 输出代码与测试。
```

### Task 23.3 - Evidence：条款引用可追溯（clause_ref + rule_version）

```markdown
# Context
你正在执行子任务：23.3 - 拦截证据链。
你的目标是把条款引用与规则版本写入 Evidence，并在 SSE warning/error 中可追溯。

# Critical Rules
- **Evidence-First**: clause_ref 必须可追溯（文档/条款 ID/版本）。

# References
- tasks: `docs/tasks.md`（Task 23）

# Execution Plan
1) 定义 clause citation 模型。
2) 组装 evidence。

# Verification
- 单元：evidence 中包含 clause refs。

# Output Requirement
- 输出代码与测试。
```

### Task 23.4 - 冒烟：compliance_check_smoke_test.py

```markdown
# Context
你正在执行子任务：23.4 - 合规检查冒烟。
你的目标是实现冒烟脚本，验证至少一条红线被拦截并输出证据。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 23）

# Execution Plan
1) seed/加载规则。
2) 发起检查并断言拦截与 evidence。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（条款引用）
- [x] 是否包含只读默认与审批链要求（写意图拦截）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
