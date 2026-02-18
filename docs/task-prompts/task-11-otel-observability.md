# Task 11 - 可观测性：OpenTelemetry traces/metrics（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 11 组任务：可观测性：OpenTelemetry traces/metrics（建议项落地为生产级基线）。
你的角色是 **技术负责人/架构师**。
你的目标是定义 trace/span/metric 基线、关键属性字段、与 requestId 的关联方式，并制定验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **RBAC + 审计 + requestId 贯穿**: 观测数据必须能关联 requestId，不得泄露敏感信息。
- **配置外部化**: OTel exporter/endpoint/采样率必须配置化并校验。
- **结构化错误**: 对外错误模型字段齐全（message 英文）。
- **真实集成测试（No Skip）**: 冒烟测试需在真实服务启动下验证关键 span/metric 至少能产生（如依赖 collector，缺配置必须失败并输出英文错误）。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- TDD: `docs/技术设计文档-最佳实践版.md`（#12）
- tasks: `docs/tasks.md`（Task 11）

# Execution Plan
1) Task 11.1 - Trace：关键 span 定义与属性
2) Task 11.2 - Metrics：请求量/错误率/P95-P99/工具失败率等
3) Task 11.3 - 冒烟：otel_smoke_test.py 验证最小可用

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/otel_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 11.1 - Trace：span 基线与 requestId/sessionId 关联

```markdown
# Context
你正在执行子任务：11.1 - Trace span 基线。
你的目标是为关键链路打点：`http.request/intent.classify/tool.postgres.query/llm.generate/evidence.build`。

# Critical Rules
- **可观测性字段稳定**: span attributes 至少包含 requestId/sessionId/toolName/status/errorCode。
- **脱敏**: 不记录用户原文与敏感数据。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#12.1）
- tasks: `docs/tasks.md`（Task 11）

# Execution Plan
1) 接入 OTel SDK。
2) 在关键函数边界创建 span 并附加属性。

# Verification
- 单元：span 创建/属性存在（允许通过依赖注入 fake tracer 实现，不允许 mock 外部系统）。

# Output Requirement
- 输出代码与测试。
```

### Task 11.2 - Metrics：延迟与错误率基线

```markdown
# Context
你正在执行子任务：11.2 - Metrics 基线。
你的目标是增加请求量、错误率、P95/P99、工具失败率、模型队列长度等指标。

# Critical Rules
- **配置外部化**: exporter 配置必须来自环境变量。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#12.2）
- tasks: `docs/tasks.md`（Task 11）

# Execution Plan
1) 定义 metrics 名称与标签。
2) 在关键路径上报。

# Verification
- 单元：指标对象存在并可递增。

# Output Requirement
- 输出代码与测试。
```

### Task 11.3 - 冒烟：otel_smoke_test.py

```markdown
# Context
你正在执行子任务：11.3 - OTel 冒烟测试。
你的目标是实现 `backend/scripts/otel_smoke_test.py`，在真实服务启动下验证最小 span/metric 可产生。

# Critical Rules
- **真实集成测试（No Skip）**: 缺少 collector/exporter 配置必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 11）

# Execution Plan
1) 启动服务并发起真实请求。
2) 断言本地 exporter 或日志中出现关键 span 名称（按实现方式）。

# Verification
- 冒烟脚本通过。

# Output Requirement
- 输出脚本与相关配置说明（不新增文档时可在代码注释最小化说明）。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局硬约束写入）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
