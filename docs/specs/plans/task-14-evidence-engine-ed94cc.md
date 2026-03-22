# Task 14 证据链引擎执行蓝图（Claim/Citation/Lineage/ToolCallTrace + evidence.update）

本计划将证据链引擎拆分为“数据结构与契约边界、组装/一致性校验、SSE 增量事件语义与顺序、降级/拒答语义、可自动化验收（真实集成）”五个可交付里程碑，并严格对齐现有后端 Pydantic 与前端 Zod 的单一事实源。

## 0. 范围与权威参考

- **任务目标**：完成 Task 14（`docs/tasks.md` #14）——“证据链引擎：Claim/Citation/Lineage/ToolCallTrace 组装与增量更新”。
- **强制约束**（来自 `docs/requirements.md`、`docs/design.md`、`docs/contracts/api-and-events-draft.md`）：
  - **Evidence-First**：数值结论必须映射至少 1 条 Evidence；Evidence 必须包含 `sourceSystem/sourceLocator/timeRange/confidence/validation`；计算类结论必须绑定 `lineageVersion`，缺失需拒答确定性输出或降级并输出 `warning`。
  - **Structured Errors**：对外错误 `message` 必须英文；SSE `type=error` 的 `payload` 必须与 REST 错误同构：`code/message/details?/retryable/requestId`。
  - **Schema 单一事实源**：后端 Pydantic（Evidence 与 SSE 事件）；前端 Zod（Evidence 与 SSE 事件）。
  - **RBAC + Masking**：Evidence 与 tool result 默认脱敏；脱敏策略可审计。
  - **Real Integration（No Skip）**：冒烟/集成测试必须连真实 FastAPI + 真实 Postgres；配置缺失或服务不可用必须失败，禁止 skip。

## 1. 现状对齐（避免契约漂移）

### 1.1 当前 Evidence 模型（已存在）
- 后端：`backend/gangqing_db/evidence.py`（Pydantic）
- 前端：`web/schemas/evidence.ts`（Zod）
- 关键字段已满足任务要求的子集：
  - `evidenceId/sourceSystem/sourceLocator/timeRange/toolCallId?/lineageVersion?/dataQualityScore?/confidence/validation/redactions?`

### 1.2 当前 SSE Envelope（已存在）
- 后端：`backend/gangqing/schemas/sse.py`（Pydantic）
- 前端：`web/schemas/sseEnvelope.ts`（Zod）
- **权威决策（以 T15 为准）**：SSE 事件结构采用“顶层扁平字段 + payload”（`type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`），不采用 `type + envelope + payload` 的嵌套结构。
- **契约收敛动作（与 T15 一致）**：需要在 `docs/contracts/api-and-events-draft.md` 中把 6.1.2 的结构描述修订为扁平结构，确保单一事实源。
- **sequence 硬约束（与 T15 一致）**：单连接内必须严格单调递增，且 `meta` 必须为首事件并满足 `sequence=1`。
- **event: 行策略（与 T15 一致）**：服务端可以输出 `event:` 行用于兼容/调试，但客户端与测试必须只以 JSON 的 `type` 字段为准。

### 1.3 当前 chat SSE 输出的证据引用行为（已存在）
- `backend/gangqing/api/chat.py`：
  - `tool.result.payload.evidenceRefs` 从工具结果里提取 `evidenceId` 列表（排序去重），证据缺失会输出 `warning(EVIDENCE_MISSING)`。
  - **缺口**：尚未输出 `evidence.update`，也没有 Claim/Citation/Lineage/ToolCallTrace 的组装层。

## 2. 设计决策（基于最佳实践的选择）

### 2.1 增量事件的“不可变事实”优先
参考事件溯源（Event Sourcing）与事件驱动系统最佳实践：
- **事件应倾向不可变、append-only**，以形成审计轨迹；历史事件不应被修改（Azure Event Sourcing pattern：事件是永久信息源；更新通过新增补偿事件/新版本结构实现）。
- 事件投递通常为 **at-least-once**，消费者必须 **幂等**（CockroachLabs：重复事件需要通过幂等处理；顺序要求应尽量缩小到“同一实体范围内”而非全局）。

### 2.2 evidence.update 的落地选择：append 为主，update 为“补全/纠错”的受控通道
结合 `docs/contracts/api-and-events-draft.md` 已定义的 `mode=append|update|reference`：
- **默认**：`append`（新增 Evidence）。
- **允许**：`update`（同一 `evidenceId` 的“字段补全/验证状态更新/追加 redactions”），但必须遵守“字段不可回退/不可篡改来源”的规则（见 4.2）。
- **保守**：不引入 delete；如需“撤销/纠错”，以新增 `warning`/新增 Evidence（不同 `evidenceId`）表达冲突与裁决，而不是删除旧 Evidence。

