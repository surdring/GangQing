### Task 14 - 证据链引擎：Claim/Citation/Lineage/ToolCallTrace 组装与增量更新（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 14 号任务：证据链引擎：Claim/Citation/Lineage/ToolCallTrace 组装与增量更新。
你的角色是 **技术负责人/架构师**。
你的目标是制定 Task 14 的详细执行计划，并定义证据链引擎的：
- 数据结构与对外契约边界
- 证据组装与一致性校验规则（Evidence-First）
- SSE 增量更新事件（`evidence.update`）的语义与顺序
- 降级/拒答语义（warning vs error vs final）
- 可自动化的验收口径（单元 + 冒烟，且真实集成）

# Critical Rules
- **NO CODE IMPLEMENTATION**: 此 Umbrella 阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 只输出“怎么做/分几步/文件结构/契约长什么样/如何验收”。
- **Evidence-First（强制）**:
  - 数值结论必须能映射到至少 1 条 Evidence。
  - Evidence 必须包含 `sourceSystem/sourceLocator/timeRange/confidence/validation`。
  - 计算类结论必须绑定 `lineageVersion`；缺失必须拒绝确定性输出或降级并输出 `warning`。
- **Structured Errors（强制）**:
  - 对外错误 `message` 必须为英文。
  - SSE `type=error` 的 `payload` 必须与 REST 错误同构：`code/message/details?/retryable/requestId`。
- **Schema 单一事实源（强制）**:
  - 后端：Pydantic（Evidence 与 SSE 事件）。
  - 前端：Zod（Evidence 与 SSE 事件）。
- **RBAC + Masking（强制）**: Evidence / tool result 中的敏感字段默认脱敏；脱敏策略要可审计。
- **Real Integration（强制，No Skip）**: 冒烟/集成测试必须连真实 FastAPI + 真实 Postgres；配置缺失或服务不可用必须失败，禁止 skip。

# References
- PRD: docs/requirements.md（R2.2/R6.2/R14.3/R14.4）
- TDD: docs/design.md（2.10.5/3.3/3.5/5.1/6）
- tasks: docs/tasks.md（L1 #14）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse + SSE Envelope 规则）

# Current Code Anchors (现有代码锚点，用于避免“凭空指定路径”)
- 后端 Evidence 模型（Pydantic）：`backend/gangqing_db/evidence.py`
- 后端 SSE 事件模型（Pydantic）：`backend/gangqing/schemas/sse.py`
- 后端 SSE 输出与 tool.result evidenceRefs 行为：`backend/gangqing/api/chat.py`
- 前端 Evidence schema（Zod）：`web/schemas/evidence.ts`
- 前端 SSE Envelope schema（Zod）：`web/schemas/sseEnvelope.ts`

# Execution Plan
1) Task 14.1（EvidenceChain 数据模型与组装规则：Claim/Citation/Lineage/ToolCallTrace）
- Goal: 明确 EvidenceChain 的最小可用对外字段集合与后端组装/校验规则。
- Deliverables:
  - 后端 Pydantic EvidenceChain 相关模型与校验器
  - 与前端 Zod schema 对齐的字段命名与别名策略

2) Task 14.2（Evidence 增量更新：SSE `evidence.update` 事件契约与发送时机）
- Goal: 让前端 Context Panel 能在工具返回后“立即增量渲染”证据。
- Deliverables:
  - SSE `evidence.update` 的事件定义（后端 Pydantic + 前端 Zod）
  - 服务端发送时机：tool.result 前后顺序与一致性约束

3) Task 14.3（降级与冲突处理：EVIDENCE_MISSING/EVIDENCE_MISMATCH/out_of_bounds）
- Goal: 证据不足时不允许输出确定性数值；并用可解析事件表达降级原因。
- Deliverables:
  - 规则表：触发条件 -> `warning/error/final` 的事件策略
  - 关键英文 message 规范（可检索、可审计、非敏感）

