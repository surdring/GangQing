### Task 16 - 高风险意图/提示词注入防护：策略化拦截 + 审计留痕（Umbrella）

```markdown
# Context
你正在执行第 16 号任务：高风险意图/提示词注入防护：策略化拦截 + 审计留痕。
角色：**技术负责人/架构师**。
目标是规划注入检测（直接/间接）、输出安全校验、越权/写意图拦截策略、证据链/审计记录规则 ID 与原因摘要，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 本 Umbrella 阶段禁止输出任何实现代码。
- **PLANNING ONLY**: 只输出“怎么做/分几步/改哪些文件/契约是什么”。
- **Schema First（强制）**:
  - 后端：对外 I/O、工具参数、审计事件、Evidence 结构必须使用 Pydantic 作为单一事实源。
  - 前端：对外 I/O、SSE 事件、配置必须使用 Zod 作为单一事实源。
- **Guardrail 强制（需求硬约束）**:
  - 越权/敏感查询 => `FORBIDDEN`
  - 写操作倾向/高风险指令/红线 => `GUARDRAIL_BLOCKED`
  - 物理边界/变化率越界 => `GUARDRAIL_BLOCKED` 或降级为“仅展示数据与来源”（见 R17.3）
- **Structured Errors（强制）**: 对外错误与 SSE `error` 事件必须同构，包含：`code` + `message`(英文) + `details?` + `retryable` + `requestId`。
- **Audit & Evidence（强制）**:
  - 触发拦截时：Evidence/审计必须记录 `ruleId` 与原因摘要（禁止敏感细节）。
  - 审计必须可按 `requestId` 检索，字段必须包含 `tenantId/projectId/userId/role/eventType` 等关键上下文。
- **Read-Only Default（强制）**: 不确定是否为写操作时按只读处理；任何写操作仅允许进入 L4 治理链路。
- **RBAC & Data Isolation（强制）**: 所有接口/工具调用必须做 RBAC 与数据域隔离（tenantId/projectId）。
- **Real Integration (No Skip)**: 冒烟/集成测试必须连真实服务；配置缺失或依赖不可用必须失败，不得跳过。

# References
- PRD: docs/requirements.md（R10.1/R10.2/R10.3/R11.1/R15.1/R17.2/R17.3/R5.1）
- TDD: docs/design.md（4.1/4.2/4.4/6/3.6/3.10）
- contracts: docs/contracts/api-and-events-draft.md（Error/Audit/Evidence/SSE Events）
- tasks: docs/tasks.md（任务 16）

# Execution Plan
1) Task 16.1（注入检测：直接/间接 + 输出安全校验）
- Goal:
  - 识别直接注入（用户输入）与间接注入（工具结果/知识库片段）特征。
  - 输出阶段进行敏感信息与系统提示词泄露检测。
- Deliverables:
  - 可配置的规则集与匹配策略（配置外部化 + 启动时校验）。
  - “命中事件”结构定义（用于审计与 Evidence 记录）。

2) Task 16.2（高风险意图识别与策略化拦截：越权/敏感查询/写操作倾向）
- Goal:
  - 将拦截策略落到“意图分类 -> 工具选择 -> 执行前门禁 -> 输出/审计”闭环。
  - 明确 `FORBIDDEN` 与 `GUARDRAIL_BLOCKED` 的触发条件与差异。
- Deliverables:
  - 风险分级与策略表（riskLevel -> action: block/warn/degrade）。
  - SSE 事件输出策略（`warning` vs `error` + `final`）。

3) Task 16.3（Evidence 与审计留痕：ruleId + reasonSummary + requestId 可检索）
- Goal:
  - 统一“拦截证据”结构：ruleId、类别、命中位置（input/output/tool_context）、原因摘要、阈值版本（如适用）。
  - 审计日志脱敏：不得记录敏感原文与系统提示词。
- Deliverables:
  - 审计事件类型枚举与 actionSummary 字段约束（必须可被脱敏策略处理）。
  - Evidence 结构中对 guardrail 命中的最小可追溯字段集合。

4) Task 16.4（测试与契约对齐：单元 + 冒烟 + 契约测试补齐）
- Goal:
  - 对拦截策略、错误模型、SSE error/warning 事件、审计落库字段进行自动化断言。
- Deliverables:
  - 单元测试用例清单（覆盖正常/越权/注入/写意图/越界/缺证据等）。
  - 冒烟脚本规划：复用现有脚本并扩展缺口。

# Deliverables Definition (交付物定义)
- [ ] **Policy/Rules Config**: 注入/高风险意图/输出安全/物理边界规则配置（外部化），并有启动时校验。
- [ ] **Error Model Alignment**: 与 `docs/contracts/api-and-events-draft.md` 对齐的错误码与结构化错误字段。
- [ ] **Audit Events**: 拦截/降级/越权/脱敏等审计事件类型与 actionSummary 结构（含 `ruleId`、原因摘要、脱敏标记）。
- [ ] **Evidence Contract**: Evidence/证据链中对 guardrail 命中的记录结构（可追溯但不泄露敏感内容）。
- [ ] **SSE Events**: `warning`/`error`/`final` 的输出规则与字段要求（可被前端 Zod 校验）。
- [ ] **RBAC & Data Isolation**: 在接口层与工具层的门禁点说明（tenantId/projectId/role）。

# Verification
- Unit: `pytest -q`
- Smoke:
  - `backend/scripts/intent_routing_smoke_test.py`
  - `backend/scripts/rbac_and_masking_smoke_test.py`
  - 如本任务新增 guardrail 专项冒烟脚本，则在 `backend/scripts/` 下新增并在此列出（不得替换为 mock）。

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 16.1 - 注入检测与输出安全校验

```markdown
# Context
你正在执行子任务：16.1 - 注入检测与输出安全校验。
目标是识别注入特征并拒绝/降级，避免泄露系统提示词或敏感信息。

