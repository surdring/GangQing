# T47 前端 Context Panel 强化：执行蓝图（仅规划）

本蓝图定义 Context Panel 的输入契约、Evidence 状态模型、流式增量合并与可追溯展开信息架构，并给出可自动化验收口径（不包含任何代码实现）。

## 1. 背景与权威约束（Single Source of Truth）

- 权威需求：`docs/requirements.md`（R6.2/R13.3/R14.4/R10.2）
- 权威设计：`docs/design.md`（2.10.2/3.5/5.1/6）
- 权威对外契约：`docs/contracts/api-and-events-draft.md`
  - SSE 扁平 Envelope（`type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`）
  - `evidence.update / warning / error / final` 最小集合
  - Evidence 字段与降级规则（`validation`）
  - ErrorResponse 统一模型（`code/message/details?/retryable/requestId`，`message` 必须英文）
- 前端权威 Schema（Zod）：
  - `web/schemas/evidence.ts`
  - `web/schemas/errorResponse.ts`
  - `web/schemas/sseEnvelope.ts`

## 2. 目标（Task 47 范围）

- 明确 Context Panel 的**输入契约**：只渲染通过 Zod 校验的 SSE 事件 payload 或 REST 响应（禁止 `unknown` 直接进入渲染）。
- 落地 Evidence 状态模型（必含）：
  - `verifiable` / `not_verifiable` / `out_of_bounds` / `mismatch`
- 定义 Evidence 的**增量合并策略**与“不允许回退/不允许篡改来源”的强约束，保证流式更新稳定、无闪烁、不丢字段。
- 定义“可追溯展开”的信息架构：
  - `sourceSystem/sourceLocator/timeRange/lineageVersion/toolCallId/dataQualityScore/redactions`
- 定义 `warning` 与 Evidence 状态映射，让 UI 明确表达“为什么降级/不可验证”。

## 3. 非目标（明确不做）

- 不实现任何 UI 代码/Hook/后端代码。
- 不重新设计全局布局，仅聚焦右侧 Context Panel。
- 不新增对外协议字段；如确需扩展，必须先更新 `docs/contracts/api-and-events-draft.md` 并同步提示词引用。

## 4. 输入契约与“只渲染已校验数据”规则

### 4.1 SSE 输入：只接受 `SseEnvelopeSchema` 解析成功的事件

- Context Panel 的所有状态变更只能来自 `useChatSseStream` 传出的回调：
  - `onEvidenceUpdate(payload: SseEvidenceUpdatePayloadSchema)`
  - `onWarning(payload: SseWarningPayloadSchema)`
  - `onError(error: ErrorResponseSchema)`
  - `onFinal()`
- 禁止：在 Context Panel 内部对 `unknown` 做 ad-hoc 解析并渲染。

### 4.2 REST 输入（如存在）

- 任意非 2xx 必须是 `ErrorResponseSchema`。
- 2xx 的 evidence 列表/链路对象必须对应已有 Zod schema（若当前无 schema，需要先补 schema 才能作为输入；不允许“先渲染再补契约”。）

## 5. Context Panel 状态模型（Panel 级）

> Panel 状态用于表达“证据是否可用/是否稳定/是否需要降级提示”，并决定是否允许继续接收流式事件。

### 5.1 PanelState（建议枚举）

- `idle`：尚未开始（无 request 上下文）
- `streaming`：正在接收事件（允许 evidence 增量更新）
- `degraded`：仍在 streaming，但已出现 warning（降级提示已生效）
- `error_stable`：收到 `error` 事件（结构化错误），面板进入稳定错误态
- `final_stable`：收到 `final`，面板冻结（不再接收任何事件更新）

### 5.2 final 冻结与事件优先级（决策）

由于外部最佳实践资料抓取受限，本蓝图采用**契约优先**原则（以 `docs/contracts/api-and-events-draft.md` 的强约束为准）：

- **冻结规则（强制）**：收到 `type=final` 后，Context Panel 必须进入 `final_stable`，并拒绝后续任何事件对 UI 的影响。
- **错误优先（推荐）**：收到 `type=error` 后立即进入 `error_stable`（同时仍需等待/允许 Hook 处理 `final(status=error)` 以完成连接收尾），但 UI 内容以 `error` 为准，不再显示半成品“伪证据”。
- **warning 时间线（推荐）**：在 `streaming` 期间保留 warning 列表（按 `sequence`），并定义“当前有效降级原因”为最后一条 warning；进入 `final_stable` 后不再追加。

> 说明：该策略既满足契约的“final 必须最后一条事件”的验收点，也满足前端“可审计/可追溯”的降级说明需求。

## 6. Evidence 状态模型（Evidence 级）

