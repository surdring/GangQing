# T12 意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）执行计划

本计划在 L1 约束下落地“意图识别 + 策略路由”，统一对外契约（Pydantic/Zod）、置信度与澄清策略、只读默认门禁、ACTION_* 草案输出但不执行，以及审计与验收口径。

## 0. 范围与关键结论

- **范围**：对应 `docs/tasks.md` 任务 12。
- **对外通道**：意图识别与路由结果将通过 **SSE 事件**对前端可见（你已确认选项 B）。
- **SSE 事件形态**：以当前实现与前端 schema 为准，采用**扁平字段**（`type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`）继续扩展。
- **写操作治理**：
  - `ACTION_PREPARE`：允许生成 **草案 Draft**（仅输出草案，不执行），并采取**最小落库**（Draft 可通过 `draft_id` 检索）。
  - `ACTION_EXECUTE`：L1 阶段 **一律拦截**（只读默认），返回结构化错误或进入“审批/执行”后续链路（仅预留入口，不在本任务内执行）。
- **RBAC 口径**：本任务计划以 **capability** 为准（你已确认选项 C）。
- **Schema First**：
  - 后端：意图、路由决策、草案、错误模型均使用 **Pydantic** 作为单一事实源。
  - 前端：SSE 消费必须与 `web/schemas/sseEnvelope.ts` 对齐；新增事件需补齐 Zod schema。

## 1. References（权威来源）

- PRD：`docs/requirements.md`（R15.1 / R5.1 / R6.1~R6.3）
- TDD：`docs/design.md`（2.4 / 3.9 / 3.6.1 / 6.1 / 6.4）
- Tasks：`docs/tasks.md`（任务 12）
- Contracts：`docs/contracts/api-and-events-draft.md`

## 2. Execution Plan（执行蓝图）

### 2.1 Task 12.1（意图模型与输出契约）

#### Goal
- 定义稳定的“意图识别输出”契约：
  - 意图类别（`QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE`）
  - 置信度（数值）与等级（可选）
  - 澄清问题（当不明确时）
  - 可审计字段（`requestId/sessionId/stepId` 等来自 `RequestContext`）

#### Contract（后端 Pydantic：IntentResult）
- **IntentType**：枚举
  - `QUERY`
  - `ANALYZE`
  - `ALERT`
  - `ACTION_PREPARE`
  - `ACTION_EXECUTE`
- **Confidence（强制）**：
  - `confidence: float`（0.0..1.0）
  - `confidence_label: "high"|"medium"|"low"`（可选，但建议用于策略与 UI 文案）
- **Clarification（强制：Ambiguity -> Clarify）**：
  - `needs_clarification: bool`
  - `clarification_questions: ClarificationQuestion[]`（当 `needs_clarification=true` 必须至少 1 条）
- **Rationale（审计可追溯但对外最小化）**：
  - `reason_codes: str[]`（稳定枚举/字符串，用于审计与指标聚合；避免输出长链路推理）
  - `reason_summary: str | None`（可选：短摘要，避免敏感信息）
- **Safety hints（用于只读默认/高风险拦截）**：
  - `has_write_intent: bool`（当识别到写倾向或不确定时，必须偏向 true）
  - `risk_level: "low"|"medium"|"high"`

#### 对外 SSE 表示（新增事件）
- 新增 SSE 事件类型：`intent.result`
  - **Envelope**：必须与现有 `backend/gangqing/schemas/sse.py`（扁平字段）与前端 `web/schemas/sseEnvelope.ts` 对齐：
    - `type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`
  - `payload`：`IntentResult`（或其对外安全子集）

#### 置信度与澄清策略（统一口径）
- **阈值建议（可配置化）**：
  - `confidence >= 0.80`：可直接进入路由（仍需 RBAC/门禁）
  - `0.50 <= confidence < 0.80`：优先澄清（除非用户问题非常明确且只读查询）
  - `< 0.50`：必须澄清
- **澄清问题生成原则**：
  - 每次澄清最多 1~3 个问题
  - 问题必须可回答且能显著减少歧义（例如：时间范围、对象、指标口径、是否只是生成草案）
  - 不得引导用户越权或直接执行写操作

