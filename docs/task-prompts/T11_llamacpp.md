### Task 11 - 接入 llama.cpp 推理服务（超时/错误码映射/健康检查联动）（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 11 号任务：接入 llama.cpp 推理服务（超时/错误码映射/健康检查联动）。
你的角色是 **技术负责人/架构师**。
你的目标是制定任务 11 的详细执行计划，并定义 llama.cpp 适配层对外接口、配置与校验、超时/不可用错误映射、健康检查联动（unhealthy/degraded），以及真实集成测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 在此阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 你的输出聚焦于“怎么做”、“分几步”、“文件结构如何”、“接口长什么样（契约/Schema）”。
- **配置外部化（强制）**: llama.cpp base URL、超时、并发/队列相关配置不得硬编码；必须通过统一配置加载机制加载并校验。
- **结构化错误（强制）**: 对外错误必须结构化（`code`/`message`/`requestId`/`retryable`/`details?`），其中 `message` 必须为英文；上游不可用/超时映射 `UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT`。
- **可观测与审计（强制）**: 推理调用必须产出结构化日志与审计事件，至少包含 `requestId`、`toolName`（或等价字段）、耗时与状态；日志与审计中不得泄露密钥。
- **Schema First（强制）**: 后端对外 I/O 与配置使用 Pydantic（或项目统一配置 schema）作为单一事实源；输出必须可被 schema 校验。
- **真实集成测试（No Skip）（强制）**: 冒烟/集成测试必须连接真实 llama.cpp；缺少配置或依赖不可用必须失败，不得跳过。

# References
- PRD: docs/requirements.md（R9.1/R12.3）
- TDD: docs/design.md（2.7.1/2.7.2/2.9）
- tasks: docs/tasks.md（任务 11）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 11.1（llama.cpp 适配层接口与配置）
- Goal: 定义 llama.cpp 适配器的最小对外接口（输入/输出/错误），并完成配置项清单与校验口径。
- Deliverables: 适配器接口契约、配置 schema、需要改动/新增的文件清单。

2) Task 11.2（超时/不可用错误映射与重试/降级策略）
- Goal: 明确网络错误/HTTP 错误/超时/输出不可解析等场景的稳定错误码映射与 `retryable` 判定规则。
- Dependencies: 依赖 11.1 的接口契约与配置 schema。

3) Task 11.3（健康检查联动：unhealthy/degraded）
- Goal: 定义健康检查对 llama.cpp 的探测方式与状态映射（依赖不可用 vs 系统降级）。
- Dependencies: 依赖 11.1 的配置 schema 与 11.2 的错误映射规则。