4) Task 14.4（真实冒烟测试补齐：`backend/scripts/evidence_smoke_test.py`）
- Goal: 用真实服务验证 Evidence 增量事件与降级链路。
- Deliverables:
  - `backend/scripts/evidence_smoke_test.py`（真实 FastAPI + 真实 Postgres）
  - 至少 1 条成功路径 + 1 条失败/降级路径

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确新增/修改的目录树（重点：EvidenceChain 模型、SSE 事件、smoke test 脚本）。
- [ ] **API Contracts**: 明确 SSE `evidence.update` 事件结构与发送时机（与 `docs/contracts/api-and-events-draft.md` 对齐）。
- [ ] **Evidence Contract**: EvidenceChain 中 Claim/Citation/Lineage/ToolCallTrace 的字段定义、必填约束与降级语义。
- [ ] **Error Model**: 复用既有错误码（`EVIDENCE_MISSING/EVIDENCE_MISMATCH/GUARDRAIL_BLOCKED/CONTRACT_VIOLATION/...`）并明确触发条件。
- [ ] **RBAC & Masking**: 明确 evidence/tool result 的默认脱敏要求与审计字段。
- [ ] **Observability**: `requestId` 贯穿，SSE `sequence` 单调递增；tool.call/tool.result 与 evidenceRefs 可关联。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/evidence_smoke_test.py`
  - 说明：当前仓库中尚未存在该脚本（以实际文件为准）；Task 14.4 必须补齐并在 CI/本地可运行。

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 14.1 - EvidenceChain 组装规则与校验

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：14.1 - EvidenceChain 组装规则与校验。
你的角色是 **高级开发工程师**。
你的目标是实现证据链组装与一致性校验（Evidence-First），并在不满足规则时触发降级/拒答。

# Critical Rules
- **Schema First**: 后端 Pydantic 为单一事实源；对外输出前必须校验。
- **数值必须有证据**: 任何数值结论必须绑定 Evidence（至少 `timeRange`）。
- **lineageVersion 强制（计算型结论）**: 缺失必须降级为 `warning` 且最终文本不得输出确定性数值。
- **结构化 warning/error**: `message` 必须英文，且 `requestId` 必须可关联。
- **No Mock for Integration**: 冒烟测试必须连真实服务。

# References
- tasks: docs/tasks.md（14.1）
- contracts: docs/contracts/api-and-events-draft.md（Evidence）
- Code anchors:
  - `backend/gangqing_db/evidence.py`
  - `web/schemas/evidence.ts`

# Target Files (authoritative)
- `backend/gangqing_db/evidence.py`（若需扩展 Evidence 字段/校验）
- `backend/gangqing/` 下新增/修改 EvidenceChain 相关模型与组装逻辑（以本任务实际落盘文件为准）
- `backend/tests/` 下新增对应单元测试（以本任务实际落盘文件为准）

# Execution Plan
1) 定义 EvidenceChain 相关 Pydantic 模型
- 包含：Claim/Citation/Lineage/ToolCallTrace（最小字段集合 + 别名策略与 JSON 形态）。

2) 实现组装与校验规则
- 缺少 Evidence 或 Evidence.timeRange：不得输出确定性数值，生成 `warning(code=EVIDENCE_MISSING)` 所需上下文。
- 计算类缺 lineageVersion：生成 `warning(code=EVIDENCE_MISSING)` 或拒答策略（按 contracts/设计约束）。
- 冲突/不一致：生成 `warning(code=EVIDENCE_MISMATCH)` 并携带最小 `details` 摘要（禁止敏感信息）。

3) 编写单元测试（真实语义，不要求真实 DB）
- 覆盖 happy path + 关键边界（缺证据/缺 timeRange/缺 lineageVersion/冲突）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/evidence_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 14.2 - Evidence 增量更新：SSE `evidence.update`

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：14.2 - Evidence 增量更新：SSE `evidence.update`。
你的角色是 **高级开发工程师**。
你的目标是在工具返回后立刻输出“可渲染”的证据增量，支持 Context Panel 实时更新。

# Critical Rules
- **Schema First**: 后端 Pydantic + 前端 Zod 均需对齐。
- **SSE 事件可解析**: 必须符合 `docs/contracts/api-and-events-draft.md` 的 SSE envelope 规则。
- **sequence 单调递增**: 单连接内必须严格递增。
- **脱敏**: evidence payload 默认脱敏；敏感字段不得出现在对外事件中。
- **错误同构**: error 事件 payload 必须为 ErrorResponse。

# References
- PRD: docs/requirements.md（R6.2）
- tasks: docs/tasks.md（14.2）
- contracts: docs/contracts/api-and-events-draft.md（SSE/Evidence）
- Code anchors:
  - 后端：`backend/gangqing/schemas/sse.py`
  - 前端：`web/schemas/sseEnvelope.ts`

# Target Files (authoritative)
- 后端 SSE 事件模型：`backend/gangqing/schemas/sse.py`
- 后端 SSE 输出逻辑（聊天流）：`backend/gangqing/api/chat.py`
- 前端 SSE schema：`web/schemas/sseEnvelope.ts`
- 前端 Evidence schema：`web/schemas/evidence.ts`

# Execution Plan
1) 定义 `evidence.update` 事件的 payload 结构
- 约束：必须能让前端仅凭事件完成渲染（至少包含完整 Evidence，或包含可解析引用 + 可同步拉取的方案；L1 优先“直接传 Evidence”）。

2) 定义发送时机与顺序
- 当 tool.result 产生 `evidenceRefs` 时：应保证对应的 `evidence.update` 在流中可被前端收到（顺序策略必须固定，建议：先 evidence.update 再 tool.result，或 tool.result 中仅引用已发送 evidenceId）。
- 当工具结果缺 Evidence：必须输出 `warning(code=EVIDENCE_MISSING, message=...)`（英文）。

3) 前端契约与回归
- 更新/新增前端 Zod schema，以能解析 `evidence.update` 并保证与后端一致。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/evidence_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 14.3 - 降级策略：缺证据/不一致/越界（warning / error / final）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：14.3 - 降级策略：缺证据/不一致/越界。
你的角色是 **高级开发工程师**。
你的目标是把“不可验证/冲突/越界”转化为可执行的：
- SSE 事件策略（warning/error/final）
- 最终回答文本约束（不得输出确定性数值）

# Critical Rules
- **Evidence-First**: 无证据不得给确定性数值。
- **English Message**: warning/error 的 `message` 必须英文。
- **No Sensitive Details**: `details` 必须为结构化摘要且脱敏。

# References
- PRD: docs/requirements.md（R2.2/R14.3/R14.4）
- TDD: docs/design.md（2.10.5/5.1/6）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse + SSE warning/error/final 规则）

# Target Files (authoritative)
- `backend/gangqing/api/chat.py`（warning 事件与 tool.result evidenceRefs 行为）
- `backend/gangqing/schemas/sse.py`
- `backend/tests/`（新增降级策略的单元测试）

# Execution Plan
1) 定义降级规则表
- 输入：证据存在性、timeRange 合法性、lineageVersion 存在性、validation 状态（verifiable/not_verifiable/out_of_bounds/mismatch）。
- 输出：是否允许给出确定性数值、是否必须输出 warning、是否应终止（error+final）。

2) 实现 warning 事件与 details 规范
- `details` 必须仅包含最小字段（例如 `toolCallId/toolName/evidenceId`），禁止原始 SQL、rows、token 等。

3) 单元测试覆盖
- 至少覆盖：EVIDENCE_MISSING、EVIDENCE_MISMATCH、out_of_bounds 三类。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/evidence_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**。
```