### 2.3 lineageVersion 的强约束来源
- 结合 `docs/requirements.md#R7.3` 与 `docs/design.md#5.2/#5.6`：
  - **计算类结论**必须引用指标口径仓库的版本（`lineageVersion`），缺失或冲突需拒绝确定性结论。
- **落地策略（Task 14）**：
  - Evidence 可选携带 `lineageVersion`（保持与现有 Evidence 模型一致）。
  - Claim/Lineage 结构中：
    - **若 claim 是计算结果**，则 `lineageVersion` 必填；否则 claim 必须进入降级（warning + 非确定性表达）。

## 3. 交付物与目录结构（仅规划，不在本阶段写实现代码）

> 说明：以下为“将要新增/修改”的文件结构规划，具体实现将在 Umbrella 阶段结束后进入。

### 3.1 后端（Pydantic 单一事实源）
- **新增**（建议路径，沿用现有 `gangqing_db` 作为契约模型库）：
  - `backend/gangqing_db/evidence_chain.py`
    - `Claim` / `Citation` / `Lineage` / `ToolCallTrace` / `EvidenceChain`
    - 一致性校验器（Pydantic validators）
  - `backend/gangqing/schemas/evidence_update.py`（或直接扩展 `backend/gangqing/schemas/sse.py`）
    - `SseEvidenceUpdatePayload` / `SseEvidenceUpdateEvent`
- **修改**：
  - `backend/gangqing/schemas/sse.py`
    - 增加 `evidence.update` 事件（保持扁平 Envelope，与前端 discriminatedUnion 对齐）
  - `backend/gangqing/api/chat.py`
    - 在 tool.result 前后插入 `evidence.update`（规则见 5.2）

### 3.2 前端（Zod 单一事实源）
- **新增/修改**：
  - `web/schemas/sseEnvelope.ts`
    - 增加 `evidence.update` 的 envelope schema（并加入 `SseEnvelopeSchema` discriminatedUnion）
  - `web/schemas/evidence.ts`
    - 若 EvidenceChain 引入前端展示所需的 Claim/Citation/Lineage/ToolCallTrace，也需在 `web/schemas/` 下新增对应 Zod schema（例如 `evidenceChain.ts`），并保持字段命名与后端 by_alias 输出一致。

### 3.3 测试与脚本
- **新增**：
  - `backend/scripts/evidence_smoke_test.py`（真实 FastAPI + 真实 Postgres；无配置/服务不可用必须失败）
- **新增/修改**：
  - `backend/tests/test_evidence_chain_models.py`（单元：模型校验/一致性规则/错误码与英文 message）
  - `backend/tests/test_sse_evidence_update_contract.py`（单元：SSE evidence.update schema 断言 + sequence 单调递增约束的可测试组件）

## 4. EvidenceChain 数据结构与契约边界（Task 14.1）

### 4.1 EvidenceChain 的定位
EvidenceChain 是“可追溯证据的装配层”，其职责是：
- 把一次 request 内的 **结论（Claims）** 与 **证据（Evidence/Citations）**、**口径（Lineage）**、**工具轨迹（ToolCallTrace）** 严格绑定。
- 输出给：
  - SSE `evidence.update`（增量）
  - （未来）`GET /api/v1/evidence/chains/{requestId}`（按 `docs/contracts/api-and-events-draft.md` 8.1）

### 4.2 结构定义（最小可用字段集合）

#### 4.2.1 Claim（结论条目）
- **必备字段（最小）**：
  - `claimId`：稳定 id（建议与 `requestId + index` 或 UUID 绑定；需可追溯且不可碰撞）
  - `claimType`：`number|text|table|chart|boolean`（至少要区分 number，因为 number 需要 Evidence-First 强约束）
  - `subject`：结论对象摘要（例如 `"BlastFurnace#2"`，脱敏/摘要形式）
  - `value`：结论值（number/text 等，取决于 claimType）
  - `unit?`：数值单位（若适用）
  - `evidenceRefs`：关联的 `evidenceId[]`（**数值 claim 必须非空**）
  - `lineageVersion?`：
    - **计算类数值**：必填
    - 非计算/原始展示：可选
  - `validation`：`verifiable|not_verifiable|out_of_bounds|mismatch`（与 Evidence.validation 同枚举，便于前端统一渲染）