Evidence 的权威字段来源：`web/schemas/evidence.ts`。

### 6.1 Evidence.validation 的 UI 语义（强制对齐 contracts）

- `verifiable`
  - UI：正常可验证态（绿/安全语义），允许展示“确定性”结论标签。
- `not_verifiable`
  - UI：不可验证态（灰/弱化），必须显示“不可验证/已降级”提示。
- `out_of_bounds`
  - UI：越界/命中 guardrail（高风险提示），必须阻止展示确定性结论（只允许展示“数据与来源”及风险原因）。
- `mismatch`
  - UI：证据冲突/不一致（冲突提示），必须阻止展示确定性结论，并建议用户核对口径/时间窗/来源。

### 6.2 Evidence 完整性（可追溯最低门槛）

- Evidence 只有在满足以下字段存在时才允许作为“可追溯证据条目”渲染：
  - `evidenceId`
  - `sourceSystem`
  - `sourceLocator`（object）
  - `timeRange.start/end`
- 若从事件/响应拿到的对象无法通过 `EvidenceSchema` 校验：
  - 不得渲染为 Evidence 条目；
  - 必须通过 `warning` 或“缺失证据”占位表达降级（UI 可中文，但 warning.message 必须英文）。

## 7. `evidence.update` 增量合并策略（核心）

### 7.1 输入模式（来自 contracts + Zod）

- `payload.mode`：`append | update | reference`
  - `append/update`：必须携带 `payload.evidences[]`
  - `reference`：必须携带 `payload.evidenceIds[]`（仅引用，不包含详情）

### 7.2 合并的幂等键

- 以 `evidenceId` 作为幂等键。
- 合并必须是**稳定、可重复、顺序无关（在 sequence 单调前提下）**：同一 evidenceId 多次出现不会产生重复条目。

### 7.3 不允许回退 / 不允许篡改来源（强制验收规则）

对同一 `evidenceId` 的后续 `update`：

- **来源不可篡改（强制）**：
  - `sourceSystem` 不允许变化
  - `sourceLocator` 不允许变化（语义等价需定义：默认采用“深度相等”；若后端存在字段排序差异，需在实现时采用稳定序列化/规范化后比较）
  - `timeRange.start/end` 不允许变化
  - 若检测到变化：
    - 将该 evidenceId 视为 `validation=mismatch` 的证据冲突（Evidence 级），并在 Panel 顶部展示 warning（code 推荐 `EVIDENCE_MISMATCH`）。

- **字段不可回退（强制）**：
  - `lineageVersion` 不允许从“有值”变为“缺失/空/null”
  - `dataQualityScore` 不允许从“有值”变为“缺失/空/null”
  - `toolCallId` 不允许从“有值”变为“缺失/空/null”（若业务允许 toolCallId 后补齐，则仅允许 null→string，不允许 string→null）
  - `redactions` 不允许从“有说明”回退为缺失

- **允许补齐（推荐）**：
  - 允许后续 update 补齐此前缺失的可选字段（如 `lineageVersion/dataQualityScore/toolCallId/redactions`）。

### 7.4 reference 模式的 UI 行为

- `mode=reference` 时，Context Panel 不应凭空生成 Evidence 详情。
- UI 行为必须可验收（二选一，建议先选 1）：
  1) 显示“仅引用”占位条目（展示 evidenceId，提示需通过证据检索接口拉取详情）；或
  2) 完全不新增条目，但在“证据计数/提示区”展示“收到 evidenceIds 引用数量”。

> 备注：当前任务 Non-Goals 不要求新增检索接口交互，但必须避免“看似有来源但不可映射”的引用。

## 8. `warning` 与 Evidence 状态的映射（按你的选择：混合策略）

你已确认采用 **混合（推荐）**：默认全局展示；若可归因则落到 Evidence 行。

### 8.1 Warning 的存储与展示

- 存储：按 `sequence` 追加到 `warningTimeline[]`（保留原始 `code/message/details?`，message 英文原样保留）。
- 展示：
  - Panel 顶部展示“当前有效 warning = timeline 最后一条”；
  - 同时提供“查看全部 warning”折叠面板（用于可追溯）。

### 8.2 Warning 归因规则（可验收）

若 `warning.payload.details` 中出现以下任一可识别字段，则视为“可归因”并在对应 Evidence 行显示二级标签：

- `evidenceId`
- `toolCallId`
- `timeRange`（需能与 Evidence.timeRange 匹配）

否则：按“全局 warning”处理。

### 8.3 Warning code 与 UI 文案映射（示例口径）

- `EVIDENCE_MISSING`
  - UI：证据缺失，已降级为仅展示数据与来源（禁止确定性结论）。
