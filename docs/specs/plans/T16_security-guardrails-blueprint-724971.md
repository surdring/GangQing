# Task 16 安全 Guardrails 执行蓝图（注入检测/输出安全/越权与写意图拦截/审计与证据/测试口径）

本计划定义 Task 16 在现有 GangQing 架构与契约下的“策略化拦截 + 审计留痕”闭环：注入检测（直接/间接）、输出安全校验、越权/写意图拦截、Evidence/Audit 记录 `ruleId` 与原因摘要，并补齐单元/冒烟/契约测试口径。

## 0. 约束与权威依据（不可违反）

- **只读默认（R5.1）**：不确定是否写操作 => 按只读处理；任何写操作仅允许进入 **L4 草案/审批/受控执行**链路。
- **错误同构（contracts 2.x + 6.x）**：REST 非 2xx 与 SSE `type=error` 事件 `payload` 必须是 `ErrorResponse(code/message/details?/retryable/requestId)`，且 **message 必须英文**。
- **Guardrail 强制映射**：
  - 越权/敏感查询 => `FORBIDDEN`
  - 写操作倾向/高风险指令/红线 => `GUARDRAIL_BLOCKED`
  - 物理边界/变化率越界 => `GUARDRAIL_BLOCKED` 或降级为“仅展示数据与来源”（R17.3）
- **Schema First**：后端 Pydantic；前端 Zod。
- **Audit & Evidence**：触发拦截/降级必须写审计 + 证据链，记录 `ruleId` 与原因摘要（禁止敏感原文）；审计可按 `requestId` 检索，包含 `tenantId/projectId/userId/role/eventType`。
- **Real Integration (No Skip)**：冒烟/集成必须连真实服务；配置缺失/依赖不可用 => 直接失败。

## 1. 现状基线（用于定位改动点）

### 1.1 现有门禁与拦截链路

- **意图识别**：`backend/gangqing/agent/intent.py::identify_intent` 输出 `IntentResult`（含 `hasWriteIntent`、`riskLevel`、`reasonCodes`），并写审计 `intent.classified`。
- **路由决策**：`backend/gangqing/agent/routing.py::route_intent`
  - `ACTION_EXECUTE` => `GUARDRAIL_BLOCKED`（只读默认）
  - 工具清单 RBAC 校验失败 => `FORBIDDEN` + 审计 `rbac.denied`
- **工具执行前门禁**：`backend/gangqing/tools/gate.py::assert_tool_call_allowed`
  - scope 缺失/跨域 => `AUTH_ERROR`
  - 写意图 => `GUARDRAIL_BLOCKED`
  - tool 不在 allowlist => `FORBIDDEN`

### 1.2 现有 SSE / Error / Evidence / Audit

- **后端 SSE（Pydantic）**：`backend/gangqing/schemas/sse.py`（`warning/error/final` 已存在，且 `error.payload` 为 `ErrorResponse`）。
- **前端 Zod**：`web/schemas/sseEnvelope.ts`、`web/schemas/errorResponse.ts`、`web/schemas/evidence.ts`。
- **审计落库**：`backend/gangqing/common/audit.py` + `backend/gangqing_db/audit_log.py`（落库前递归脱敏 `redact_sensitive` + masking policy）。
- **Evidence 降级**：`backend/gangqing/common/evidence_degradation.py` 能基于 `evidence.validation` 产出 `warning`。

### 1.3 Task16 的关键缺口

- **缺口 A**：注入检测（直接/间接）规则集、命中结构、审计事件类型。
- **缺口 B**：输出安全校验（系统提示词泄露/敏感信息泄露/恶意内容/过长输出）的统一校验点与失败策略。
- **缺口 C**：`ruleId` + `reasonSummary` + `hitLocation` 的最小可追溯字段集合（同时进入 SSE.details / Audit / Evidence）。
- **缺口 D**：单元 + 冒烟 + 契约测试矩阵。

## 2. 总体方案：三段式防线 + 统一裁决器（Policy Engine）

按 OWASP Prompt Injection（结构化分隔、least privilege、输出监控、审计监控）与仓库契约约束，将防护分为三段，每段产出统一 `GuardrailDecision`：

1) **Input Guardrail（用户输入）**：直接注入、越权敏感查询、写意图诱导。
2) **Context Guardrail（工具结果/检索片段）**：间接注入（将不可信内容当指令）、编码/混淆、外部内容指令化。
3) **Output Guardrail（最终输出）**：系统提示词泄露、敏感信息泄露、恶意内容、异常长度。