#### Target Files（计划修改/新增）
- **新增/修改（后端）**：
  - `backend/gangqing/schemas/intent.py`（IntentType / IntentResult / ClarificationQuestion）
  - `backend/gangqing/agent/intent_classifier.py`（意图识别模块边界：输入 `message + ctx`，输出 `IntentResult`）
  - `backend/gangqing/schemas/sse.py`（加入 `intent.result` 对应 payload typing / event 声明，保持扁平 envelope）
- **新增/修改（前端）**：
  - `web/schemas/sseEnvelope.ts`（补齐 `intent.result` 的 Zod schema，加入到 discriminatedUnion）

#### 验收要点
- 任意请求必须产出 IntentResult：
  - 要么 `needs_clarification=false` 且给出稳定意图
  - 要么 `needs_clarification=true` 且给出澄清问题
- `confidence` 取值范围严格为 0..1
- 不允许“猜测执行”：当 `needs_clarification=true` 时不得继续调用工具或生成草案

---

### 2.2 Task 12.2（策略路由：工具白名单 + 只读默认门禁 + ACTION 草案）

#### Goal
- 基于 `IntentResult + RequestContext + capability` 输出稳定路由决策（RouteDecision）：
  - 明确可用工具集合（白名单）
  - 明确下一步：继续（只读查询/分析）、发起澄清、生成草案、或阻断
  - 对 `ACTION_EXECUTE` 做 L1 拦截

#### Contract（后端 Pydantic：RouteDecision）
- `decision_type: "clarify"|"allow"|"draft"|"block"`
- `selected_intent: IntentType`
- `allowed_tool_names: str[]`（只读意图仅包含 read-only 工具；L1 只读默认）
- `blocked_reason_code: str | None`（当 `decision_type=block` 必填；推荐复用稳定码，如 `GUARDRAIL_BLOCKED/FORBIDDEN`）
- `clarification: ClarificationQuestion[] | None`
- `draft: ActionDraft | None`（当 `decision_type=draft` 必填）
- `audit_tags: dict[str, str]`（用于审计聚合：intent/risk_level/policy_version 等）

#### ACTION_* 门禁与草案策略（强制）
- **只读默认**：任何不确定或高风险请求按只读处理。
- **ACTION_PREPARE**：允许生成草案 `ActionDraft`，但：
  - 不得调用任何写工具
  - 草案必须包含：
    - `draft_id`（草案标识；本任务采用**最小落库**，必须可用于后续检索/提交审批）
    - `action_type`（例如 `schedule_change` / `parameter_change` 等最小枚举，允许先用 `unknown` 并要求澄清）
    - `target_resource_summary`（脱敏摘要）
    - `constraints`（约束清单）
    - `risk_assessment`（风险等级与原因 codes）
    - `required_capabilities`（后续提交/审批/执行所需能力集合）
- **ACTION_EXECUTE**：L1 阶段一律 `block`：
  - 对外通过 SSE `error` 事件返回 `ErrorResponse(code=GUARDRAIL_BLOCKED)`（英文 message）
  - 同时通过 SSE `final(status=error)` 结束
  - 可在 `warning/progress` 中给用户中文提示“需要审批/仅生成草案”等（注意：SSE `warning.message` 允许中文；`error.message` 必须英文）

#### 工具白名单策略（只读）
- 按 capability 控制：
  - 例如：只读查询工具要求 `tool:postgres:read`
- 路由输出必须显式列出 `allowed_tool_names`，避免“模型任意挑工具”。

#### 高风险拦截口径（强制）
- 命中以下任一情形，路由必须 `block` 或 `clarify`：
  - 明确写入/执行倾向（特别是 `ACTION_EXECUTE`）
  - 权限缺失（capability 不满足）
  - 试图绕过审计/越权访问/批量导出敏感数据
  - 指令注入/提示词攻击特征（若已有检测能力，路由层必须接入结果）

#### 对外 SSE 表示（新增事件）
- 新增 SSE 事件类型：`routing.decision`
  - `payload`：`RouteDecision`（对外安全子集：不含敏感细节）
- 新增 SSE 事件类型：`draft.created`
  - `payload`：`ActionDraft`（或 draft 引用 + 摘要）