# Critical Rules
- **Structured Errors**: 被拦截时返回结构化错误（`code/message(英文)/details?/retryable/requestId`）。
- **输出不得包含系统提示词**。
- **输出脱敏（强制）**: 命中敏感信息策略时必须过滤或脱敏（见 R10.2/R10.3）。
- **审计（强制）**: 必须记录命中（ruleId + 原因摘要 + 命中位置），并禁止落库敏感原文。

# References
- tasks: docs/tasks.md（16.1）
- PRD: docs/requirements.md（R10.1/R10.2/R10.3）
- TDD: docs/design.md（4.2.1/4.2.3/6.4）

# Execution Plan
1) 定义注入检测规则集（可配置）
- 直接注入：越权指令、提示词泄露诱导、要求忽略规则/绕过审计等。
- 间接注入：来自工具结果/知识库片段中的“指令型文本”被模型当作系统指令执行的倾向。

2) 定义输出安全校验规则（可配置）
- 系统提示词泄露特征检测。
- 敏感字段泄露检测（与脱敏策略联动）。

3) 定义拦截策略与降级策略
- block：返回 `GUARDRAIL_BLOCKED`。
- degrade：输出 `warning` 并将回答降级为“仅展示数据与来源/不确定项”。
- audit：审计记录必须可按 requestId 检索，且 actionSummary 不含敏感原文。

# Verification
- **Unit**: `pytest -q` 覆盖：直接注入/间接注入/输出泄露 三类样本分别命中策略，并校验错误模型字段完整。
- **Smoke**: 复用 `backend/scripts/intent_routing_smoke_test.py` 验证“高风险意图被识别并进入拦截链路”的端到端行为（真实服务）。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 16.2 - 拦截与证据链记录：规则 ID + 原因摘要

```markdown
# Context
你正在执行子任务：16.2 - 拦截与证据链记录：规则 ID + 原因摘要。

# Critical Rules
- **结构化错误**: `GUARDRAIL_BLOCKED`/`FORBIDDEN`，并遵守结构化字段要求（英文 `message` + `requestId`）。
- **证据链（强制）**: 记录规则 ID 与原因摘要（不含敏感细节），并能关联到本次 requestId/sessionId（如有）。
- **SSE（强制）**: 拦截时在 SSE 流中输出可解析的 `error` 或 `warning`，并以 `final` 收敛。

# References
- tasks: docs/tasks.md（16.2）
- contracts: docs/contracts/api-and-events-draft.md（Evidence/Audit）
- PRD: docs/requirements.md（R17.2/R5.1/R11.1）
- TDD: docs/design.md（3.6/3.5.3/6.4）

# Execution Plan
1) 定义“策略化拦截”决策表
- 输入：intent 分类结果、用户 role/capabilities、目标资源（如财务/工艺参数）、是否疑似写操作、是否命中注入/输出安全规则。
- 输出：allow / warn+degrade / block(forbidden) / block(guardrail_blocked)。

2) 统一拦截输出
- 越权/敏感查询：`FORBIDDEN`（并审计 `auth.denied` 或等价事件）。
- 写操作倾向/高风险指令/红线：`GUARDRAIL_BLOCKED`（并审计 guardrail.hit）。

3) 统一 evidence/audit 记录
- evidence: 最小字段集合必须包含 ruleId、category、reasonSummary、hitLocation、timestamp、requestId。
- audit: actionSummary 必须可脱敏，禁止原文落库。

4) SSE 输出规则
- block => `error` + `final`。
- warn+degrade => `warning`（含 code/message）+ 后续 message.delta（降级回答）+ `final`。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/intent_routing_smoke_test.py`（验证拦截链路对话端到端）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 16.3 - 审计与 Evidence 留痕：ruleId + 原因摘要 + 脱敏