决策类型：`allow` / `warn_degrade` / `block_forbidden` / `block_guardrail`，并驱动 SSE（warning vs error+final）、审计与证据链记录。

## 3. 规则体系与 Rule ID 命名（稳定、可枚举、可审计）

### 3.1 规则 ID 命名空间（建议）

- `GUARDRAIL_INJ_*`：提示词注入（直接/间接）
- `GUARDRAIL_OUTPUT_*`：输出安全校验（提示词泄露/敏感信息）
- `GUARDRAIL_RBAC_*`：越权/敏感查询（映射 `FORBIDDEN`）
- `GUARDRAIL_WRITE_*`：写意图/绕过审批（映射 `GUARDRAIL_BLOCKED`）
- `GUARDRAIL_PHYS_*`：物理边界/变化率（映射 `GUARDRAIL_BLOCKED` 或 degrade）

### 3.2 Rule Catalog（规则目录）的落盘

- **文档枚举（验收/权威）**：在 `docs/contracts/api-and-events-draft.md` 增补 Guardrail Rules Catalog 章节（ruleId、类别、默认动作、错误码映射、审计事件类型）。
- **运行时配置（外部化）**：后端新增配置项（如 `GANGQING_GUARDRAIL_POLICY_JSON` 或 `GANGQING_GUARDRAIL_POLICY_PATH`），启动时用 Pydantic 校验并快速失败。

## 4. Schema First：需要新增/扩展的契约模型（仅定义，不写实现）

### 4.1 后端 Pydantic（建议新增 `backend/gangqing/schemas/guardrail.py`）

- `GuardrailHitLocation`：`input | tool_context | output`
- `GuardrailAction`：`allow | warn_degrade | block_forbidden | block_guardrail`
- `GuardrailHit`：`ruleId/category/hitLocation/reasonSummary/riskLevel/policyVersion?/evidenceId?`
- `GuardrailDecision`：`action/errorCode?/hits/retryable`

### 4.2 ErrorResponse.details 的 guardrail 约定

保持 `ErrorResponse` 顶层 5 字段不变，把 guardrail 信息放入 `details`：

- `details.ruleId`
- `details.reasonSummary`（英文；禁止敏感细节）
- `details.hitLocation`
- `details.stage`（如 `guardrail.input` / `guardrail.output` / `tool.gate`）

## 5. 策略化拦截：FORBIDDEN vs GUARDRAIL_BLOCKED

- **FORBIDDEN（403）**：RBAC capability 不足；敏感域读取权限不足。
- **GUARDRAIL_BLOCKED（409）**：写意图/绕过审批/注入导致试图改变系统规则/系统提示词提取/物理越界（按策略）。

## 6. SSE 输出规则（warning vs error + final）

- `block_*`：输出 `type=error`（payload=ErrorResponse）并紧随 `type=final(status=error)`。
- `warn_degrade`：输出 `type=warning`，继续输出降级回答 `message.delta`，最后 `final(status=success)`。

补充决策（定稿）：

- `warning.payload.code`：**复用稳定错误码**（例如 `EVIDENCE_MISSING`/`EVIDENCE_MISMATCH`/`UPSTREAM_TIMEOUT`/`GUARDRAIL_BLOCKED`），不引入 warning 专用枚举。
- `warning.payload.message`：必须英文（与 contracts 一致）。

## 7. Evidence 与审计留痕（ruleId + reasonSummary + requestId）

### 7.1 Evidence：以 `Detector` 作为安全事件证据来源

- `sourceSystem = "Detector"`
- `sourceLocator` 建议包含：`ruleId/hitLocation/category/reasonSummary/policyVersion`
- `timeRange`：事件发生时间点的短区间（保证 `end > start`）
- `validation`：注入/输出/写意图 => `not_verifiable`；物理越界 => `out_of_bounds`

### 7.2 Audit：新增事件类型（规划）

建议扩展 `backend/gangqing/common/audit_event_types.py`：

- `guardrail.hit`
- `output.blocked`（可选）

审计 `actionSummary` 最小字段集合：`ruleId/reasonSummary/hitLocation/category/decisionAction/policyVersion/inputDigest/toolName/toolCallId`。

补充决策（定稿）：