#### 4.2.2 Citation（来源引用）
- 在 L1 现状中 Evidence 已包含 sourceSystem/sourceLocator/timeRange，因此 Citation 可以作为“面向展示的映射层”：
  - `citationId`
  - `sourceSystem/sourceLocator/timeRange`
  - `extractedAt`（建议补齐；若当前工具未提供，可先通过 tool.result timestamp 作为近似，但要在 validation/notes 中标注）
  - `filtersSummary?`（脱敏摘要）
  - `evidenceId`（引用 Evidence）

#### 4.2.3 Lineage（口径/公式）
- `metricName`
- `lineageVersion`
- `formulaId?`（若有）
- `inputs`（引用 Evidence/Citations 的列表或摘要）

#### 4.2.4 ToolCallTrace（工具调用轨迹）
- 复用 SSE tool.call/tool.result 的关键字段，确保关联：
  - `toolCallId` / `toolName`
  - `attempt?` / `maxAttempts?`（若本系统未来细化每次 attempt）
  - `status` / `durationMs?`
  - `argsSummary`（必须脱敏）
  - `resultSummary`（必须脱敏）
  - `error?`（同构 ErrorResponse，message 英文）
  - `evidenceRefs`（与 SSE tool.result 一致）

#### 4.2.5 EvidenceChain（聚合根）
- `requestId/tenantId/projectId/sessionId?`
- `claims[]`
- `evidences[]`（复用现有 Evidence 模型）
- `citations[]`（可选；若短期不引入 citations，可由前端直接展示 Evidence.sourceLocator）
- `lineages[]`（可选；但计算类 claim 若存在，至少要能输出 lineageVersion）
- `toolTraces[]`（可选；用于 Context Panel 关联工具与证据）
- `warnings[]`（结构化 warning 列表；用于最终收敛）

### 4.3 一致性校验规则（Evidence-First）
- **数值 Claim 必须有证据**：`claimType=number` => `evidenceRefs.length >= 1`，否则：
  - 输出 `warning(code=EVIDENCE_MISSING, message=英文, details={claimId,...})`
  - Claim.validation 设置为 `not_verifiable`
  - 最终文本输出不得把该数值作为确定性结论（见 6）
- **证据字段完整性**：每条 Evidence 必须满足现有 Evidence schema（timeRange end>start 等）。
- **计算类结论必须绑定 lineageVersion**：若 claim 标记为“computed”或由工具/模板声明为计算结果，则 `lineageVersion` 必填；缺失 => `warning(code=EVIDENCE_MISSING 或 CONTRACT_VIOLATION 按阶段选择)` 并拒绝确定性输出。
- **证据与结论一致性**（最小 L1 规则）：
  - 若 Evidence.validation 为 `mismatch/out_of_bounds/not_verifiable`，claim.validation 不能为 `verifiable`。
  - 若同一 claim 引用的 evidences 中存在互斥来源/时间窗冲突（可检测到），输出 `warning(code=EVIDENCE_MISMATCH)` 并将 claim.validation= `mismatch`。

## 5. SSE `evidence.update` 事件（Task 14.2）

### 5.1 事件契约（扁平 envelope + payload）
- 事件类型：`type = "evidence.update"`
- 顶层字段：沿用现有 `SseEvent`（`timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`）
- `payload`（对齐 `docs/contracts/api-and-events-draft.md` 的模式，但以扁平 envelope 表达）：
  - `mode`：`append|update|reference`
  - `evidence`：Evidence（当 mode=append|update 必填）
  - `evidenceId`：string（当 mode=reference 必填）
  - `toolCallId?`：用于把本次 evidence.update 绑定到某次工具调用（建议加；若不加，可依赖 evidence.toolCallId）

### 5.2 发送时机与顺序约束
- **核心目标**：前端 Context Panel 能在工具返回后“立即增量渲染”。
- **顺序（单连接 sequence 单调递增）建议**：
  1. `tool.call`
  2. （可选）`progress(stage=tooling, ...)`
  3. 工具成功返回并得到 Evidence 后：
     - 先发 1..n 条 `evidence.update(mode=append)`（每条 1 个 Evidence；或按批发送，但建议单条便于增量 UI）
     - 再发 `tool.result(evidenceRefs=...)`
  4. 后续若 Evidence 被补全/验证状态更新：发 `evidence.update(mode=update)`（必须受控 merge）
  5. `final`
- **约束**：
  - `tool.result.payload.evidenceRefs` 必须是此前已发送（append/update）过的 `evidenceId` 子集；否则视为 **契约违规**（应触发 `CONTRACT_VIOLATION` 或至少 warning + 审计）。
  - `sequence` 必须严格递增；`final` 之后不得再有事件。

