# Task 27 - 反馈闭环（RLHF for Industry）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 27 组任务：反馈闭环（RLHF for Industry）：点赞/点踩/纠错 → 待审核队列 → 知识库/规则库/Golden Dataset 回归。
你的角色是 **技术负责人/架构师**。
你的目标是定义反馈数据模型、审核流（最小流程）、与回归集版本记录的契约与验收方案。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端表单 I/O/配置用 Zod；后端反馈/审核/审计事件用 Pydantic。
- **RBAC + 审计 + requestId**: 反馈提交与审核动作必须鉴权并审计。
- **结构化错误**: message 英文。
- **Evidence-First**: 反馈必须关联原请求的 requestId、证据链摘要或引用 ID，避免不可追溯纠错。
- **Read-Only Default**: 知识库/规则库写入属于受控写入，必须走审核流程与审计。
- **真实集成测试（No Skip）**: 冒烟必须连接真实后端与真实数据库；缺配置必须失败并英文报错。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#152-155）
- tasks: `docs/tasks.md`（Task 27）

# Execution Plan
1) Task 27.1 - 前端：纠错入口与表单（Zod 校验）
2) Task 27.2 - 后端：反馈入库与最小审核流（提交/同意/拒绝/追问）
3) Task 27.3 - 回归集更新记录（Golden Dataset 版本记录）
4) Task 27.4 - 冒烟：feedback_loop_smoke_test（后端+前端）

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/feedback_loop_smoke_test.py && node web/scripts/feedback_ui_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 27.1 - 前端：纠错入口与提交表单（Zod）

```markdown
# Context
你正在执行子任务：27.1 - 前端反馈表单。
你的目标是实现纠错入口与表单，并通过 Zod 校验提交数据。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: 前端 I/O 用 Zod。
- **RBAC**: 若需要登录态，未登录应提示并阻断。

# References
- tasks: `docs/tasks.md`（Task 27）

# Execution Plan
1) 定义表单 schema。
2) 实现提交与错误展示。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 27.2 - 后端：反馈入库与审核流（Pydantic + 审计）

```markdown
# Context
你正在执行子任务：27.2 - 反馈入库与审核流。
你的目标是实现反馈提交、审核队列、审核动作（同意/拒绝/追问）并审计。

# Critical Rules
- **Schema 单一事实源**: 请求/响应 Pydantic。
- **RBAC + 审计**: 审核动作必须鉴权并审计。
- **结构化错误**: message 英文。

# References
- tasks: `docs/tasks.md`（Task 27）

# Execution Plan
1) 定义反馈与审核状态模型。
2) 实现 API 与审计。

# Verification
- 单元：状态机转移。

# Output Requirement
- 输出代码与测试。
```

### Task 27.3 - 回归集记录：Golden Dataset 更新与版本关联

```markdown
# Context
你正在执行子任务：27.3 - 回归集更新记录。
你的目标是记录反馈被采纳后，如何更新知识库/规则库/Golden Dataset，并保留版本与审计。

# Critical Rules
- **Evidence-First**: 变更记录必须可追溯到反馈与 requestId。
- **Read-Only Default**: 写入必须经过审核通过后执行。

# References
- PRD: `docs/产品需求.md`（Golden Dataset）
- tasks: `docs/tasks.md`（Task 27）

# Execution Plan
1) 定义版本记录表。
2) 在审核通过时写入记录。

# Verification
- 单元：记录生成。

# Output Requirement
- 输出代码与测试。
```

### Task 27.4 - 冒烟：feedback_loop_smoke_test.py / feedback_ui_smoke_test.mjs

```markdown
# Context
你正在执行子任务：27.4 - 反馈闭环冒烟。
你的目标是验证真实链路：提交反馈->进入队列->审核->记录版本。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 27）

# Execution Plan
1) 后端冒烟：跑通状态机。
2) 前端冒烟：构建后跑表单提交。

# Verification
- 两个冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（反馈关联 requestId/evidence 摘要）
- [x] 是否包含只读默认与审批链要求（写入需审核）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
