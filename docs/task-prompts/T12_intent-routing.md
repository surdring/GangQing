### Task 12 - 实现意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 12 号任务：实现意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）。
你的角色是 **技术负责人/架构师**。
你的目标是制定任务 12 的详细执行计划，并统一：意图输出契约、置信度与澄清策略、只读默认门禁、高风险拦截与审计口径。

# Critical Rules (核心约束)
- **NO CODE IMPLEMENTATION**: 在此阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 你的输出应聚焦于“怎么做/分几步/修改哪些文件/契约长什么样/如何验收”。
- **Schema First**:
  - 后端：意图识别输出、路由决策输出、对外错误模型使用 Pydantic 作为单一事实源。
  - 前端：如涉及对外 I/O 或 SSE 事件消费，必须与 `web/schemas/*` 的 Zod schema 对齐。
- **Read-Only Default (强制)**: 任何写操作倾向（ACTION_*）不得直接执行；L1 阶段必须拦截并返回结构化错误或引导进入 L4 草案/审批流程（仅输出草案，不执行）。
- **Ambiguity -> Clarify (强制)**: 意图不明确时必须发起澄清问题，不得猜测执行。
- **Structured Errors (强制)**: 对外错误必须结构化：`code` + `message`(英文) + `requestId` + `retryable` + `details?`。
- **RBAC & Audit (强制)**: 意图识别结果、路由决策、工具调用（如有）必须写入审计；日志/审计字段至少包含 `requestId`，可用时包含 `sessionId/stepId/toolName`。
- **Real Integration (No Skip)**: 冒烟/集成测试必须连接真实 FastAPI + 真实 Postgres + 真实 llama.cpp；配置缺失或依赖不可用必须失败，不得 skip。

# References
- PRD: docs/requirements.md（R15.1/R5.1）
- TDD: docs/design.md（2.4/3.9/6.1/6.4）
- tasks: docs/tasks.md（任务 12）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan (执行蓝图)

1) Task 12.1（意图模型与输出契约）
- Goal: 定义“意图识别”的稳定输出契约：意图类别、置信度、澄清问题（如需）与可审计字段。
- Deliverables: 后端 Pydantic 模型（Intent/IntentResult/ClarificationQuestion 等）；意图识别模块的输入输出边界。

2) Task 12.2（策略路由：工具白名单 + 写意图拦截/只读默认）
- Goal: 基于“角色 + 意图 + 数据域”收敛可用工具集合与策略；对 ACTION_* 意图进行门禁拦截并输出结构化错误/草案入口。
- Deliverables: 路由决策模型（RouteDecision）；策略路由实现与审计字段；错误码映射口径。

3) Task 12.3（测试与验收：单元 + 冒烟 + 契约对齐）
- Goal: 用自动化测试固化：澄清策略、写意图拦截、错误模型字段完整性、以及与现有契约的一致性。
- Deliverables: 单元测试用例；补齐 `backend/scripts/intent_routing_smoke_test.py`（当前仓库缺失，但 `docs/tasks.md` 明确要求）。

# Deliverables Definition (交付物定义)
- [ ] **Target Files**: 明确将修改/新增哪些文件（backend 代码、tests、scripts）。
- [ ] **API Contracts**: 意图结果与路由决策的对外表示（如经 SSE/REST 输出）必须与 `docs/contracts/api-and-events-draft.md` 对齐。
- [ ] **Error Model**: 明确本任务会触达的错误码（至少 `GUARDRAIL_BLOCKED/FORBIDDEN/VALIDATION_ERROR/CONTRACT_VIOLATION/INTERNAL_ERROR`）与英文 `message` 要求。
- [ ] **Observability & Audit**: 明确审计事件类型与必填字段（`requestId` 等）。

# Verification Plan (整体验收)
- Unit: `pytest -q`
- Smoke: `backend/scripts/intent_routing_smoke_test.py`

# Output Requirement
请输出一份详细的 **Markdown 执行计划**，包含上述所有章节。
**不要写代码**，请确认你理解了只读默认、澄清策略、结构化错误与审计要求后再输出计划。

---

### Task 12.1 - 意图识别输出：类别 + 置信度 + 澄清

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：12.1 - 意图识别输出：类别 + 置信度 + 澄清。
你的角色是 **高级开发工程师**。
你的目标是实现意图识别模块，产出结构化结果并满足审计与可观测要求。

# Critical Rules (核心约束)
- **Schema First**: 意图识别输出必须由 Pydantic 模型定义并校验。
- **Ambiguity -> Clarify**: 意图不明确必须输出澄清问题结构，不得猜测执行。
- **Structured Errors**: 对外错误 `message` 必须为英文。
- **RBAC & Audit**: 记录意图识别结果与置信度（脱敏后）并绑定 `requestId`。

# References
- PRD: docs/requirements.md（R15.1）
- TDD: docs/design.md（2.4.1/3.9）
- tasks: docs/tasks.md（12）

# Target Files
- backend/gangqing/agent/（意图识别模块，如已存在则在现有文件内扩展）
- backend/gangqing/api/ 或 backend/gangqing/app/（如意图输出需要出现在对话链路中）
- backend/tests/（新增单元测试）