### 5.3 幂等与去重（客户端/服务端协同）
- 基于“at-least-once”投递最佳实践：
  - 客户端按 `evidenceId` 去重。
  - 服务端尽量保证同一 `evidenceId` 的 append 只发一次；若重发也必须不破坏最终状态。

### 5.4 `message.delta` 与 `evidence.update` 的相对顺序决策（以 T15 为准 + 参考最佳实践）

- **最佳实践参考（摘要）**：在主流“可追溯 RAG/Streaming citations”实现中，citation 往往可以与文本增量**交错出现**，甚至在“fast citations”模式下做到“inline/near-real-time traceability”（例如 Cohere streaming 会在生成过程中发出 citation-start 等事件）。这意味着“先文本后证据”与“先证据后文本”都可能发生，关键在于消费者的幂等与关联能力，以及对“未可验证内容”的 UI/语义约束。
- **本项目硬约束**：Evidence-First 要求“数值结论必须有证据”，因此 **不允许在证据尚未出现时输出确定性数值结论**。
- **落地决策（约束变体，推荐）**：
  - **不强制** `message.delta` 与 `evidence.update` 的全局相对顺序（两者可交错），只强制 T15 的序列规则：`meta(sequence=1)` 首、`final` 末、`sequence` 严格递增。
  - **强制“先证据后断言”**：
    - 若某段 `message.delta` 将要输出“需要证据背书的数值/关键事实”，则必须满足：该段落引用的 `evidenceId` 已经通过 `evidence.update` 发出（append/update），并且该段落在语义上可被前端/审计关联到 `evidenceRefs`（通过 `toolCallId`/`evidenceRefs`/EvidenceChain 组装）。
    - 若无法满足，则该段只能以“非确定性/待验证”的表达输出，并且必须伴随 `warning(code=EVIDENCE_MISSING, message=英文, details=...)` 或将 Claim.validation 置为 `not_verifiable`，以保证对外语义可机器判定。
  - **实现侧建议（用于后续实现阶段）**：以“与来源数据相关的 message.delta 段落”为边界，在触发该段之前尽快 emit 对应 `evidence.update`，以提升 UI 的即时可追溯性。

## 6. 降级/拒答语义（Task 14.3）

### 6.1 warning vs error vs final（对外语义）
- **warning**：可恢复/可降级场景，流继续。
  - 示例：`EVIDENCE_MISSING`（工具结果没带 evidenceRefs）、`UPSTREAM_TIMEOUT`（已安排重试/降级）、`EVIDENCE_MISMATCH`（发现冲突但仍可展示来源数据）。
- **error**：不可恢复，必须紧跟 `final(status=error)`。
  - 示例：鉴权/隔离缺失（`AUTH_ERROR/FORBIDDEN`），契约输出不合法（`CONTRACT_VIOLATION`），内部错误（`INTERNAL_ERROR`）。
- **final**：流结束标志；
  - `status=success` 不代表“所有结论可验证”，只代表“流程完成且无不可恢复错误”。可验证性由 warnings/claims.validation 体现。

### 6.2 关键降级规则表（触发条件 -> 事件策略）
- **缺少任何 Evidence 支撑的数值结论**：
  - 事件：必须发 `warning(code=EVIDENCE_MISSING, message=英文, details={claimId,...})`
  - Claim：`validation=not_verifiable`
  - 最终输出：不得给出确定性数值；改为“仅展示数据与来源/需要补齐证据”的表达
- **Evidence 存在 mismatch**：
  - 事件：`warning(code=EVIDENCE_MISMATCH, message=英文, details={...})`
  - Claim：`validation=mismatch`
  - 最终输出：展示冲突来源与时间窗，不裁决“唯一真值”
- **out_of_bounds（物理边界/变化率越界）**：
  - 事件：`warning(code=GUARDRAIL_BLOCKED 或 专用 code, message=英文)`（若直接阻断可升级为 error；L1 建议先 warning + 降级展示）
  - Evidence：`validation=out_of_bounds`
  - 最终输出：必须标注越界与不确定
- **计算类结论缺 lineageVersion**：
  - 事件：`warning(code=EVIDENCE_MISSING, message=英文, details={missing:"lineageVersion"...})`
  - Claim：`validation=not_verifiable`
  - 最终输出：拒绝确定性计算值；可展示原始数据证据与“口径缺失”原因

### 6.3 英文 message 规范（可检索、可审计、非敏感）
- 统一模板（示例风格，不是实现代码）：
  - `Evidence missing for numeric claim`
  - `Evidence mismatch detected between sources`
  - `Lineage version is required for computed claim`
  - `Evidence validation is not verifiable`
- 约束：message 不得包含敏感原值/SQL/凭证；详细上下文放入脱敏后的 `details`。

