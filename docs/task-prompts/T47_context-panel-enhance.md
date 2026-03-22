### Task 47 - （L1）前端 Context Panel 强化：“证据缺失/不可验证/降级态”表达与可追溯展开（Umbrella）

```markdown
# Context
你正在执行第 47 号任务：前端 Context Panel 强化。
角色：**技术负责人/架构师**。
目标是规划 Context Panel 的状态模型（完整/缺失/冲突/降级）、可追溯展开交互、与后端 `warning/evidence.update/error/final` 事件对齐，并把“Evidence-First + 不可验证降级”落到**可执行的 UI 行为与验收**。

# Goals
- 明确定义 Context Panel 的**输入契约**（仅允许渲染通过 Zod 校验的 SSE 事件 payload / REST 响应）。
- 定义 Evidence 的**状态模型**与 UI 表达：
  - `verifiable`（可验证）
  - `not_verifiable`（不可验证）
  - `out_of_bounds`（越界/触发 guardrail）
  - `mismatch`（证据冲突/不一致）
- 定义 Evidence 的**增量合并策略**与“不允许回退/不允许篡改来源”的规则，保证流式更新不闪烁、不丢字段。
- 定义“可追溯展开”的信息架构：`sourceSystem/sourceLocator/timeRange/lineageVersion/toolCallId/dataQualityScore/redactions`。
- 定义 `warning` 与 Evidence 状态的映射，使 UI 能明确表达“为什么降级/不可验证”。

# Non-Goals
- 不实现任何 UI 代码/Hook 代码/后端代码（本提示词只产出执行蓝图）。
- 不重新设计全局布局与交互框架（只聚焦右侧 Context Panel 与其数据模型/状态）。
- 不引入新的对外协议字段；如需扩展，必须先更新 `docs/contracts/api-and-events-draft.md` 并同步任务提示词引用。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 只展示可追溯证据；不可验证必须显式 UI 表达。
- **Schema 单一事实源**: 前端对外数据结构用 Zod。
- **TypeScript Strict**。
- **真实集成测试（No Skip）**。
- **SSE 扁平 Envelope（强制）**：事件必须是扁平字段（`type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`），不得嵌套 `envelope` 对象。
- **错误 message 英文（强制）**：`warning/error` 的 `payload.message` 必须英文；UI 展示文案可中文。

# References
- PRD: docs/requirements.md（R6.2/R14.4/R13.3/R10.2）
- TDD: docs/design.md（2.10.2/3.5/5.1/6）
- Contracts: docs/contracts/api-and-events-draft.md（2/3/6：ErrorResponse、SSE 扁平 Envelope、Evidence 字段与降级规则）
- EvidenceViewModel（状态机/渲染规则/合并一致性校验）：docs/specs/context-panel-evidence-viewmodel.md
- Frontend Zod: web/schemas/evidence.ts, web/schemas/errorResponse.ts, web/schemas/sseEnvelope.ts
- Frontend SSE Hook: web/hooks/useChatSseStream.ts（契约校验与事件对齐行为）
- tasks: docs/tasks.md（任务 47）

# Execution Plan
1) Task 47.1（Evidence UI 状态：缺失/冲突/降级）
2) Task 47.2（可追溯展开：sourceLocator/timeRange/lineageVersion 等）

# Inputs & Contracts (must follow)
## Evidence (Zod single source of truth)
- Evidence 对象以 `web/schemas/evidence.ts` 为准，字段名必须一致：
  - `evidenceId`（必填）
  - `sourceSystem`（必填）
  - `sourceLocator`（必填，object；用于定位来源，禁止包含密钥/凭证/敏感原值）
  - `timeRange.start/end`（必填，ISO string）
  - `toolCallId?`（可选）
  - `lineageVersion?`（可选；涉及计算类结论建议展示/强调）
  - `dataQualityScore?`（可选，0..1）
  - `confidence`（Low/Medium/High）
  - `validation`（`verifiable|not_verifiable|out_of_bounds|mismatch`）
  - `redactions?`（可选；仅说明脱敏发生原因/策略 ID/字段名，不得包含原值）

## ErrorResponse / warning payload
- ErrorResponse schema 以 `web/schemas/errorResponse.ts` 为准：`code/message/details?/retryable/requestId`。
- `warning.payload` 必须包含：`code/message(details?)`，其中 `message` 必须英文。

## SSE event envelope (flat)
- SSE 事件 envelope 必须为扁平结构（Contracts 强制）：
  - `type` / `timestamp` / `requestId` / `tenantId` / `projectId` / `sessionId?` / `sequence` / `payload`
- Context Panel 必须处理的最小事件集合：
  - `evidence.update`（`payload.mode` + `payload.evidences`）
  - `warning`
  - `error`
  - `final`

# Verification
- Unit: `npm -C web test`
- Smoke:
  - `npm -C web run build`
  - `.venv/bin/python backend/scripts/web_sse_e2e_smoke_test.py`

# 联调检查清单（Context Panel）
- [ ] Context Panel 的输入模型是否来源于“已校验”的数据（Zod 校验通过的 SSE 事件 payload 或 REST 响应），禁止直接渲染未校验的 `unknown`？
- [ ] 是否与后端事件对齐并能正确处理：
  - [ ] `evidence.update`（证据增量更新，可能多次出现）
  - [ ] `warning`（证据不足/不可验证/降级原因）
  - [ ] `error`（结构化错误，payload 为 ErrorResponse；包含 `requestId`）
  - [ ] `final`（结束后证据面板状态稳定，不再闪烁/回退；`final` 后不得再接受任何事件更新 UI）
- [ ] evidence 增量合并策略是否明确（不会因为后续 update 缺字段导致“覆盖丢失”）？
- [ ] evidence 更新“不允许回退/篡改来源”规则是否明确并可验收：
  - [ ] 同一 `evidenceId` 的 `sourceSystem/sourceLocator/timeRange` 不允许被后续 update 改写为不一致值（检测到不一致 => 视为 `mismatch` 并输出降级态）
  - [ ] `lineageVersion` 不允许从有值变为缺失（缺失只能保持原值）
  - [ ] `dataQualityScore` 不允许从有值变为缺失（缺失只能保持原值）
- [ ] 是否只展示“可追溯证据”：
  - [ ] Evidence 必须包含 `sourceSystem/sourceLocator/timeRange`（字段名以 `web/schemas/evidence.ts` 为准）
  - [ ] `sourceLocator` 是否“可定位但不泄露”（禁止 token/secret/password/cookie 等；禁止敏感原值）
  - [ ] 涉及计算的结论是否展示 `lineageVersion`（字段名以 Zod 为准）
- [ ] 当 evidence 不完整/缺失时，是否明确显示降级态（例如：缺证据/不可验证/冲突/越界），并避免渲染出“看似可信”的引用？
- [ ] 当后端返回结构化错误（`error` 事件或 REST 错误）时，Context Panel 是否：
  - [ ] 不展示半成品伪证据
  - [ ] 保留 `requestId`（便于审计/排障）
- [ ] 脱敏提示是否到位（R10.2）：
  - [ ] Evidence 含 `redactions` 时，UI 明确提示“已脱敏”及原因摘要（不显示原值）
  - [ ] 无权限时禁止提供“展开查看原始数据”的入口
- [ ] `backend/scripts/web_sse_e2e_smoke_test.py` 是否至少覆盖：
  - [ ] 正常链路含 `evidence.update`（如当前阶段支持）
  - [ ] 缺证据链路输出 `warning` 并在 UI 可见
  - [ ] 错误链路结构化 `error` 可解析且包含 `requestId`
- [ ] Context Panel 是否能稳定表达“不可验证降级”（R14.4）：
  - [ ] `warning.code=EVIDENCE_MISSING` => 明确提示“证据缺失，已降级为仅展示数据与来源”
  - [ ] `warning.code=EVIDENCE_MISMATCH` => 明确提示“证据冲突，无法给出确定性结论”
  - [ ] `validation=out_of_bounds` => 明确提示“越界/命中 guardrail”，并阻止展示确定性结论

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 47.1 - Context Panel：证据缺失/不可验证/降级态 UI

```markdown
# Context
你正在执行子任务：47.1 - Context Panel：证据缺失/不可验证/降级态 UI。