# Execution Plan (具体步骤)
1) 定义 Pydantic 模型
- Action: 定义 Intent 枚举/类型、IntentResult（含 `intent`/`confidence`/`should_clarify`/`clarification_question?`/`reasoning_summary?` 等）。

2) 实现意图识别与澄清问题生成
- Action: 对照 `QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE` 设计分类逻辑与阈值策略；当证据不足或表述模糊时生成澄清问题。

3) 审计与可观测字段贯穿
- Action: 确保 `requestId` 可拿到并写入日志/审计记录；不记录敏感原文（按现有脱敏策略）。

# Verification (验收标准)
- **Unit**: `pytest -q`
  - 覆盖：模糊输入 -> `should_clarify=true` 且提供澄清问题。
  - 覆盖：明确查询/分析 -> 返回对应意图与置信度。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。

---

### Task 12.2 - 策略路由：写意图拦截与只读默认

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：12.2 - 策略路由：写意图拦截与只读默认。
你的角色是 **高级开发工程师**。
你的目标是将意图识别结果转为“可用工具集合/执行策略”，并落实只读默认门禁。

# Critical Rules (核心约束)
- **Read-Only Default**: ACTION_* 意图不得执行写操作；L1 必须拦截。
- **RBAC**: 任何工具调用都必须 capability 校验。
- **Structured Errors**: 写意图拦截使用稳定错误码（优先 `GUARDRAIL_BLOCKED`，越权用 `FORBIDDEN`），英文 `message`。
- **Audit**: 记录路由决策（允许/拦截原因/工具白名单摘要）并绑定 `requestId`。

# References
- PRD: docs/requirements.md（R5.1/R15.1）
- TDD: docs/design.md（2.4.2/3.6.1/3.9/6.4）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files
- backend/gangqing/agent/（策略路由模块）
- backend/gangqing/tools/（如需要读取工具注册表/能力矩阵）
- backend/tests/（新增单元测试）

# Execution Plan (具体步骤)
1) 定义路由决策模型
- Action: 定义 RouteDecision（允许的工具集合摘要、是否需要拦截、拦截原因、面向用户的下一步提示）。

2) 实现 intent -> policy
- Action: 按“角色 + 意图 + 数据域”裁剪工具集合；对 ACTION_EXECUTE/ACTION_PREPARE 走门禁策略（L1 拦截/仅草案）。

3) 错误码与对外输出
- Action: 与契约对齐结构化错误模型字段，确保 SSE/REST 输出可被前端解析。

# Verification (验收标准)
- **Unit**: `pytest -q`
  - 覆盖：ACTION_EXECUTE -> 返回 `GUARDRAIL_BLOCKED`（或按 contracts/实现约定）且 `message` 为英文。
  - 覆盖：越权敏感工具 -> `FORBIDDEN`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。

---

### Task 12.3 - 自动化验收：单元测试 + 冒烟测试脚本（真实服务）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：12.3 - 自动化验收：单元测试 + 冒烟测试脚本（真实服务）。
你的角色是 **高级开发工程师**。
你的目标是补齐自动化验证，确保任务 12 可被 CI/人工一键复现验收。

# Critical Rules (核心约束)
- **Real Integration (No Skip)**: 冒烟测试必须连接真实服务（FastAPI/Postgres/llama.cpp）。
- **Config Missing -> Fail**: 缺少必要配置必须失败并给出清晰英文错误。
- **Structured Errors**: 失败路径必须断言结构化错误字段完整性。

# References
- tasks: docs/tasks.md（任务 12）
- TDD: docs/design.md（7.1/7.2/7.4/7.5）

# Target Files
- backend/tests/（补齐单元测试）
- backend/scripts/intent_routing_smoke_test.py（新增：当前仓库缺失，但任务清单要求）

# Execution Plan (具体步骤)
1) 单元测试
- Action: 增加覆盖：
  - 模糊输入 -> 需要澄清
  - ACTION_EXECUTE -> 拦截
  - 错误模型字段完整性（`code/message/requestId/retryable`）

2) 冒烟测试脚本（真实服务）
- Action: 新增 `backend/scripts/intent_routing_smoke_test.py`，遵循现有 scripts 的风格：启动/探测服务、发起真实请求、断言关键路径与失败路径。

# Verification (验收标准)
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/intent_routing_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。

---

### Checklist（自检）
- [x] 是否包含 `# Critical Rules` 且 Umbrella 阶段明确禁止写代码？
- [x] 是否列出了每个子任务的 **Target Files**？
- [x] 是否明确强调 **意图不明确必须澄清**？
- [x] 是否明确强调 **只读默认** 与 ACTION_* 拦截策略？
- [x] 是否对齐 **结构化错误模型** 且 `message` 为英文？
- [x] 是否包含 **RBAC/审计/requestId** 贯穿要求？
- [x] 是否包含 **真实集成测试不可 skip** 的要求？
- [x] 是否将 `backend/scripts/intent_routing_smoke_test.py` 纳入 12.3 交付物？

# 权威参考文档 / Constraints

- `docs/specs/plans/T12_intent-routing-e61b7e.md`
