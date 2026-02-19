### Task 51 - （L2）Token 预算与配额增强：缓存与高频问题模板化（成本治理）（Umbrella）

```markdown
# Context
你正在执行第 51 号任务：Token 预算与配额增强：缓存与高频问题模板化（成本治理）。
角色：**技术负责人/架构师**。
目标是规划缓存策略（命中可审计）、高频问题模板化、配额计数与成本治理指标，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **配置外部化（强制）**: 缓存 TTL、开关、模板列表不得硬编码。
- **可审计（强制）**: 缓存命中/未命中必须写审计并绑定 `requestId`。
- **结构化错误**: 超额/过载返回结构化错误，英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R15.4）
- TDD: docs/design.md（2.7.2）
- tasks: docs/tasks.md（任务 51）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 51.1（缓存：key 设计、TTL、审计字段）
2) Task 51.2（高频问题模板化：路由与 Evidence）
3) Task 51.3（观测指标：命中率/节省 token）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/quota_and_cache_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 51.1 - 缓存与模板化：可审计命中 + 降级建议

```markdown
# Context
你正在执行子任务：51.1 - 缓存与模板化：可审计命中 + 降级建议。

# Critical Rules
- **审计**: `X-Cache: HIT|MISS` 也要进入审计摘要。

# References
- tasks: docs/tasks.md（51.1）

# Execution Plan
1) 定义缓存配置与 key。
2) 实现模板化路由。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/quota_and_cache_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（模板化/缓存结果仍需 evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
