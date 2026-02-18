# Task 26 - Token 预算与配额：路由/缓存/模板化（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 26 组任务：Token 预算与配额：SLM/LLM 路由、缓存与高频问题模板化（成本治理）。
你的角色是 **技术负责人/架构师**。
你的目标是定义配额模型、缓存策略、路由策略（SLM/LLM）、以及可观测指标与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **RBAC + 审计 + requestId 贯穿**: 配额命中/拒绝必须可审计，关联 requestId。
- **结构化错误**: 配额不足/拒绝必须结构化（message 英文）。
- **配置外部化**: 配额阈值、缓存 TTL、路由策略配置化并校验。
- **Evidence-First**: 缓存命中时仍需输出 evidence（来源=cache，且标注原始数据来源与时间范围）。
- **真实集成测试（No Skip）**: 冒烟必须连接真实缓存/存储（若引入 Redis 等）；缺配置必须失败并英文报错。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#123）
- TDD: `docs/技术设计文档-最佳实践版.md`（#9.2、#12）
- tasks: `docs/tasks.md`（Task 26）

# Execution Plan
1) Task 26.1 - 配额模型（按用户/角色/场景）与审计事件
2) Task 26.2 - 缓存策略与高频模板化（只读）
3) Task 26.3 - 可观测：配额命中率/缓存命中率
4) Task 26.4 - 冒烟：quota_and_cache_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/quota_and_cache_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 26.1 - 配额与拒绝策略：结构化错误 + 审计

```markdown
# Context
你正在执行子任务：26.1 - 配额模型与拒绝策略。
你的目标是实现配额检查并在不足时返回结构化错误与审计记录。

# Critical Rules
- **结构化错误**: `code/message(英文)/details?/retryable/requestId`。
- **RBAC + 审计**: 配额事件必须审计。

# References
- tasks: `docs/tasks.md`（Task 26）

# Execution Plan
1) 定义配额模型与存储。
2) 实现拒绝错误码与 retryable。

# Verification
- 单元：超额 -> 拒绝。

# Output Requirement
- 输出代码与测试。
```

### Task 26.2 - 缓存与模板化：保证 Evidence 可追溯

```markdown
# Context
你正在执行子任务：26.2 - 缓存与模板化。
你的目标是实现缓存与高频模板化查询，并确保输出 evidence 仍可追溯。

# Critical Rules
- **Evidence-First**: 缓存命中也要标注原始来源与时间范围。
- **Read-Only Default**: 不新增写操作。

# References
- tasks: `docs/tasks.md`（Task 26）

# Execution Plan
1) 定义可缓存的查询类型。
2) 设计缓存 key 与失效策略。

# Verification
- 单元：缓存命中/未命中。

# Output Requirement
- 输出代码与测试。
```

### Task 26.3 - 观测：配额/缓存指标与审计字段

```markdown
# Context
你正在执行子任务：26.3 - 观测指标。
你的目标是上报配额命中率、缓存命中率、拒绝次数等指标。

# Critical Rules
- **配置外部化**: exporter 配置外部化。

# References
- tasks: `docs/tasks.md`（Task 26）

# Execution Plan
1) 定义 metrics。
2) 在关键路径上报。

# Verification
- 单元：指标递增。

# Output Requirement
- 输出代码与测试。
```

### Task 26.4 - 冒烟：quota_and_cache_smoke_test.py

```markdown
# Context
你正在执行子任务：26.4 - 配额/缓存冒烟。
你的目标是验证真实服务链路下：配额限制生效、缓存命中生效、结构化错误与审计存在。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 26）

# Execution Plan
1) 发起多次请求触发配额。
2) 发起重复请求触发缓存。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（缓存命中也需 evidence）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