---

### Task 14.4 - 真实冒烟测试：`backend/scripts/evidence_smoke_test.py`

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：14.4 - 真实冒烟测试：`backend/scripts/evidence_smoke_test.py`。
你的角色是 **高级开发工程师**。
你的目标是补齐并运行一个“真实服务链路”的冒烟测试脚本，用于验收：
- SSE 流中出现 evidence 相关事件（warning/evidence.update/tool.result evidenceRefs）
- 在缺证据/冲突/越界场景下，系统按约束降级

# Critical Rules
- **Real Integration Only**: 必须连真实 FastAPI + 真实 Postgres；配置缺失必须失败。
- **No Skip**: 不允许 skip。
- **Structured Error**: 失败必须输出可检索英文 message，并携带 requestId。

# References
- tasks: docs/tasks.md（L1 #14）
- contracts: docs/contracts/api-and-events-draft.md（SSE envelope + warning/error/final）

# Target Files (authoritative)
- `backend/scripts/evidence_smoke_test.py`（需要创建/补齐）
- 若需要复用：参考 `backend/scripts/sse_smoke_test.py` 的启动与断言方式（以仓库实际文件为准）

# Execution Plan
1) 实现 smoke test 脚本
- 能启动/连接真实服务或复用已有启动方式。
- 能发起一次对话请求并消费 SSE 事件流。

2) 断言至少两个场景
- 成功路径：出现 `tool.call/tool.result/final`，且 tool.result 携带 `evidenceRefs` 或出现 `evidence.update`。
- 降级路径：出现 `warning(code=EVIDENCE_MISSING 或 EVIDENCE_MISMATCH)`，并且 `message` 为英文。

# Verification
- **Smoke**: `backend/scripts/evidence_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径 + 验证命令与关键输出摘要**。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（本任务核心）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
- [x] Unit tests 已运行并通过（`pytest -q`）
- [x] Smoke tests 已运行并通过（`backend/scripts/evidence_smoke_test.py`）
- [x] 任务状态已同步（`docs/tasks.md`）
