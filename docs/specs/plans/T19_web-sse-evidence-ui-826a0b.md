# T19 前端三栏式布局 + SSE 流式渲染 + 证据链可视化（实现蓝图 / Prompt）
本蓝图基于现有 `web/` 原型做增量改造：移除硬编码 mock 数据流，改为真实后端 SSE 事件驱动渲染，并用 Zod 对 SSE 事件/配置/对外 I/O 做运行时校验，最终满足三栏信息架构与 Evidence-First 的 UI 约束。

## 0. 权威契约与裁决（必须写进实现）
### 0.1 权威来源优先级（强制）
1) `docs/contracts/api-and-events-draft.md`
2) `docs/design.md`
3) `docs/requirements.md`

实现中必须在 README/PR/提交说明里显式声明：事件解析与 UI 行为以以上文档为准。

### 0.2 已发现的契约冲突与裁决
- **[冲突点] SSE Envelope 的结构**
  - `docs/contracts/api-and-events-draft.md`：SSE envelope **扁平字段**（不得嵌套 `envelope` 对象），字段为顶层 `type/timestamp/requestId/tenantId/projectId/sessionId?/sequence/payload`。
  - `docs/design.md` 3.5.1：描述为顶层 `type + envelope + payload`（存在嵌套 `envelope` 的表述）。
  - **[裁决]** 以 `docs/contracts/api-and-events-draft.md` 为准（优先级更高，且当前 `web/schemas/sseEnvelope.ts` 已实现扁平结构）。

- **[冲突点] SSE 接口形态（直连流 vs 其他变体）**
  - 本仓库契约草案（contracts）给出 `POST /api/v1/chat/stream` 直接返回 `text/event-stream`。
  - **[裁决]** 本任务前端实现蓝图以直连流为唯一实现路径：`POST /api/v1/chat/stream`。

## 1) 现状盘点（基于 `web/` 原型）
### 1.1 已存在的关键资产（可复用）
- `web/schemas/sseEnvelope.ts`
  - 已实现契约要求的扁平 envelope。
  - 已覆盖：`meta/progress/tool.call/tool.result/message.delta/evidence.update/warning/error/final`（其中 `message.delta` 当前缺失，需要补齐）。
- `web/schemas/errorResponse.ts`、`web/schemas/evidence.ts`、`web/schemas/evidenceChain.ts`
  - 基本满足 Error/Evidence/EvidenceChain 的 Zod 单一事实源要求。
- `web/tests/contractSchemas.test.ts`
  - 已对 schema 做了单测（但尚未覆盖 `message.delta`、`sequence` 一致性、`tenantId/projectId` 缺失的契约错误路径）。

### 1.2 必须移除/改造的硬编码 mock（任务强制）
- `web/constants.tsx`
  - 存在 `MOCK_WATERFALL_DATA`/`MOCK_SPECTRUM_DATA`/`SAMPLE_EVIDENCE`；这些不得再作为主渲染数据源。
- `web/components/ChatInterface.tsx`
  - `tenantId/projectId/apiBaseUrl` 带默认值（`t1/p1/http://localhost:8000`），属于“配置硬编码风险”。必须改为**配置加载 + Zod 校验 + 缺失快速失败**。
  - SSE 当前实现通过 `fetch` 读流，并手写解析 `\n\n` + `data:`。需要抽离为可复用的 SSE 客户端模块，并纳入状态机/重连/取消。
- `web/components/ContextPanel.tsx`
  - 目前展示包含 `> FETCH FROM ...` 等演示性 raw log 字符串，不符合 Evidence-First 的“可追溯证据字段展示 + 脱敏标识”要求，需要改为基于 `EvidenceChain` 的真实字段渲染（仍可保留 UI 风格，但内容必须来自契约字段）。

## 2) 目标信息架构：三栏布局（Task 19.1）
### 2.1 三栏结构（与 requirements R13.1 / design 2.2.1 对齐）
- **左栏（Navigation）**：会话列表/场景/功能入口（可沿用现有 `Sidebar`）。
- **中栏（Chat）**：流式消息区 + 输入区（沿用 `ChatInterface`/`ChatMessage`，但数据源改为 SSE 事件驱动）。
- **右栏（Context Panel）**：证据链可视化（沿用 `ContextPanel`，但改为 EvidenceChain + 增量 evidence.update 合并）。

### 2.2 交互联动规则（必须实现）
- Chat 中的 Trust Pill（数值胶囊）点击：
  - 右栏定位到对应 claim/evidence 详情；若 evidence 仅 reference（`evidence.update.mode=reference`），触发拉取 evidence chain 或 evidence detail（按后端实际端点）并渲染。
