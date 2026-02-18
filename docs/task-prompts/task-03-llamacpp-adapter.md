# Task 3 - 建立模型推理适配层（llama.cpp 网关/适配器）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 3 组任务：建立模型推理适配层（llama.cpp 网关/适配器：超时、并发、配额、观测）。
你的角色是 **技术负责人/架构师**。
你的目标是定义模型适配器的边界、错误映射、并发/超时/配额策略、观测字段与验收方案。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic；前端 I/O/配置用 Zod。
- **结构化错误**: `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **配置外部化**: llama.cpp URL、超时、并发上限、队列长度等必须配置化并校验。
- **RBAC + 审计 + requestId**: 模型调用也要与 requestId 关联（日志/审计/trace）。
- **Evidence-First**: 任何关键结论必须可追溯；模型输出若用于计划/证据链结构化，必须 schema 校验，失败要重试或降级。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实 llama.cpp 服务；缺配置/不可用必须失败并输出英文错误。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`
- TDD: `docs/技术设计文档-最佳实践版.md`（#9、#3.4、#12）
- tasks: `docs/tasks.md`（Task 3）

# Execution Plan
1) Task 3.1 - 适配器接口与配置模型
- Deliverables: 统一的 `LLMClient`/adapter 接口定义、配置加载与校验（Pydantic）。

2) Task 3.2 - 超时/并发/队列与配额
- Decisions: 并发控制策略、排队与拒绝策略（结构化错误码）、不同错误 retryable 判定。

3) Task 3.3 - 输出约束与 schema 校验
- Goal: 对关键结构化输出（意图/计划/证据链片段/错误对象）做校验，不通过则重试或降级为安全输出。

4) Task 3.4 - 观测与审计字段
- Deliverables: tokens/latency（可用则记录）与 requestId 关联。

# Verification
- Unit Tests: `pytest -q`
- Smoke Tests: `backend/scripts/llamacpp_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 3.1 - 新增 llama.cpp 适配器模块与配置校验

```markdown
# Context
你正在执行子任务：3.1 - llama.cpp 适配器模块与配置校验。
你的目标是新增/完善模型适配器模块，支持与 llama.cpp 通信，并确保所有配置外部化且校验。

# Critical Rules
- **配置外部化**: URL/超时/并发/配额不得硬编码。
- **Schema 单一事实源**: 配置与对外数据结构用 Pydantic 定义并校验。
- **结构化错误**: 对外错误必须字段齐全且 message 英文。
- **真实集成测试（No Skip）**: 缺少 llama.cpp 地址或服务不可用，冒烟测试必须失败并给出英文错误。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#9）
- tasks: `docs/tasks.md`（Task 3）

# Execution Plan
1) 定义配置模型（llama.cpp base URL、超时、并发、最大排队）。
2) 实现最小请求/响应适配与错误映射。
3) 在日志中关联 `requestId`。

# Verification
- 单元：覆盖超时/不可达/错误码映射。
- 冒烟：`backend/scripts/llamacpp_smoke_test.py`。

# Output Requirement
- 输出所有新增/修改文件与测试。
```

### Task 3.2 - 并发/配额/队列策略与错误码映射

```markdown
# Context
你正在执行子任务：3.2 - 并发/配额/队列策略。
你的目标是实现并发限制、队列与拒绝策略，并把拒绝映射为结构化错误。

# Critical Rules
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。
- **可观测性**: 记录队列长度、等待时长（若可用）。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#9.2、#12）
- tasks: `docs/tasks.md`（Task 3）

# Execution Plan
1) 设计队列满/超时/配额不足的错误码与 retryable。
2) 实现并发控制逻辑并打点日志。

# Verification
- 单元测试覆盖：队列满、超时、配额不足。

# Output Requirement
- 输出代码与测试。
```

### Task 3.3 - 关键结构化输出 schema 校验与降级

```markdown
# Context
你正在执行子任务：3.3 - 输出校验与降级。
你的目标是对模型输出中的关键结构（如意图分类结果/计划片段/错误对象）做 schema 校验，失败时重试或降级。

# Critical Rules
- **Schema 单一事实源**: 校验 schema 必须由 Pydantic 定义。
- **Evidence-First**: 不可验证或校验失败不得输出确定性数值结论。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#9.2、#3.4）
- tasks: `docs/tasks.md`（Task 3）

# Execution Plan
1) 定义结构化输出的 Pydantic 模型。
2) 校验失败：有限次重试；仍失败则降级为安全的只读输出（必要时输出 warning）。

# Verification
- 单元测试覆盖：校验失败、重试耗尽、降级输出。

# Output Requirement
- 输出代码与测试。
```

### Task 3.4 - 观测字段与 requestId 关联

```markdown
# Context
你正在执行子任务：3.4 - 观测字段与 requestId 关联。
你的目标是记录 latency/tokens（若可用）并与 requestId 关联，方便定位性能问题。

# Critical Rules
- **可观测性**: 结构化字段稳定。
- **RBAC/审计**: 不记录敏感内容原文；只记录必要统计与摘要。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#12）
- tasks: `docs/tasks.md`（Task 3）

# Execution Plan
1) 在模型调用前后记录开始/结束时间、耗时。
2) 若 llama.cpp 返回 token 使用信息，结构化记录。

# Verification
- 单元测试覆盖：字段存在与 requestId 关联。

# Output Requirement
- 输出代码与测试。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局硬约束写入）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
