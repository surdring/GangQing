---
trigger: always_on
---
# GangQing 全局编码规范

本文档为 GangQing（钢擎）项目的全局编码规范，适用于前端（React + TypeScript）、后端（FastAPI + Python）、AI 编排与工具链（LangChain/LangGraph）、数据层与基础设施相关代码。


## 0. 适用范围与优先级

- **强制（MUST）**：带“强制/MUST”的条目必须遵守。
- **推荐（SHOULD）**：默认遵守；若不遵守需在 PR/评审中给出理由。
- **允许（MAY）**：可选项。

发生冲突时优先级：

1. **安全与合规要求**（RBAC、审计、脱敏、红线、只读默认）
2. **契约与证据链一致性**（Schema 单一事实源、可追溯）
3. **可观测性与可运维性**（日志/指标/追踪）
4. **语言与框架风格规范**（TS/Python 等）

## 1. 通用原则（General Principles）

### 1.1 命名与语义

- **变量名**：名词，描述内容（例：`userProfile`、`evidenceChain`）。
- **函数名**：动词/动词短语，描述动作（例：`buildEvidenceChain`、`checkPermission`）。
- **布尔值**：使用 `is/has/can/should` 前缀。
- **避免缩写**：除通用缩写（`ID/URL/API/RBAC/SSE` 等）。

### 1.2 注释与文档

- **Doc 注释/说明**：业务逻辑说明优先中文；必要时补充英文术语。
- **行内注释**：仅用于解释“为什么这么做”，避免“重复代码表达”。
- **TODO/FIXME**：使用英文，便于全局搜索。

### 1.3 错误处理（强制）

- **错误消息（message）必须为英文**，便于日志检索与自动分析。
- **对外接口必须返回结构化错误模型**，至少包含：

  - `code`：稳定错误码（例：`VALIDATION_ERROR`/`AUTH_ERROR`/`UPSTREAM_TIMEOUT`/`CONTRACT_VIOLATION`/`GUARDRAIL_BLOCKED`）
  - `message`：英文可读描述
  - `details?`：结构化上下文（禁止放敏感信息）
  - `retryable`：是否可重试
  - `requestId`：链路追踪 ID

- **捕获处补充上下文**：如设备统一 ID、批次号、工具名、失败阶段 `stepId`。

### 1.4 契约与 Schema（强制）

- **单一事实源**：所有对外输入/输出/事件/工具参数/证据链结构必须有 Schema。
- **前端/TypeScript**：对外契约使用 **Zod** 作为单一事实源，类型从 schema 推导（`z.infer`）。
- **后端/Python**：对外契约使用 **Pydantic** 作为单一事实源（请求/响应模型、工具参数模型、Evidence 模型）。
- **边界校验**：

  - API 入参必须在 handler 层完成校验后再进入业务逻辑。
  - 对外响应（尤其 streaming/events/evidence）在输出前必须通过 schema 断言/序列化校验。

### 1.5 可观测性与上下文贯穿（强制）

- 统一 `RequestContext`：至少包含 `requestId`，并预留 `tenantId`、`projectId`（若启用多租户/项目隔离）。
- 贯穿范围：HTTP 入站 → Agent 编排 → 工具调用 → 日志/指标/审计 → 对外响应。
- 结构化日志字段至少包含：`requestId`，并在可用时包含 `sessionId`/`taskId`/`stepId`/`toolName`。

### 1.6 提交规范（Git）

- 使用 Conventional Commits：`feat/fix/docs/refactor/test/chore`。
- 一个 PR 尽量只解决一个主题问题；跨模块改动需要明确说明风险与回滚点。

### 1.7 隔离与权限上下文（强制）

- 若启用多租户/项目隔离：所有数据读写必须默认按 `tenantId/projectId` 过滤。
- 检测到跨隔离访问：返回 `AUTH_ERROR`，并写入审计。

### 1.8 流式与事件协议（强制）

- 若采用 SSE/WebSocket 流式：

  - 必须能被前端分段渲染（阶段/步骤/工具调用/证据链生成）。
  - 流中错误必须是可解析结构化错误（`AppError` 等价模型）。
  - 客户端取消必须向下传播并取消底层模型/工具调用。

## 2. 仓库结构与模块边界（推荐）

> 以“可替换/可测试/可审计”为目标，尽量把框架代码与业务核心隔离。

- **前端**：`web/`（React + Vite + TS）
- **后端**：`backend/`（FastAPI）
- **AI/Agent**：`backend/gangqing/agent/`（LangGraph 编排、意图识别、证据链）
- **工具链**：`backend/gangqing/tools/`（ERP/MES/DCS/EAM 等）
- **数据/语义层**：`backend/gangqing/semantic/`（实体映射、事件模型、指标口径）
- **测试**：`tests/`（单元/集成/契约/Golden Dataset）
- **文档**：`docs/`（PRD/TDD/运维/规范）