- 右栏支持“本次请求的全量证据链视图” + “选中某个 evidence/claim 的详情视图”。

## 3) SSE 客户端：事件解析、状态机、取消与重连（Task 19.2 + 19.4）
### 3.1 事件 envelope（前端假设，强制）
以 `docs/contracts/api-and-events-draft.md` 为准：
- 顶层必含：`type/timestamp/requestId/tenantId/projectId/sequence/payload`，可选 `sessionId`。
- **强制校验**：`tenantId/projectId` 缺失或空 => 视为 `CONTRACT_VIOLATION`（客户端侧），进入可观测错误路径与 UI 降级提示。

### 3.2 最小 UI 状态机（强制）
状态：
- `idle`
- `connecting`
- `streaming`
- `error`
- `done`

状态转换（建议实现为 reducer）：
- `idle -> connecting`：用户点击发送 / 自动重试开始。
- `connecting -> streaming`：收到首个有效事件（必须是 `meta`；否则契约错误）。
- `streaming -> done`：收到 `final`。
- `connecting|streaming -> error`：
  - 收到 `type=error`（payload 为 ErrorResponse），或
  - Zod 校验失败 / JSON 解析失败 / 网络断开且超过重试上限。
- `error -> connecting`：用户点击“重试”，或 retryable=true 自动重连策略触发。

UI 可感知（必须）：
- 顶部或输入框附近显示：连接中/生成中/已完成/已断开/重连中/重连失败。

### 3.3 `sequence` 一致性检查与 UI 降级（强制）
- 维护 `lastSequence`（每条事件通过 Zod 后再检查）。
- 若出现：
  - 非递增（`sequence <= lastSequence`）
  - 跳号（`sequence > lastSequence + 1`）
- 必须：
  - 进入可观测路径（console.error + 前端错误上报接口/钩子，详见 6 节）
  - UI 显示“数据可能不完整”的降级提示（不可静默吞掉）。

### 3.4 取消/停止（Cancel Propagation，强制）
**最佳实践裁决：必须有显式取消端点**，原因：
- SSE 是单向，单靠断开连接不一定能让服务端及时停止推理/工具调用（且不利于审计与可测性）。
- `docs/contracts/api-and-events-draft.md` 已定义 `POST /api/v1/chat/stream/cancel`（body: `{requestId}`）。

前端实现要求：
- 点击“停止生成”/离开页面/unmount：
  - 本地：停止追加渲染，冻结本次 assistant message；状态机进入 `done` 或 `error`（建议单独 `cancelled` 子状态，但最低集可映射为 `done` 并标注取消原因）。
  - 远端：调用取消端点（携带 `Authorization` + `X-Tenant-Id/X-Project-Id/X-Request-Id`），并在可观测日志记录取消结果。
- 若后端声明 `meta.payload.capabilities.cancellationSupported=false`：
  - UI 仍允许用户“停止本地渲染”，但必须提示“server-side cancellation not supported”。

### 3.5 断线重连策略（最佳实践裁决）
参考 WHATWG SSE 与 MDN：
- SSE 原生 `EventSource` 支持自动重连 + `Last-Event-ID`；但本项目当前用 `fetch + ReadableStream`，需要自行实现重连。

裁决与要求：
- 使用**指数退避**重连：`baseDelayMs`、`maxDelayMs`、`maxAttempts` 全部由配置驱动（Zod 校验），禁止魔法数字散落。
- 仅在“网络断开/5xx/`retryable=true` 的 error”时自动重连。
- 重连恢复语义（直连流的最小可落地策略）：
  - 重连后**重新发起一次新的** `POST /api/v1/chat/stream`（新的 `requestId`），并在 UI 明确标记“已重试，结果可能不同”。
  - 不做同一 `requestId` 的续传假设；若未来后端补齐 `Last-Event-ID/sequence` 续传能力，需先更新 `docs/contracts/api-and-events-draft.md` 并再扩展前端。
- 必须在 UI 可感知展示“重连中/第 N 次/等待 X 秒”。

## 4) Evidence UI：Context Panel + Trust Pill（Task 19.3）
### 4.1 Evidence 增量合并规则（强制）
按 contracts 的 `evidence.update.payload.mode`：
- `append`：新增 evidence；以 `evidenceId` 为幂等键写入本地 evidence store。
- `update`：更新 evidence；必须遵守“字段不可回退/不可篡改来源”的前端合并策略：
  - 若新 evidence 缺字段不得覆盖旧字段（避免回退）。
  - `sourceSystem/sourceLocator/timeRange` 等来源字段若变化，视为高风险：必须触发 UI 警示（潜在 mismatch）并写入可观测日志。
