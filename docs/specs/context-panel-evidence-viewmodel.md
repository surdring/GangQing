---
description: Context Panel EvidenceViewModel 状态机/渲染规则与证据合并一致性校验（T47.1）
---

# 1. 目的与范围

本文档用于子任务 **T47.1 - Context Panel：证据缺失/不可验证/降级态 UI** 的落地说明，定义：

- EvidenceViewModel 的 **状态机**（初始/流式/稳定）与冻结规则
- `warning`/`error`/`final` 到 UI 的映射原则
- `evidence.update` 的合并与一致性校验规则（**不可回退/不可篡改来源**）

权威契约与字段名以以下文档与 schema 为准：

- `docs/requirements.md`
- `docs/design.md`
- `docs/contracts/api-and-events-draft.md`
- `web/schemas/evidence.ts`
- `web/schemas/sseEnvelope.ts`
- `web/schemas/errorResponse.ts`

# 2. EvidenceViewModel：数据模型（前端 Zod 单一事实源）

实现文件：`web/schemas/evidenceViewModel.ts`

## 2.1 视图模型字段（摘要）

- `requestId/tenantId/projectId/sessionId?`
- `status`：
  - `empty`：尚未接收到任何证据/告警
  - `streaming`：流式接收中（允许增量合并）
  - `stable`：稳定态（发生 `error` 或 `final`）
- `isFrozen`：是否冻结（**收到 `final` 后必须为 true**）
- `lastSequence/lastTimestamp`：最后处理事件的 envelope 元信息（用于展示与审计定位）
- `evidencesById`：以 `evidenceId` 为幂等键的 Evidence 字典（Evidence 结构以 `web/schemas/evidence.ts` 为准）
- `evidenceOrder`：UI 展示顺序（当前实现为按 evidenceId 排序，确保稳定）
- `warnings`：warning 时间线（按 sequence 追加）
- `error`：结构化错误（`ErrorResponse`）
- `finalStatus`：`success | error | cancelled`

# 3. 状态机与冻结规则（Panel 级）

## 3.1 状态机

- 初始：`empty`
- 收到以下任一事件后进入 `streaming`：
  - `warning`
  - `evidence.update`
- 收到 `error`：
  - `status -> stable`
  - `error` 字段写入
  - **允许**后续 `final(status=error)` 到达以完成连接收尾，但 UI 内容以 `error` 为准
- 收到 `final`：
  - `status -> stable`
  - `finalStatus` 写入
  - `isFrozen -> true`

## 3.2 冻结规则（强制）

- **强制**：收到 `type=final` 后，EvidenceViewModel 必须冻结；冻结后：
  - 忽略任何后续 `warning/evidence.update/error` 对 UI 的影响
  - 目的：避免“闪烁/回退/篡改来源”

# 4. 渲染规则（Context Panel）

实现文件：`web/components/ContextPanel.tsx`

## 4.1 初始态（无证据）

- 当 `evidence` 为空：展示“证据链/点击 Trust Pill”的引导
- 若同时存在 `evidenceViewModel`（例如 streaming 期间但尚未选择某条 evidence）：
  - 顶部展示 `status/seq`（可观测性）
  - 若存在 `error`：展示结构化错误摘要（包含 `code/message/requestId`）
  - 若存在 `warnings`：展示最近 N 条 warning（保留 `code/message`）

## 4.2 流式增量态（多次 evidence.update）

- `evidenceViewModel.status=streaming` 时：
  - 顶部显示 `status=streaming seq=...`
  - warnings/error 区块可随事件更新

## 4.3 warning 到 UI 的映射

- `warnings[]` 作为时间线保存与展示（当前 UI 展示最近 5 条）
- warning.message **必须英文**（契约强制），UI 允许中文解释，但不得替换或伪造 message

## 4.4 error/final 后的稳定态

- `error` 事件：展示错误块（`code/message/requestId`），防止展示“半成品伪证据”
- `final` 后冻结：UI 只展示冻结时刻的状态

## 4.5 不可验证/降级态表达（强制）

- 当 `validation != verifiable` 时：
  - 显示对应的提示文案（i18n 已有 hint）
  - Raw Details 区域使用 `UNVERIFIABLE_EVIDENCE` 前缀，避免伪装成“确定性抓取日志”

# 5. 证据合并与一致性校验规则（不可回退/不可篡改来源）

实现文件：`web/schemas/evidenceViewModel.ts`（契约级 evidence）与 `web/components/ChatInterface.tsx`（UI trust pill）

## 5.1 幂等键

- 以 `evidenceId` 作为唯一幂等键

## 5.2 来源不可篡改（强制）

对同一 `evidenceId` 的后续更新：

- `sourceSystem/sourceLocator/timeRange` 必须保持语义一致
- 若检测到不一致：
  - Evidence 强制降级为 `validation=mismatch`
  - 追加 warning：
    - `code=EVIDENCE_MISMATCH`
    - `message='Evidence invariant source fields changed for the same evidenceId'`

## 5.3 字段不可回退（强制）

对同一 `evidenceId` 的后续更新：

- `toolCallId/lineageVersion/dataQualityScore/redactions`：
  - 允许缺失 -> 补齐
  - **不允许**有值 -> 缺失（合并时保持旧值）

## 5.4 Trust Pill 合并规则（UI 层补强）

- `source/type` 作为 UI 不可变字段：
  - 若变更：冻结为旧值，并将 `validation` 设为 `mismatch`
  - 同时输出 console warning 便于联调定位

# 6. 验证（已执行）

- Unit：`npm -C web test`
- Build：`npm -C web run build`
- Smoke：`.venv/bin/python backend/scripts/web_sse_e2e_smoke_test.py`