# Deliverables Definition (交付物定义)
- [ ] **Directory / Target Files**: 明确每个子任务将新增/修改的文件路径（以仓库实际结构为准）。
- [ ] **Environment Variables**: 明确所需 ENV、默认值策略、以及校验 schema（缺失必须快速失败，英文错误消息）。
- [ ] **Adapter Contract**: llama.cpp 适配器的输入输出（请求体/响应体）与错误模型（AppError）结构。
- [ ] **Error Mapping**: `UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT/CONTRACT_VIOLATION/SERVICE_UNAVAILABLE` 等错误码覆盖与 `retryable` 判定。
- [ ] **Healthcheck Contract**: 健康检查返回字段、unhealthy/degraded 判定、以及对外暴露的非敏感摘要。
- [ ] **Observability & Audit**: `requestId` 贯穿与审计事件字段（不得包含密钥）。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/llamacpp_smoke_test.py`

# Verification Plan (整体验收)
- 自动化断言：
  - llama.cpp 可用：推理调用成功，且审计记录包含 `requestId`、耗时与状态。
  - llama.cpp 不可用或超时：返回结构化错误（英文 `message`），错误码映射为 `UPSTREAM_UNAVAILABLE` 或 `UPSTREAM_TIMEOUT`。
  - 健康检查：能正确区分 `unhealthy` 与 `degraded`（按设计口径）。

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 11.1 - llama.cpp 适配层：配置化接入与错误映射

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：11.1 - llama.cpp 适配层：配置化接入与错误映射。
你的角色是 **高级开发工程师**。
你的目标是实现对 llama.cpp 的最小调用封装（HTTP 客户端 + 超时），并确保结构化错误、审计字段与配置校验对齐。

# Critical Rules
- **配置外部化（强制）**: base URL/timeout/并发与队列相关配置不得硬编码；必须校验。
- **Structured Errors（强制）**: 对外错误必须结构化（`code`/`message`/`requestId`/`retryable`/`details?`），`message` 必须为英文。
- **审计（强制）**: 记录调用耗时与结果摘要（脱敏），包含 `requestId`；不得记录密钥与原始 Prompt。
- **No Mock for Integration（强制）**: 集成/冒烟测试必须连接真实 llama.cpp。

# References
- tasks: docs/tasks.md（任务 11）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files (to be confirmed)
- backend/gangqing/app/config/llamacpp.py（或等价位置：llama.cpp 配置加载与校验）
- backend/gangqing/app/llm/llamacpp_client.py（或等价位置：HTTP 客户端适配器）
- backend/gangqing/app/errors.py（或等价位置：AppError/错误码映射，如需）
- backend/scripts/llamacpp_smoke_test.py（冒烟测试，若尚不存在则创建）

# Environment Variables
- `GANGQING_LLAMACPP_BASE_URL`
- `GANGQING_LLAMACPP_TIMEOUT_SECONDS`
- `GANGQING_LLAMACPP_MAX_CONCURRENCY`（如本任务范围包含并发限制）

# Execution Plan
1) 实现 HTTP 客户端封装与超时。
2) 统一错误映射。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/llamacpp_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 11.2 - 超时/不可用错误映射与重试/降级策略

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：11.2 - 超时/不可用错误映射与重试/降级策略。
你的角色是 **高级开发工程师**。
你的目标是把 llama.cpp 调用侧的错误分类、错误码映射、`retryable` 判定、以及必要的重试/降级策略落到代码与测试里，并与对外契约保持一致。

# Critical Rules
- **Structured Errors（强制）**: 错误响应必须结构化且 `message` 为英文。
- **Contract Alignment（强制）**: 错误码必须与 `docs/contracts/api-and-events-draft.md` 对齐；不得新增未登记错误码。
- **No Silent Fallback（强制）**: 不得吞错；任何降级必须对外可观测（warning/progress/error 或日志/审计事件）。

# References
- PRD: docs/requirements.md（R9.1/R9.3）
- TDD: docs/design.md（6.1/6.2/6.4）
- tasks: docs/tasks.md（任务 11）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files (to be confirmed)
- backend/gangqing/app/llm/llamacpp_client.py（或等价位置：错误分类与映射）
- backend/gangqing/app/errors.py（或等价位置：错误模型/错误码枚举）
- backend/scripts/llamacpp_smoke_test.py（补充失败路径断言：超时/不可用）

# Execution Plan
1) 明确错误分类：连接失败、DNS/连接拒绝、HTTP 5xx、超时、响应不可解析（契约违反）。
2) 映射稳定错误码：`UPSTREAM_UNAVAILABLE`、`UPSTREAM_TIMEOUT`、`CONTRACT_VIOLATION` 等，并输出 `retryable`。
3) 若实现重试：明确重试次数上限、退避策略与日志/审计字段；并写测试断言。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/llamacpp_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Task 11.3 - 健康检查联动：unhealthy/degraded 判定

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：11.3 - 健康检查联动：unhealthy/degraded 判定。
你的角色是 **高级开发工程师**。
你的目标是把 llama.cpp 状态纳入健康检查，并区分依赖不可用与系统降级态（并确保对外信息不包含敏感数据）。

# Critical Rules
- **结构化错误**: 健康检查失败也要提供可读英文信息（不泄露密钥）。
- **配置校验**: 关键配置缺失必须快速失败。

# References
- PRD: docs/requirements.md（R12.3）
- tasks: docs/tasks.md（任务 11）
- TDD: docs/design.md（2.9）

# Execution Plan
1) 在健康检查中探测 llama.cpp。
2) 将结果映射为 unhealthy/degraded。

# Verification
- **Smoke**: 通过 `backend/scripts/llamacpp_smoke_test.py` 与健康检查脚本验证。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [ ] 是否所有错误 `message` 都是英文？
- [ ] 是否包含结构化错误模型字段（`code/message/requestId/retryable/details?`）？
- [ ] 是否明确了配置外部化与配置校验策略（缺失即失败）？
- [ ] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [ ] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [ ] 是否包含真实集成测试且不可 skip 的要求？