# Critical Rules
- **不得展示伪造引用**。
- **不得把不可验证数据包装成确定性数值**（必须降级语义）。

# References
- tasks: docs/tasks.md（47.1）

# Deliverables
- 一份“EvidenceViewModel 状态机/渲染规则”蓝图（文字 + 表格/要点），覆盖：
  - 初始态（无证据）
  - 流式增量态（多次 `evidence.update`）
  - `warning` 到 UI 的映射
  - `error/final` 后的稳定态
- 一份“证据合并与一致性校验规则”（不可回退/不可篡改来源）清单

# Execution Plan
1) 定义 EvidenceViewModel schema（Zod）。
2) 根据 `validation`/`warning` 渲染 UI。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**:
  - `npm -C web run build`
  - `.venv/bin/python backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（本任务核心）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
- [x] Doc References Updated

# Notes (consistency)
- 本任务文档中涉及字段名一律以 `web/schemas/*.ts` 与 `docs/contracts/api-and-events-draft.md` 为准；若发现不一致，必须先修订契约文档再调整实现任务。

---

### Task 47.2 - Context Panel：可追溯展开（sourceLocator/timeRange/lineageVersion/toolCallId）

```markdown
# Context
你正在执行子任务：47.2 - Context Panel：可追溯展开（Evidence Expand）。

# Critical Rules
- **不得展示伪造引用**。
- **sourceLocator 必须可定位但不泄露**：禁止密钥/Token/凭证/敏感原值；脱敏只用摘要与字段名。
- **final 后冻结**：收到 `final` 后不得再更新 Context Panel（避免闪烁与回退）。

# References
- PRD: docs/requirements.md（R2.2/R13.3/R10.2）
- TDD: docs/design.md（2.10.2/3.3/3.5）
- Contracts: docs/contracts/api-and-events-draft.md（3：Evidence 字段；6：SSE 事件）
- Frontend Zod: web/schemas/evidence.ts

# Deliverables
- 一份“Evidence 展开信息架构”蓝图，明确：
  - 展开层级（摘要/详情）
  - 必显字段与可选字段（严格按 Zod/Contracts 字段名）
  - `redactions` 的展示规则（只提示策略与字段名，不显示原值）
  - 无权限/脱敏场景的交互约束（不可提供绕过入口）
- 一份“可追溯跳转/定位”规则：
  - `sourceSystem + sourceLocator` 如何映射到可点击的定位信息（在不能跳转时给出不可跳转原因）
  - `timeRange` 的展示格式与时区策略（只展示，不在前端推导/修改时间范围语义）
- 一份“数据质量与置信度表达”规则：
  - `dataQualityScore` 与 `confidence` 的展示逻辑
  - 当 `validation != verifiable` 时的强制降级提示

# Verification
- **Unit**: `npm -C web test`
- **Smoke**:
  - `npm -C web run build`
  - `.venv/bin/python backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```