- `reference`：只记录 `evidenceIds`；Context Panel 在需要展示详情时通过 REST 拉取（端点以实际后端为准，但 payload/响应必须再走 Zod）。

### 4.2 Trust Pill 渲染规则（强制写入实现）
- 仅对“可追溯数值”渲染 Trust Pill：
  - 至少满足：存在 claim（`claimType=number`）且 `evidenceRefs.length>=1`；并能在 evidence store 中解析到对应 `Evidence`（包含 `timeRange`）。
- 缺失 Evidence 或 `validation=not_verifiable`：
  - Trust Pill 必须降级样式（灰态/虚线/提示文案），并引导查看缺失原因（来自 `warning` 事件或 EvidenceChain `warnings`）。
- `validation=out_of_bounds` 或 `validation=mismatch`：
  - Trust Pill 必须明显风险态（颜色/图标），并在 Context Panel 展示冲突来源（引用 evidence 的 `sourceSystem/sourceLocator/timeRange`）。
  - 禁止用确定性解释掩盖冲突（必须用“冲突/越界”的事实表述）。

### 4.3 脱敏（前端展示规则，强制）
- Evidence 默认展示脱敏后的字段。
- 若 evidence 含 `redactions`：
  - Context Panel 必须显示“已脱敏”标识 + 原因摘要（不展示原值）。

## 5) Schema 清单（Zod 单一事实源）
### 5.1 必须新增/修改的 Zod schema
- `web/schemas/sseEnvelope.ts`
  - **必须补齐** `message.delta` envelope：`payload.delta: string`。
  - 建议新增：对 `type` 进行更严格枚举（当前 base 是 `z.string()`，但最终通过 discriminatedUnion 已限定；需要确保包含 `message.delta`）。
- `web/schemas/config.ts`（新增）
  - `VITE_API_BASE_URL`
  - `VITE_TENANT_ID` / `VITE_PROJECT_ID`（若从登录态/路由获得，则此处可不需要，但必须有唯一来源）
  - `VITE_SSE_RECONNECT_*`（baseDelay/maxDelay/maxAttempts 等）
  - 规则：缺失关键配置必须抛出英文错误（便于日志检索）。
- `web/schemas/errorResponse.ts`
  - 保持 5 字段严格模型（已满足 contracts 2.1）。

### 5.2 运行时校验策略（必须）
- SSE 每条 `data:` JSON：
  - `JSON.parse` -> `SseEnvelopeSchema.safeParse`。
  - parse 失败：
    - 记录可观测错误（含 requestId/sessionId/sequence/原始 type 若可取）
    - 状态机进入 `error`
    - UI 显示契约错误降级提示（不要静默）。

## 6) 可观测性（前端最小字段集 + 上报策略）
### 6.1 最小日志字段（强制）
每条 SSE 事件处理都至少记录：
- `requestId`
- `sessionId`（若有）
- `tenantId`
- `projectId`
- `sequence`
- `eventType`（`type`）
- `clientState`（idle/connecting/streaming/error/done）

### 6.2 错误上报策略（不含敏感信息）
- 分为：
  - **契约错误**：`SSE_CONTRACT_VIOLATION`（本地 code）
  - **解析错误**：`SSE_INVALID_JSON`/`SSE_FRAME_PARSE_ERROR`
  - **后端结构化错误**：来自 `type=error` payload（ErrorResponse）
- 上报内容必须脱敏：不得包含 token、cookie、原始用户输入全文、原始 tool args。

## 7) 文件级改动清单（按路径：改什么 / 为什么 / 对齐条款）
> 注意：本清单是“实现者要改的文件”，本任务输出不包含实现代码。

### 7.1 布局与组件结构
- `web/App.tsx`
  - **改什么**：将“演示用途的 scenario 顶栏”改为可插拔（不作为数据源），并为三栏布局预留稳定容器；右栏 Context Panel 不应使用绝对定位遮挡主布局（小屏可改为抽屉）。
  - **为什么**：满足 R13.1 三栏式布局与响应式适配。
  - **对齐**：requirements R13.1；design 2.2.1。

- `web/components/ChatInterface.tsx`
  - **改什么**：
    - 移除直接在组件内完成 SSE 解析/状态维护的实现，抽离为 `useGangQingChat`（见 design 2.10.1）。
    - 移除 `tenantId/projectId/apiBaseUrl` 的硬编码默认值：改为 config loader（Zod）。
    - 事件驱动渲染：`progress/message.delta/evidence.update/warning/error/final` 分别更新不同 UI 区域。
    - 引入“停止生成/重试”入口，驱动状态机与取消端点。
  - **为什么**：契约校验、状态机、重连/取消必须集中管理；组件只做渲染。
  - **对齐**：design 2.10.1；contracts 6.1.*；requirements R13.2/R6.1/R6.3。

