# Task 19 - 设备诊疗专家（EAM 连接器）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 19 组任务：设备诊疗专家（F2.2）：EAM 工单/备件/BOM 查询适配器与证据链输出。
你的角色是 **技术负责人/架构师**。
你的目标是定义 EAM 连接器的只读边界、参数校验、脱敏与 RBAC、Evidence 输出与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Read-Only Default**: EAM 连接器优先只读查询；不得执行写操作。
- **Schema 单一事实源**: 连接器参数与输出必须 Pydantic；前端展示用 Zod。
- **RBAC + 审计 + requestId**: 访问 EAM 数据必须鉴权并审计。
- **Evidence-First**: 工单/备件/BOM 信息必须作为 citations 输出（来源系统、时间范围/更新时间）。
- **结构化错误**: message 英文、字段齐全。
- **配置外部化**: EAM base URL、鉴权、超时、重试不得硬编码。
- **真实集成测试（No Skip）**: 冒烟必须连接真实 EAM 服务；不可用/缺配置必须失败并英文报错。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F2.2）
- TDD: `docs/技术设计文档-最佳实践版.md`（#7、#7.1）
- tasks: `docs/tasks.md`（Task 19）

# Execution Plan
1) Task 19.1 - EAM 连接器配置与参数模型
2) Task 19.2 - 查询接口：工单/备件/BOM（只读）+ 脱敏
3) Task 19.3 - Evidence 输出与审计
4) Task 19.4 - 冒烟：eam_connector_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/eam_connector_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 19.1 - EAM 连接器配置加载与 Pydantic 校验

```markdown
# Context
你正在执行子任务：19.1 - 连接器配置与校验。
你的目标是定义 EAM 配置模型，并实现统一配置加载（外部化 + 校验）。

# Critical Rules
- **配置外部化**: URL/鉴权/超时不得硬编码。
- **结构化错误**: 缺配置必须抛出英文错误。

# References
- tasks: `docs/tasks.md`（Task 19）

# Execution Plan
1) 定义 Pydantic config schema。
2) 加载环境变量并校验。

# Verification
- 单元测试：缺字段失败。

# Output Requirement
- 输出代码与测试。
```

### Task 19.2 - 只读查询：工单/备件/BOM + 脱敏与 RBAC

```markdown
# Context
你正在执行子任务：19.2 - EAM 查询。
你的目标是实现只读查询并执行 RBAC 与脱敏策略。

# Critical Rules
- **Read-Only Default**: 禁止写操作。
- **RBAC + 审计**: 越权必须失败并审计。

# References
- PRD: `docs/产品需求.md`（F2.2）
- tasks: `docs/tasks.md`（Task 19）

# Execution Plan
1) 定义查询参数模型。
2) 实现字段过滤与脱敏。

# Verification
- 单元测试：越权拒绝。

# Output Requirement
- 输出代码与测试。
```

### Task 19.3 - Evidence：工单/备件引用与时间范围/更新时间

```markdown
# Context
你正在执行子任务：19.3 - Evidence 输出。
你的目标是为 EAM 查询结果生成 citations（source_system=EAM、对象 ID、更新时间/时间范围）。

# Critical Rules
- **Evidence-First**: citations 字段必须完整。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#5.2）
- tasks: `docs/tasks.md`（Task 19）

# Execution Plan
1) 组装 evidence citations。
2) 写入审计（tool_call/tool_result）。

# Verification
- 单元测试：evidence 字段存在。

# Output Requirement
- 输出代码与测试。
```

### Task 19.4 - 冒烟：eam_connector_smoke_test.py（真实 EAM）

```markdown
# Context
你正在执行子任务：19.4 - EAM 冒烟。
你的目标是实现 `backend/scripts/eam_connector_smoke_test.py`，连接真实 EAM，验证查询与证据链。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置或服务不可用必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 19）

# Execution Plan
1) 探活 EAM。
2) 发起查询并断言 evidence。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（EAM citations）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（明确只读）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