## 7. RBAC + Masking（证据与工具结果的默认策略）

### 7.1 默认脱敏要求
- Evidence 与 tool result 的对外输出默认脱敏（遵循 `docs/contracts/api-and-events-draft.md` 的禁止 key 规则与 `redactions` 建议结构）。
- `argsSummary/resultSummary/sourceLocator` 必须进行递归脱敏（按 key 命中替换为 `[REDACTED]`）。

### 7.2 可审计字段
- Evidence 的 `redactions` 必须说明：
  - `reason`（例如 `masked_by_role_policy`）
  - `policyId`（策略版本）
  - `fields[]`（被脱敏字段名列表）
- 审计事件（tool_call/tool_result）需要记录脱敏后的摘要与策略命中信息（不包含原值）。

## 8. 可自动化验收口径（单元 + 冒烟，且真实集成）

### 8.1 单元测试（pytest -q）必须覆盖
- **模型与一致性校验**（不依赖外部服务）：
  - Evidence.timeRange `end > start`（已存在，但纳入证据链测试集）
  - 数值 claim 缺 evidenceRefs => 触发降级（warning 生成策略的纯逻辑部分）
  - 计算类 claim 缺 lineageVersion => 降级/拒答策略
  - Evidence.validation 与 Claim.validation 的一致性约束（不得出现 claim=verifiable 但 evidence=mismatch 等）
- **SSE 契约**：
  - `evidence.update` 的 payload 校验（mode 与 evidence/evidenceId 的互斥必填）
  - `sequence` 单调递增（可通过对生成器输出做断言）
- **Structured Errors**：
  - 构造 `SseErrorEvent`/`tool.result.status=failure` 时 payload.error 必须可被 `ErrorResponse` 验证；message 英文。

### 8.2 冒烟测试（backend/scripts/evidence_smoke_test.py）必须覆盖
- **真实集成前置条件**：
  - 真实 FastAPI 服务可启动
  - 真实 Postgres 可连接且已迁移/有造数
  - 必要环境变量缺失 => 测试必须失败（英文错误）
- **成功路径**：
  - 调用 `/chat/stream`，收集 SSE 事件
  - 断言最小序列（以 T15 最小事件集合为准）：
    - `meta(sequence=1)` -> `tool.call` -> `tool.result` -> `message.delta(>=1)` -> `final(status=success)`
    - 若返回 Evidence：`evidence.update(>=1)` 必须出现（与 `toolCallId/evidenceRefs` 可关联），且满足 `tool.result.payload.evidenceRefs` 与已 emit 的 evidenceId 一致性约束
  - 断言 `sequence` 严格递增
  - 断言每条 `evidence.update.payload.evidence` 可被 Evidence Pydantic 验证
- **失败/降级路径（至少 1 条）**：
  - 触发 `EVIDENCE_MISSING`：让工具返回不含 evidenceId（或模拟工具结果缺失 evidence 字段的真实分支），断言出现 `warning(code=EVIDENCE_MISSING, message=英文)` 且仍然 `final(status=success)`（流程完成但结论降级）
  - 或触发 `UPSTREAM_TIMEOUT`：断言出现 warning/progress，最终要么重试成功，要么 `error+final(status=error)`（按系统重试策略）

## 9. 风险点与落地注意事项

- **契约文档不一致风险**：`docs/contracts/api-and-events-draft.md` 目前存在“嵌套 envelope”与“扁平 envelope”混用描述。Task 14 **以 T15 的扁平 envelope 决策为准**，必须在实现前/实现中完成 contracts 修订收敛，否则前后端/测试会长期漂移。
- **证据更新的 merge 复杂度**：`mode=update` 必须严格定义“允许补全哪些字段、禁止回退哪些字段、冲突如何发 warning”。建议将 merge 规则写成纯函数并单测。
- **真实集成测试稳定性**：必须保证 smoke test 对依赖缺失的失败信息清晰（英文），并且不使用 skip。

## 10. 里程碑拆分（与 Task 14.1~14.4 对齐）

- **14.1（模型与组装规则）**：确定 EvidenceChain 的最小字段集 + Pydantic/Zod 对齐 + 一致性校验规则表。
- **14.2（SSE evidence.update）**：定义 `evidence.update` 事件 schema（后端/前端）+ 明确发送时机与顺序约束。
- **14.3（降级/冲突处理）**：规则表落地为可测试的决策逻辑；定义英文 message 规范与错误码映射。
- **14.4（真实冒烟测试）**：补齐 `backend/scripts/evidence_smoke_test.py`，覆盖成功 + 降级/失败路径；在本地/CI 可运行。