说明：若当前仓库结构与上述不一致，以“新增代码遵守、存量逐步迁移”为策略，不强制一次性重构。

## 3. TypeScript / React（前端）规范

### 3.1 类型与契约

- 禁止隐式 `any`；未知类型用 `unknown` + 类型守卫。
- API 输入/输出、Streaming 事件、Evidence 展示数据必须有 Zod schema。

### 3.2 组件与状态

- 组件职责单一：展示组件与数据获取/状态管理组件分离。
- 对话与流式：必须处理 `loading/error/cancel/retry/timeout` 全链路状态。
- 证据面板（ContextPanel）：

  - 只展示可追溯证据；禁止展示“看似有来源但不可映射”的引用。
  - 必须有“证据缺失/不可验证/降级模式”的 UI 表达。

### 3.3 错误与日志

- 前端错误提示可中文，但发送到后端的错误对象/日志字段应包含英文 `code/message`。
- 任何会影响审计或证据链的操作都应带 `requestId/sessionId`。

### 3.4 样式

- Tailwind 使用原则：

  - 优先组件化复用，避免同类 UI 大量重复 class。
  - 颜色、间距、字体尽量沉淀为 design tokens（与 PRD 设计系统一致）。

## 4. Python / FastAPI（后端）规范

### 4.1 工程与风格

- Python 版本以项目实际为准（TDD 期望 3.11+）。
- 格式化：Black；导入：isort；类型检查：mypy（若启用）；Lint：Ruff（推荐）或 Flake8。

### 4.2 Pydantic 模型（强制）

- 所有 API request/response、工具参数、Evidence、审计事件必须定义为 Pydantic 模型。
- 模型字段命名使用 `snake_case`（对外 JSON 可按项目策略转换）。

### 4.3 错误模型（强制）

- 对外统一错误响应：稳定 `code` + 英文 `message` + `requestId`。
- 捕获上游系统错误（ERP/MES/DCS）必须映射为 `UPSTREAM_*` 类错误码，并标注 `retryable`。

### 4.4 结构化日志与审计（强制）

- 日志使用结构化 JSON（例如 `structlog`）。
- 审计日志必须覆盖：

  - 用户查询（query）
  - 工具调用（tool_call，参数摘要必须脱敏）
  - 审批动作（approval）
  - 写操作（write_operation）

## 5. Agent / 工具链 / 证据链（项目强制约束）

### 5.1 只读默认（Read-Only Default）（强制）

- 未显式授权与审批通过前，系统不得执行任何写操作。
- 写操作必须经过：草案 → 审批/多签 → 受控执行 → 回滚点记录 → 审计。

### 5.2 证据链（Evidence）

- 任何数值型结论必须能映射到：

  - 数据源（ERP/MES/DCS/EAM/文档）
  - 时间范围
  - 口径版本（`lineage_version`）
  - 数据质量评分（如有）

- 禁止伪造 citation/evidence id。

### 5.3 工具实现规范（强制）

- 工具必须：参数校验、超时、重试策略（按工具定义）、脱敏、返回证据对象。
- 工具必须输出可观测字段：`toolName`、耗时、状态、错误码。

### 5.4 幻觉与物理约束

- 关键数值输出必须经过一致性校验；不可校验则降级为“展示数据与来源”。
- 物理边界/变化率越界必须触发 guardrail，并写入证据链与审计。

## 6. 安全规范（强制）

- RBAC：所有接口/工具必须做权限检查。
- 数据脱敏：财务数据/工艺参数/敏感配方必须按角色脱敏。
- Kill Switch：必须可一键熔断写操作，并可审计。
- 跨网域：任何 OT 写入必须走审批 + 专用通道 + OT 二次确认；不得直接反控。

## 7. 测试规范（强制）

- 测试金字塔：单元测试为主，集成测试覆盖关键链路，E2E 覆盖核心场景。
- Golden Dataset：

  - 覆盖行业术语、SOP、常见故障、成本口径、红线拦截。
  - 任何模型/Prompt/工具变更必须跑回归。

- 契约测试：对 streaming/events/evidence 的 schema 做自动化断言。

## 8. 代码评审（PR Review）检查清单（推荐）

- 变更是否引入/修改对外契约？是否向后兼容？
- 是否影响证据链与审计？是否补齐 requestId/上下文？
- 是否新增了绕过 RBAC/脱敏/红线的路径？
- 是否新增测试（至少单元或契约测试）？
- 是否具备可观测性（日志/指标）？

## 9. 附录：错误码建议（可扩展）

- `VALIDATION_ERROR`
- `AUTH_ERROR`
- `FORBIDDEN`
- `NOT_FOUND`
- `UPSTREAM_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `CONTRACT_VIOLATION`
- `GUARDRAIL_BLOCKED`
- `EVIDENCE_MISSING`
- `EVIDENCE_MISMATCH`