```markdown
# Context
你正在执行子任务：16.3 - 审计与 Evidence 留痕：ruleId + 原因摘要 + 脱敏。
你的目标是把 guardrail 的“命中信息”以**可追溯但不泄露**的方式落到审计与 Evidence 中，并确保能按 `requestId` 检索。

# Critical Rules
- **Structured Errors**: `message` 必须为英文；对外错误字段必须完整（`code/message/details?/retryable/requestId`）。
- **Audit（强制）**:
  - 必须记录 `ruleId`、原因摘要、命中位置（input/output/tool_context）与 riskLevel。
  - 禁止将敏感原文（用户输入/工具返回片段/系统提示词）直接写入审计落库。
- **Evidence（强制）**:
  - 证据链必须可追溯：记录规则 ID 与原因摘要，但不得包含敏感细节。
  - 不得伪造 evidenceId 或引用来源。
- **RBAC & Data Isolation（强制）**: 审计查询本身也必须遵守 tenantId/projectId 过滤与 RBAC。

# References
- tasks: docs/tasks.md（16.3）
- PRD: docs/requirements.md（R11.1/R10.2/R17.2）
- TDD: docs/design.md（2.8.1/4.4/6.1/6.4）
- contracts: docs/contracts/api-and-events-draft.md（Audit/Evidence/Error）
  - 权威参考：`docs/contracts/api-and-events-draft.md` 第 4.0（Guardrail Rules Catalog）与第 4.2.1（guardrail.hit actionSummary 最小字段约束）

# Execution Plan
1) 定义 guardrail 命中记录结构（Schema First）
- GuardrailHit: `ruleId/category/riskLevel/hitLocation/reasonSummary/thresholdVersion?/timestamp`。
- 审计 actionSummary：必须可脱敏，并显式标记已脱敏字段（例如 `redactions` 或 `masking` 元信息）。

2) 统一写入点与事件类型
- guardrail.hit：策略拦截命中。
- auth.denied：越权访问被拒绝（与 FORBIDDEN 对齐）。
- data.masked：因权限/敏感策略导致的输出脱敏（如适用）。

3) 审计查询的最小安全要求
- `GET /audit/events` 返回的数据必须默认脱敏（角色策略），并验证不跨 tenantId/projectId。
- 必须可按 `requestId` 精确定位到本次 guardrail 命中事件。

# Verification
- **Unit**: `pytest -q`
  - 断言：guardrail.hit 审计记录包含 ruleId，但不包含敏感原文。
  - 断言：/audit/events 响应字段符合结构化契约（含 requestId）。
- **Smoke**: `backend/scripts/rbac_and_masking_smoke_test.py`
  - 断言：审计查询不会泄露敏感字段，且包含 `data.masked` 事件（如策略命中）。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 16.4 - 测试与契约对齐：单元 + 冒烟 + SSE 可解析错误

```markdown
# Context
你正在执行子任务：16.4 - 测试与契约对齐：单元 + 冒烟 + SSE 可解析错误。
你的目标是为 guardrail 相关能力补齐自动化断言，确保“拦截策略/结构化错误/SSE error/warning/审计落库”可以稳定回归。

# Critical Rules
- **Real Integration (No Skip)**: 冒烟必须连真实服务（FastAPI + Postgres + llama.cpp，如链路涉及）。配置缺失必须失败。
- **No Mock**: 集成/冒烟测试不得使用 mock/stub 绕过真实依赖。
- **Contracts First**: SSE 事件与 ErrorResponse/Audit/Evidence 输出必须通过契约校验（后端 Pydantic / 前端 Zod）。

# References
- tasks: docs/tasks.md（16.4）
- PRD: docs/requirements.md（R6.3/R11.1/R17.2）
- TDD: docs/design.md（3.5.3/6.4/7）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 单元测试用例矩阵（必须覆盖）
- 直接注入样本：应拦截并返回 `GUARDRAIL_BLOCKED`。
- 越权/敏感查询：应返回 `FORBIDDEN`。
- 写操作倾向：应返回 `GUARDRAIL_BLOCKED` 并提示进入审批。
- 审计落库：guardrail.hit/auth.denied 至少 1 条可按 requestId 查询。

2) 冒烟测试链路（真实服务）
- 复用：`backend/scripts/intent_routing_smoke_test.py` 验证高风险意图识别与路由。
- 复用：`backend/scripts/rbac_and_masking_smoke_test.py` 验证审计脱敏与跨域隔离。
- 如需新增脚本：必须包含“启动服务 -> 发请求 -> 校验响应 + 校验审计落库”的端到端断言。

3) SSE 可解析错误事件验证
- 断言 SSE `error` 事件字段完整且 `message` 英文。
- 断言 `error` 后必须有 `final`（不可恢复错误）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**:
  - `backend/scripts/intent_routing_smoke_test.py`
  - `backend/scripts/rbac_and_masking_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（记录 ruleId 与降级）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
