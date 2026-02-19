### Task 10 - 工具超时与重试策略（可观测、可审计、可降级）（Umbrella）

```markdown
# Context
你正在执行第 10 号任务：工具超时与重试策略（可观测、可审计、可降级）。
角色：**技术负责人/架构师**。
目标是定义统一的超时、重试（最多 3 次）、退避策略、错误码映射与 SSE 流内可见的降级/重试事件。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **结构化错误（强制）**:
  - 超时 => `UPSTREAM_TIMEOUT`（通常 `retryable=true`）
  - 上游不可用 => `UPSTREAM_UNAVAILABLE`
  - `message` 英文。
- **可观测与审计（强制）**: 重试次数、最终结果、耗时必须写审计并带 `requestId/toolName/stepId`。
- **SSE 流式输出（强制）**: 重试/降级过程必须通过 `warning`/`progress` 或等价事件对用户可见。
- **配置外部化（强制）**: timeout、max_retries、退避参数必须外部化并校验。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R8.3）
- TDD: docs/design.md（6.3/6.4）
- tasks: docs/tasks.md（任务 10）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 10.1（统一超时边界与错误码）
2) Task 10.2（重试策略：次数/退避/幂等要求）
3) Task 10.3（SSE 事件：重试可视化 + 审计落库）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/tool_timeout_retry_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 10.1 - 工具超时与错误映射（`UPSTREAM_TIMEOUT`/`UPSTREAM_UNAVAILABLE`）

```markdown
# Context
你正在执行子任务：10.1 - 工具超时与错误映射。
目标是为所有工具调用建立一致的超时与错误映射规则，并保证结构化错误对齐 contracts。

# Critical Rules
- **结构化错误**: 超时/不可用必须映射到稳定错误码。
- **message 英文**。

# References
- tasks: docs/tasks.md（10.1）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse）

# Execution Plan
1) 在工具调用包装层统一设置 timeout。
2) 捕获超时/连接失败并映射错误码与 `retryable`。

# Verification
- **Unit**: `pytest -q` 覆盖：超时映射与 `retryable`。
- **Smoke**: `backend/scripts/tool_timeout_retry_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 10.2 - 重试与降级：次数、退避、审计与 SSE 可视化

```markdown
# Context
你正在执行子任务：10.2 - 重试与降级：次数、退避、审计与 SSE 可视化。

# Critical Rules
- **重试最多 3 次**（按任务约束）。
- **审计**: 记录每次重试与最终结果。
- **SSE**: 重试过程必须输出可解析事件。

# References
- tasks: docs/tasks.md（10.2）
- TDD: docs/design.md（6.4）

# Execution Plan
1) 实现指数退避（参数可配置）。
2) 在 SSE 中输出重试阶段 `progress/warning`。
3) 若最终失败，输出结构化 `error` + `final`。

# Verification
- **Unit**: `pytest -q` 覆盖：重试次数上限与事件输出顺序。
- **Smoke**: `backend/scripts/tool_timeout_retry_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（重试过程工具证据仍需保留）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