- `EVIDENCE_MISMATCH`
  - UI：证据冲突，无法给出确定性结论（提示检查口径/时间窗/来源）。
- `GUARDRAIL_BLOCKED`
  - UI：命中 guardrail（越界/红线），仅展示数据与来源与风险原因。

> 强制：warning.payload.message 必须英文；UI 展示可中文，但需要保留“复制英文 message + requestId”的入口用于排障。

## 9. 可追溯展开（Information Architecture）

### 9.1 展开层级（推荐）

- Level 0：Evidence 列表（摘要行）
  - `sourceSystem`
  - `timeRange`（起止）
  - `validation` 状态胶囊
  - （可选）`confidence`
  - （可选）`dataQualityScore` 以“质量”标签表达

- Level 1：Evidence 详情（展开）
  - `evidenceId`
  - `sourceSystem`
  - `sourceLocator`（结构化渲染；对可疑 key 进行红旗提示，禁止展示密钥/凭证类字段）
  - `timeRange.start/end`
  - `toolCallId`（若存在，提供“关联工具调用”锚点）
  - `lineageVersion`（若存在，计算类结论应强调）
  - `dataQualityScore`（若存在，显示评分与含义）
  - `redactions`（若存在，显示“已脱敏”与原因摘要，禁止原值）

### 9.2 脱敏与权限表达（R10.2 对齐）

- Evidence 含 `redactions`：必须展示“已脱敏”提示 + 策略摘要（如 policyId/fields）。
- 无权限：禁止提供“展开查看原始数据”的入口；仅允许显示脱敏后的 locator 摘要。

## 10. 与现有前端代码的差距（用于实现阶段对齐）

> 仅做差距识别，不做改造。

- `web/components/ContextPanel.tsx` 当前使用 `../types` 的 `Evidence`，字段形态与 `web/schemas/evidence.ts` 不一致（例如当前使用 `evidence.source/type/timestamp/id/details`，而契约字段为 `sourceSystem/sourceLocator/timeRange/...`）。
- 当前 Context Panel 更像“展示一条 evidence + raw log”，未体现：
  - Evidence 列表
  - 流式增量合并
  - warning 时间线
  - final 冻结
  - reference 模式
- `useChatSseStream` 已实现：
  - `SseEnvelopeSchema` 校验
  - `error` 后必须跟随 `final` 的契约校验
  - `evidence.update/warning/error/final` 分发回调

实现阶段需要把 Context Panel 的输入完全从“内部 types”迁移到“Zod 推导类型”。

## 11. 验收标准（可自动化）

### 11.1 契约与输入校验（必须）

- Context Panel 只消费：
  - Zod 校验通过的 `SseEnvelope` 分发结果
  - 或 Zod 校验通过的 REST 响应
- 任意契约违规：不得渲染为“可信证据”，必须进入可观测的降级/错误表达路径。

### 11.2 事件对齐（必须）

- `evidence.update`：多次出现时合并稳定、无重复、无字段丢失。
- `warning`：
  - 面板顶部可见当前有效 warning
  - 可查看 warning 全量时间线
  - 若 details 可归因，Evidence 行有二级标签
- `error`：
  - 不展示半成品伪证据
  - 保留 `requestId`（可复制）
- `final`：
  - `final` 后冻结，不再接收事件更新 UI

### 11.3 合并“不允许回退/篡改来源”（必须）

- 同一 `evidenceId`：`sourceSystem/sourceLocator/timeRange` 任一不一致 => `mismatch` + 全局 warning（`EVIDENCE_MISMATCH`）。
- `lineageVersion/dataQualityScore/toolCallId/redactions`：有值不得被后续更新回退为空。

## 12. 验证命令（按任务提示词）

- Unit：`npm -C web test`
- Smoke：
  - `npm -C web run build`
  - `.venv/bin/python backend/scripts/web_sse_e2e_smoke_test.py`

## 13. 已锁定口径（实现前不再摇摆）

- warning 的“可归因字段”采用**最小集合**：仅支持 `evidenceId/toolCallId/timeRange`。
  - 若 `warning.payload.details` 不包含以上任一字段：按全局（Panel 级）warning 展示。
- `sourceLocator` 的“等价性比较”采用**只增不改**策略：
  - 允许：后续 `evidence.update(mode=update)` 对同一 `evidenceId` 的 `sourceLocator` **新增** key（或对原先为 `null/undefined` 的 key 补齐值）。
  - 禁止：修改既有 key 的值、删除既有 key、将既有 key 从有值回退为空。
  - 若触发禁止项：该 evidenceId 进入 `validation=mismatch`，并触发全局 warning（推荐 `EVIDENCE_MISMATCH`）。