- `web/components/ContextPanel.tsx`
  - **改什么**：
    - 展示改为以 `EvidenceChain`/`Evidence` 的真实字段渲染（sourceSystem/sourceLocator/timeRange/validation/redactions）。
    - 增加“证据缺失/不可验证/冲突/越界”的 UI 降级表达。
  - **为什么**：Evidence-First 与 Trust Pill 可展开到 Evidence。
  - **对齐**：requirements R13.3/R2.2；contracts 第3章 Evidence；design 2.10.2。

- `web/components/TrustPill.tsx`（已存在但未读；实现者需按规则改造）
  - **改什么**：根据 `validation`/是否可追溯 evidence 渲染风险态/降级态。
  - **对齐**：contracts 3.1/3.1.2；requirements R13.3。

### 7.2 SSE 客户端与配置
- `web/hooks/useGangQingChat.ts`（新增）
  - **改什么**：实现连接管理 + 事件解析分发 + 状态机 + 取消 + 重连策略。
  - **对齐**：design 2.10.1；contracts 2.1.0.* / 6.1.*。

- `web/lib/sse/parse.ts`（新增，建议）
  - **改什么**：封装 frame parsing（`\n\n` 分帧、`data:` 提取、单行 JSON 约束）。
  - **对齐**：contracts 6.1.1（data 单行 JSON）。

- `web/schemas/config.ts`（新增） + `web/config/loadConfig.ts`（新增）
  - **改什么**：统一读取 `import.meta.env` 并用 Zod 校验；缺失快速失败。
  - **对齐**：全局“配置外部化 + Zod 校验”规则；design 2.9。

### 7.3 Schema 与测试
- `web/schemas/sseEnvelope.ts`
  - **改什么**：补齐 `message.delta`。
  - **对齐**：contracts 6.1.3/6.1.4。

- `web/tests/contractSchemas.test.ts`
  - **改什么**：新增/补齐单元测试断言：
    - `message.delta` 正常解析
    - `tenantId/projectId` 缺失 => parse 失败（契约错误）
    - `evidence.update` mode 约束（已有 superRefine，需覆盖 update/reference 的边界）
  - **对齐**：Schema 单一事实源 + 运行时校验。

### 7.4 移除 mock 数据流
- `web/constants.tsx`
  - **改什么**：mock 数据不得作为聊天/证据主数据源；若必须保留演示场景，需隔离到纯 demo 页面且不影响任务19验收路径。
  - **对齐**：任务强制“移除硬编码 mock 数据流”。

## 8) 验证策略（必须可自动化）
### 8.1 Unit（`npm -C web test`）
覆盖链路（不得 skip）：
- Zod schema：ErrorResponse/Evidence/EvidenceChain/SseEnvelope（含 `message.delta`）。
- SSE 解析器：
  - 单帧/多帧/跨 chunk buffer
  - data 非 JSON -> 失败
- `sequence` 检测：
  - 非递增/跳号 -> 触发降级标志（可通过 reducer 输出状态断言）。

### 8.2 Smoke（`npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`）
**当前 `backend/scripts/web_sse_e2e_smoke_test.py` 不存在，必须补齐（实现任务时写代码；本蓝图只定义要求）。**

脚本最小断言点（必须连接真实后端 SSE，禁止 mock server）：
- 建立 SSE 连接成功（HTTP 200 + `text/event-stream`）。
- 能收到最小事件序列：
  - `meta`（首事件）
  - 至少 1 条 `message.delta`
  - `final`
- 若后端提供：能收到并解析至少 1 条 `evidence.update`（可作为增强断言）。
- 异常路径：触发 1 个可控错误（例如缺 tenant/project header）并断言：
  - 收到 `type=error` 且 payload 可被 `ErrorResponseSchema` 解析
  - 含英文 `message`、`requestId`、`retryable`

## 9) 需要实现者确认/补齐的后端契约点（直连流假设下）
- evidence chain 拉取端点：当前前端调用 `GET /api/v1/evidence/chains/{requestId}`（需与后端实际对齐并纳入 Zod 校验）。
- 取消端点：以 contracts 6.1.6 `POST /api/v1/chat/stream/cancel` 为准；若后端不同，必须更新 contracts 或提供兼容层。
