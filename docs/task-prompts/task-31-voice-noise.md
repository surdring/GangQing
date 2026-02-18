# Task 31 - 抗噪与语音交互策略（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 31 组任务：抗噪与语音交互策略：语音优先 + 降噪策略 + 自动降级为文字交互。
你的角色是 **技术负责人/架构师**。
你的目标是定义前端语音采集与降级策略、后端 ASR 适配与审计、以及弱网/噪声场景验收。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端语音 I/O/配置用 Zod；后端转写 I/O/审计用 Pydantic。
- **结构化错误**: message 英文。
- **配置外部化**: ASR 服务地址/超时/重试配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实 ASR 服务；缺配置必须失败并英文报错。
- **RBAC + 审计 + requestId**: 语音请求也必须审计，关联 requestId。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#105-110、#230-249）
- tasks: `docs/tasks.md`（Task 31）

# Execution Plan
1) Task 31.1 - 前端：语音采集与噪声探测、自动降级
2) Task 31.2 - 后端：ASR 适配器与审计
3) Task 31.3 - 冒烟：voice_smoke_test（前端）+ asr_smoke_test（后端）

# Verification
- Unit: `npm test && pytest -q`
- Smoke: `node web/scripts/voice_smoke_test.mjs && backend/scripts/asr_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 31.1 - 前端：语音采集 + 降噪探测 + 自动降级

```markdown
# Context
你正在执行子任务：31.1 - 前端语音交互。
你的目标是实现语音采集、噪声环境探测，并在不可用时自动降级为文字交互。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: 语音配置 Zod。

# References
- tasks: `docs/tasks.md`（Task 31）

# Execution Plan
1) 定义配置 schema。
2) 实现降级策略与 UI。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 31.2 - 后端：ASR 接口适配 + 审计

```markdown
# Context
你正在执行子任务：31.2 - 后端 ASR 适配。
你的目标是实现语音转写接口适配并审计。

# Critical Rules
- **配置外部化**: ASR 服务地址不得硬编码。
- **结构化错误**: message 英文。

# References
- tasks: `docs/tasks.md`（Task 31）

# Execution Plan
1) 定义 Pydantic 请求/响应。
2) 调用真实 ASR 并映射错误。

# Verification
- `pytest -q` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 31.3 - 冒烟：voice_smoke_test.mjs + asr_smoke_test.py

```markdown
# Context
你正在执行子任务：31.3 - 语音冒烟。
你的目标是验证真实链路：前端采集->后端转写->返回文本->进入对话。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 31）

# Execution Plan
1) 后端冒烟：探活 ASR 并转写样本。
2) 前端冒烟：构建后触发语音流程。

# Verification
- 两个冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（语音输入可追溯到上传/转写，按适用性）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
