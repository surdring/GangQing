### Task 45 - （L1/L2）模型推理适配层（llama.cpp 网关/适配器）：超时、并发、配额、观测能力收敛为统一模块（Umbrella）

```markdown
# Context
你正在执行第 45 号任务：模型推理适配层（llama.cpp 网关/适配器）能力收敛。
角色：**技术负责人/架构师**。
目标是规划统一推理适配层的模块边界，把超时、并发/队列、配额/限流、观测字段、错误映射收敛为统一模块，避免散落在业务代码。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **配置外部化（强制）**: timeout/queue/quota 不得硬编码。
- **结构化错误（强制）**: 映射 `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE/SERVICE_UNAVAILABLE/FORBIDDEN` 等，英文 message。
- **可观测与审计（强制）**: 推理调用必须可审计，span/log 含 requestId。
- **真实集成测试（No Skip）**: 冒烟需连真实 llama.cpp。

# References
- PRD: docs/requirements.md（R9.1/R9.2/R15.4）
- TDD: docs/design.md（2.7）
- tasks: docs/tasks.md（任务 45）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 45.1（统一适配器接口：generate/stream/cancel）
2) Task 45.2（能力内聚：timeout/concurrency/quota/observability）
3) Task 45.3（契约校验与错误映射）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/llamacpp_smoke_test.py && backend/scripts/concurrency_cancel_smoke_test.py && backend/scripts/quota_routing_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 45.1 - llama.cpp 统一适配器：超时/并发/配额/观测内聚

```markdown
# Context
你正在执行子任务：45.1 - llama.cpp 统一适配器：超时/并发/配额/观测内聚。

# Critical Rules
- **单一入口**: 业务代码不得直接调用 llama.cpp HTTP。
- **错误映射统一**。

# References
- tasks: docs/tasks.md（45.1）

# Execution Plan
1) 定义 AdapterConfig（Pydantic）。
2) 实现 generate/stream/cancel。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/llamacpp_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（全局约束保留）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