- `guardrail.hit`：作为**统一拦截/降级命中事件**，无论最终动作为 `block_*` 还是 `warn_degrade`，都必须写入（便于按 `requestId` 聚合检索与统计）。
- contracts 落盘：`guardrail.hit`（以及如采用 `output.blocked`）必须在 `docs/contracts/api-and-events-draft.md` 的 Audit Event 章节中作为权威枚举列出，并给出最小字段约束。

## 8. 改动/新增文件清单（规划）

### 8.1 后端

- **Schema**：`backend/gangqing/schemas/guardrail.py`；`backend/gangqing/common/settings.py` 增加 guardrail policy 配置项。
- **规则引擎模块（纯策略/可单测）**：
  - `backend/gangqing/common/guardrail/input_guardrail.py`
  - `backend/gangqing/common/guardrail/context_guardrail.py`
  - `backend/gangqing/common/guardrail/output_guardrail.py`
  - `backend/gangqing/common/guardrail/decision.py`
- **接入点**：`backend/gangqing/api/chat.py`
  - input：在 intent 识别前/后追加 input guardrail
  - tool_context：在 `tool.result` / evidence.update 后追加 context guardrail
  - output：在输出 `message.delta` 前（或组装 final answer 前）追加 output guardrail
- **审计**：`backend/gangqing/common/audit_event_types.py` 增加事件；`backend/gangqing/common/audit.py` 复用现有写入。

### 8.2 前端

- **Schema**：可选新增 `web/schemas/guardrail.ts`（用于解析 `warning.details` 的 guardrail 字段并驱动 UI 提示）。
- **UI**：在 ChatInterface 处理 `warning` 事件（当前未处理）并展示“降级/拦截原因摘要”。

## 9. 测试口径（单元 + 冒烟 + 契约）

### 9.1 单元测试（pytest）

必须覆盖：
- 直接注入样本 => `GUARDRAIL_BLOCKED`（含 ruleId/reasonSummary）
- 间接注入（tool_context）=> `GUARDRAIL_BLOCKED` 或 `warning+degrade`
- 输出泄露特征 => `GUARDRAIL_BLOCKED`
- 越权敏感查询 => `FORBIDDEN`
- 审计落库：`guardrail.hit` / `rbac.denied` 可按 requestId 查询，且不含敏感原文

### 9.2 冒烟测试（真实服务）

- 复用：`backend/scripts/intent_routing_smoke_test.py`
- 复用：`backend/scripts/rbac_and_masking_smoke_test.py`
- 新增（按 `docs/tasks.md` 规划）：`backend/scripts/security_guardrail_smoke_test.py`
  - 启动服务后，发起注入/写意图/越权请求
  - 断言 SSE 序列：`meta -> ... -> error -> final` 或 `meta -> warning -> ... -> final`
  - 再调用审计检索接口（或直接查库）按 requestId 验证 guardrail 事件存在

### 9.3 契约测试

- 后端：对新引入的 `warning.details` / `error.details` 字段做 Pydantic 校验
- 前端：扩展 `web/tests/contractSchemas.test.ts`，新增 `warning` case（含 ruleId/reasonSummary/hitLocation）与 `error` case（含 ruleId）。

## 10. 待你确认的决策点（在实现阶段前必须定稿）


本任务决策已定稿（后续实现与测试以此为准）：

- **warning.code 策略**：复用稳定错误码（不新增 warning 专用枚举）。
- **warn_degrade vs block（平衡：默认降级）**：
  - 注入尝试（直接/间接）与输出安全校验失败（提示词泄露/敏感信息泄露/绕过规则/写意图诱导）：默认 `block_guardrail`（`GUARDRAIL_BLOCKED`）
  - 越权/敏感查询：默认 `block_forbidden`（`FORBIDDEN`）
  - 物理边界/变化率越界：默认 `warn_degrade`（输出 `warning(code=GUARDRAIL_BLOCKED)` + 仅展示数据与来源，不给确定性结论）；只有命中“红线规则/强制禁止”的子规则时才 `block_guardrail`
- **contracts 扩展**：必须在 `docs/contracts/api-and-events-draft.md` 中落盘：
  - Guardrail Rules Catalog（ruleId -> category/defaultAction/errorCode/auditEventType）
  - Audit Event 类型枚举包含 `guardrail.hit`（必需）与其 `actionSummary` 最小字段约束