#### 审计（强制）
- 必须新增/补齐审计事件写入点：
  - `intent.classified`（记录 intent、confidence、needs_clarification、risk_level、reason_codes）
  - `routing.decided`（记录 decision_type、allowed_tool_names 摘要、block reason）
  - `draft.created`（记录 draft_id、action_type、风险等级、required_capabilities）
- 审计字段最小集合必须包含：
  - `requestId/tenantId/projectId`
  - 可用时：`sessionId/userId/role/stepId`

#### Target Files（计划修改/新增）
- **后端**：
  - `backend/gangqing/agent/router.py`（策略路由核心：输入 `ctx + intentResult`，输出 `RouteDecision`）
  - `backend/gangqing/schemas/routing.py`（RouteDecision / ActionDraft）
  - `backend/gangqing/common/audit_event_types.py`（补充 intent/routing/draft 事件类型枚举）
  - `backend/gangqing/common/audit.py`（增加便捷函数：write_intent_event/write_routing_event/write_draft_event；注意 actionSummary 必须脱敏）
  - `backend/gangqing/api/chat.py`（在现有 SSE 流中插入：intent.result -> routing.decision -> 后续阶段；当需澄清或被 block 时必须尽快输出并 final）
  - `backend/gangqing_db/`（草案最小落库：新增 Draft 表/模型与最小读写接口，供 smoke test 与后续审批链路使用）
  - `backend/migrations/versions/`（为 Draft 最小落库新增迁移，保持可回滚）
- **前端**：
  - `web/schemas/sseEnvelope.ts`（新增 `routing.decision`、`draft.created` schema）
  - （如前端要展示）`web/components/ChatInterface.tsx` / `ContextPanel.tsx`：仅在后续实现阶段处理 UI；本计划只定义契约与事件。

#### 验收要点
- `ACTION_EXECUTE` 在 L1 必须被阻断：
  - SSE 中出现 `error.payload.code=GUARDRAIL_BLOCKED`
  - 紧跟 `final(status=error)`
  - 审计中存在 `intent.classified` + `routing.decided`（且同一 `requestId` 可关联）
- `ACTION_PREPARE` 必须生成草案且不执行：
  - SSE 中出现 `draft.created`
  - 审计中存在 `draft.created`
- 不明确意图必须澄清：
  - SSE 输出 `intent.result(needs_clarification=true)`
  - 路由必须 `decision_type=clarify`
  - 不得触发工具调用事件 `tool.call`

---

### 2.3 Task 12.3（测试与验收：单元 + 冒烟 + 契约对齐）

#### Goal
- 用自动化测试固化：
  - 澄清策略（Ambiguity -> Clarify）
  - 写意图门禁（Read-Only Default）
  - 草案输出（ACTION_PREPARE）
  - 错误模型结构化字段完整性
  - SSE 事件与前端 Zod schema 的一致性（契约测试）

#### Unit Tests（后端，pytest）
- 重点覆盖（不使用 mock 服务；纯逻辑单元测试可用依赖注入 fake 实现，但需模拟真实错误形态）：
  - IntentResult schema 校验：
    - `confidence` 越界必须失败
    - `needs_clarification=true` 时 questions 不能为空
  - 路由决策：
    - 低置信度/歧义 => `clarify`
    - `ACTION_EXECUTE` => `block` + `GUARDRAIL_BLOCKED`
    - `ACTION_PREPARE` => `draft`
  - 结构化错误：
    - `ErrorResponse` 必含 `code/message(英文)/retryable/requestId`
  - SSE：
    - `meta` 必为首事件、`final` 必为最后事件
    - 错误路径必须 `error -> final(status=error)`

#### Contract Tests（前端 Zod + 后端 Pydantic）
- 新增/更新测试点：
  - 前端 `SseEnvelopeSchema` 能解析 `intent.result` / `routing.decision` / `draft.created`
  - 事件字段严格（`.strict()`）不允许后端额外字段漂移

#### Smoke Test（真实集成，强制 No Skip）
- **必须补齐脚本**：`backend/scripts/intent_routing_smoke_test.py`（当前仓库任务 12 要求存在）
- 冒烟测试场景（至少 2 条成功/失败混合）：
  - **成功（只读）**：输入典型查询 => SSE 出现 `meta`、`intent.result(QUERY/ANALYZE)`、`routing.decision(allow)`、（可选）`tool.call/tool.result`、`final(success)`
  - **澄清**：输入歧义问题 => SSE 出现 `intent.result(needs_clarification=true)`、`routing.decision(clarify)`、`final(success 或 cancelled)`（根据产品策略，但不得 tool.call）
  - **写执行阻断**：输入明确执行写操作 => SSE 出现 `error(GUARDRAIL_BLOCKED)` + `final(error)`
  - **草案**：输入“生成草案” => SSE 出现 `draft.created` + `final(success)`，且无写工具执行
