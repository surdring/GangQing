# Task 18 - L2 多模态输入：图片/音频上传管线（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 18 组任务：L2 多模态输入：图片/音频上传管线（安全隔离、大小限制、脱敏、审计）。
你的角色是 **技术负责人/架构师**。
你的目标是定义上传接口契约、存储隔离策略、权限与审计、以及与 RAG/诊断编排的对接方式。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端上传 I/O/配置用 Zod；后端上传请求/响应、工具参数、Evidence、审计事件用 Pydantic。
- **RBAC + 审计 + requestId**: 上传必须鉴权、记录审计，贯穿 requestId。
- **数据脱敏与隔离**: 文件存储隔离、大小/格式限制；禁止把原始敏感文件直接回传到 SSE。
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。
- **配置外部化**: 存储路径/对象存储、大小限制、允许类型、超时等必须配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实后端与真实存储（本地文件系统隔离目录也视为真实）；缺配置必须失败并英文报错。
- **Read-Only Default**: 上传属于受控写入，必须满足权限与审计；不得触发任何 OT 写操作。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（F2.1）
- TDD: `docs/技术设计文档-最佳实践版.md`（#14.2、#10）
- tasks: `docs/tasks.md`（Task 18）

# Execution Plan
1) Task 18.1 - 后端：上传接口与存储隔离（Pydantic 契约）
2) Task 18.2 - 编排层：多模态解析->检索->结论与不确定项
3) Task 18.3 - 前端：上传/录音交互与结果可追溯展示
4) Task 18.4 - 冒烟：multimodal_smoke_test（后端+前端）

# Verification
- Unit: `pytest -q && npm test`
- Smoke: `backend/scripts/multimodal_smoke_test.py && node web/scripts/multimodal_ui_smoke_test.mjs`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 18.1 - 后端上传接口：大小/格式限制 + 隔离存储 + 审计

```markdown
# Context
你正在执行子任务：18.1 - 多模态上传接口。
你的目标是实现上传 API，具备权限校验、大小/格式限制、隔离存储与审计。

# Critical Rules
- **RBAC + 审计**: 上传必须鉴权并审计。
- **配置外部化**: 允许类型、大小限制、存储位置必须配置化并校验。
- **结构化错误**: message 英文。

# References
- tasks: `docs/tasks.md`（Task 18）

# Execution Plan
1) 定义 Pydantic 请求/响应模型。
2) 实现文件落盘/对象存储写入（隔离目录）。
3) 记录审计事件。

# Verification
- 冒烟：上传成功与越权/超限失败路径。

# Output Requirement
- 输出代码与测试。
```

### Task 18.2 - 编排层：多模态解析与不确定项输出

```markdown
# Context
你正在执行子任务：18.2 - 多模态编排。
你的目标是将多模态解析结果纳入 Evidence，并在缺信息时输出不确定项。

# Critical Rules
- **Evidence-First**: 结论必须引用解析来源与时间范围。
- **不可验证降级**: 缺关键数据必须降级。

# References
- PRD: `docs/产品需求.md`（F2.1）
- tasks: `docs/tasks.md`（Task 18）

# Execution Plan
1) 定义解析结果模型。
2) 输出 citations 指向上传对象与解析步骤（脱敏）。

# Verification
- 单元：解析失败/缺信息降级。

# Output Requirement
- 输出代码与测试。
```

### Task 18.3 - 前端：上传/录音 UI + 结果可追溯展示

```markdown
# Context
你正在执行子任务：18.3 - 前端多模态 UI。
你的目标是实现上传/录音交互，并确保返回结果通过 Zod 校验且可展示证据链。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: 前端 I/O/配置用 Zod。

# References
- tasks: `docs/tasks.md`（Task 18）

# Execution Plan
1) 定义上传响应与诊断结果 schema。
2) UI：上传、进度、错误、重试。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 18.4 - 冒烟：multimodal_smoke_test.py / multimodal_ui_smoke_test.mjs

```markdown
# Context
你正在执行子任务：18.4 - 多模态冒烟。
你的目标是实现后端与前端冒烟脚本，验证上传->解析->证据链->UI 展示全链路。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 18）

# Execution Plan
1) 后端：上传样本并断言响应结构。
2) 前端：构建后运行并断言 UI 渲染。

# Verification
- 两个冒烟脚本通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（上传与解析 citations）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（上传按受控写入 + 审计）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
