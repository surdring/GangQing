### Task 42 - 性能与可靠性体系：P95 目标、降级策略、压测与容量基线（Umbrella）

```markdown
# Context
你正在执行第 42 号任务：性能与可靠性体系。
角色：**技术负责人/架构师**。
目标是规划性能指标口径（P50/P95/P99）、降级策略、过载错误码（`SERVICE_UNAVAILABLE`）、压测方法与容量基线报告产物。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **结构化错误（强制）**: 过载返回 `SERVICE_UNAVAILABLE`，英文 message。
- **可观测性（强制）**: 性能数据与 requestId/路由原因/工具耗时关联（去敏）。
- **配置外部化（强制）**: 降级阈值、超时、并发不得硬编码。
- **真实集成测试（No Skip）**: 性能冒烟必须针对真实服务；配置缺失必须失败。

# References
- PRD: docs/requirements.md（R14.1/R14.2）
- TDD: docs/design.md（2.8.2）
- tasks: docs/tasks.md（任务 42）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 42.1（指标与SLO：P95目标与错误预算）
2) Task 42.2（降级策略：缓存/小模型/模板化/仅展示数据与来源）
3) Task 42.3（压测与容量基线报告）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/performance_baseline_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 42.1 - 过载与降级：返回 `SERVICE_UNAVAILABLE` + 可执行建议

```markdown
# Context
你正在执行子任务：42.1 - 过载与降级：返回 `SERVICE_UNAVAILABLE` + 可执行建议。

# Critical Rules
- **结构化错误**。
- **message 英文**。

# References
- tasks: docs/tasks.md（42.1）

# Execution Plan
1) 定义过载判定与降级路径。
2) 过载时返回结构化错误并给出降级建议。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/performance_baseline_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（降级仍需 evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