- 冒烟测试必须连接：真实 FastAPI + 真实 Postgres + 真实 llama.cpp；缺配置或依赖不可用必须失败。

#### Verification Commands（验收命令）
- Unit：`pytest -q`
- Smoke：`backend/scripts/intent_routing_smoke_test.py`

## 3. Deliverables Definition（交付物定义）

### 3.1 Target Files（最小清单）
- 后端（Pydantic 单一事实源）：
  - `backend/gangqing/schemas/intent.py`
  - `backend/gangqing/schemas/routing.py`
  - `backend/gangqing/agent/intent_classifier.py`
  - `backend/gangqing/agent/router.py`
  - `backend/gangqing/api/chat.py`
  - `backend/gangqing/common/audit_event_types.py`
  - `backend/gangqing/common/audit.py`
  - `backend/tests/test_intent_contracts.py`
  - `backend/tests/test_intent_routing.py`
  - `backend/scripts/intent_routing_smoke_test.py`
- 前端（Zod 单一事实源）：
  - `web/schemas/sseEnvelope.ts`（新增事件 schema）
  - `web/tests/contractSchemas.test.ts`（补齐 SSE 新事件覆盖）

### 3.2 API Contracts（对外契约与 SSE 事件）
- SSE 新增事件：
  - `intent.result`
  - `routing.decision`
  - `draft.created`
- 错误同构：
  - `type=error` 的 `payload` 必须为 `ErrorResponse`
  - `error.message` **必须英文**

### 3.3 Error Model（错误码与英文 message）
- 本任务触达的最小错误码集合（必须在测试覆盖）：
  - `GUARDRAIL_BLOCKED`（写执行阻断/高风险拦截）
  - `FORBIDDEN`（capability 缺失）
  - `VALIDATION_ERROR`（输入/模型结构化输出校验失败）
  - `CONTRACT_VIOLATION`（SSE/对外输出不符合 schema）
  - `INTERNAL_ERROR`（兜底）

### 3.4 Observability & Audit（审计口径）
- 审计事件最小覆盖：
  - `intent.classified`
  - `routing.decided`
  - `draft.created`
  - 复用已有：`rbac.denied`、`tool_call`、`query`、`api.response`
- 必填字段：
  - `requestId`（强制）
  - `tenantId/projectId`（强制）
  - 可用时：`sessionId/userId/role/stepId/toolName`
- 脱敏：
  - `actionSummary` 仅允许摘要字段，禁止敏感原文/密钥/token/SQL/大量 rows

## 4. Risks & Decisions（风险与决策）

- **契约一致性风险**：`docs/contracts/api-and-events-draft.md` 存在“扁平 SSE envelope”与“嵌套 envelope 对象”的表述并存；当前前端与后端实现倾向扁平结构（`web/schemas/sseEnvelope.ts` 与 `backend/gangqing/schemas/sse.py`）。
  - 决策：Task 12 以 **扁平 envelope** 为准，新增事件沿用现有结构。
- **只读默认红线**：任何 ACTION_EXECUTE 或不确定写倾向必须阻断或澄清；不得“先执行再补审计”。
- **No Skip 集成测试风险**：真实 llama.cpp / Postgres 不可用会导致冒烟失败；需提前确保 `.env.local` 或环境变量齐备。

## 5. Checklist（用于你确认计划是否满足核心约束）

- [x] 只读默认：ACTION_EXECUTE L1 必拦截
- [x] Ambiguity -> Clarify：意图不明必须澄清
- [x] 结构化错误：`code/message(英文)/requestId/retryable/details?`
- [x] Schema First：后端 Pydantic + 前端 Zod 对齐
- [x] RBAC & Audit：意图/路由/草案写审计，字段含 requestId
- [x] Real Integration：冒烟脚本连真实 FastAPI + Postgres + llama.cpp，不得 skip
