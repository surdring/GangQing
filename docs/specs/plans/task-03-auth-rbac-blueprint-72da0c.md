# Task 3（认证与权限：JWT + RBAC 双层门禁）执行蓝图
本计划用于在不输出具体实现代码的前提下，给出 Task 3（L1）的模块落点、契约形态、能力点体系、拒绝策略、审计口径与自动化验收方案。

## 1. 现状扫描（仓库当前实现）

### 1.1 已存在能力（可复用/需对齐）
- **请求上下文**：`backend/gangqing/common/context.py`
  - `RequestContext`（包含 `requestId/tenantId/projectId/sessionId/userId/role/taskId/stepId`）
  - `build_request_context()` 强制要求 `X-Tenant-Id` 与 `X-Project-Id`，缺失抛 `AUTH_ERROR`（英文 message）。
- **RBAC（能力点校验）**：`backend/gangqing/common/rbac.py`
  - `require_capability(capability)` 依赖 `RequestContext` 与 `request.state.role/ctx.role`。
  - 当前 capability 集合极小：`chat:stream`、`audit:read`。
- **API 端点示例**：
  - `backend/gangqing/api/chat.py`：`Depends(require_capability("chat:stream"))`
  - `backend/gangqing/api/audit.py`：`Depends(require_capability("audit:read"))`
- **错误模型**：`backend/gangqing/common/errors.py`
  - `ErrorResponse` 字段：`code/message/details?/retryable/requestId`（对齐 contracts 最小字段集合）。
- **requestId/tenant/project 中间件**：`backend/gangqing/app/main.py`
  - 生成 `request.state.request_id`，读取 `X-Tenant-Id/X-Project-Id` 并 bind 到 structlog context。
- **审计落库**：`backend/gangqing_db/audit_log.py`
  - `AuditLogEvent` 含 `requestId/tenantId/projectId/userId/role/resource/actionSummary/result/errorCode/evidenceRefs`。

### 1.2 关键缺口/不一致（必须在 Task 3 解决或明确决策）
- **JWT 登录未落地**：当前没有 `/auth/login` 或等价端点；`userId/role` 目前通过 `X-User-Id/X-Role` 头注入，未满足 R1.1。
- **契约冲突风险：ErrorResponse 字段约束**：
  - `docs/contracts/api-and-events-draft.md#2.1` 约束“对外 ErrorResponse 仅允许 5 个字段”。
  - 但 `backend/gangqing/app/main.py` 的 `handle_app_error()` 会把大量上下文塞进 `details.context`。
  - 决策：需确认“contracts 的严格限制”是否适用于当前 REST 错误实现；若适用，需要在实现阶段调整为不输出 context（仅保留允许字段），并把上下文放入日志/审计。
- **RBAC 双层门禁尚未完整落地**：API 层已有 `Depends(require_capability)` 的示例，但“工具层 guard”目前缺少统一入口（需要定义工具调用包装器/基类/装饰器策略）。
- **审计事件覆盖不足**：现有落库函数存在，但缺少明确的“必须写审计点位清单”与测试断言（例如：AUTH_ERROR/FORBIDDEN 必须落库）。

## 2. 目标范围（L1 最小闭环）

### 2.1 必须交付
- **JWT 登录与 token 生命周期（R1.1）**
- **RBAC（R1.2）**：以 capability 为单一权限点；API + 工具双层校验
- **隔离上下文（tenantId/projectId）**：缺失直接 `AUTH_ERROR`
- **审计可追溯（R11.1）**：至少覆盖登录、鉴权失败、越权、工具调用、响应摘要

### 2.2 明确不做
- 不引入写操作能力，不涉及审批/多签/受控执行（L4）。

## 3. 设计决策（需你确认的点）
- **D1：未声明 capability 的端点/工具默认策略**
  - 已确认：**默认拒绝（Default Deny）**。
  - 对外返回：`FORBIDDEN`（HTTP 403），并在审计/日志记录 `reason=capability_not_declared`。
- **D2：错误响应 details 的对外约束是否严格执行 contracts #2.1**
  - 已确认：**严格执行** `docs/contracts/api-and-events-draft.md#2.1`。
  - 约束：对外 `ErrorResponse` 仅包含既定 5 字段；不得在 `details` 中输出 `tenantId/projectId/userId/role` 等上下文字段。
  - 上下文与诊断信息进入：结构化日志 + 审计落库（按 `requestId` 聚合取证）。
- **D3：前端是否纳入 Task 3（最小接入）**
  - 已确认：选项 B（**前端最小接入**）。
  - 约束：仅包含“登录态 + token 存储 + 请求头注入 + 鉴权失败提示”；不扩展 UI 体系，不引入与 T3 无关的前端重构。

### 3.4 业界最佳实践（无法联网抓取时的稳定共识）

说明：我尝试抓取 MDN/Auth0/Authress 等页面时发生网络超时，因此这里给出基于常见 RFC/OWASP/主流网关实践的“稳定共识”（实现时仍以本仓库 contracts 为权威）。

- **认证 vs 授权的 HTTP 语义（通用共识）**
  - `401`：缺少/无效凭证（authentication failed）
  - `403`：凭证有效但权限不足（authorization failed）
  - 对应到本项目错误码：
    - `AUTH_ERROR` -> HTTP 401
    - `FORBIDDEN` -> HTTP 403

- **默认拒绝（Default Deny）是权限系统的主流最佳实践**
  - 原因：权限点遗漏声明是最常见的“绕过”来源；默认拒绝能把遗漏变成显式失败，避免静默放行。
  - 因此对 **D1** 的推荐是：
    - API 端点未声明 capability：拒绝
    - 工具未声明 required_capability：拒绝

- **未声明 capability 被拒绝时的错误码选择（两种主流风格）**
  - 选项 1（更贴近“权限不足”语义）：返回 `FORBIDDEN`
  - 选项 2（更贴近“开发/配置错误”语义）：返回 `CONTRACT_VIOLATION`
  - 推荐（结合你们 contracts 与可运维性）：
    - **生产对外**：优先 `FORBIDDEN`（不泄露内部契约细节，语义稳定）
    - **内部可观测/审计/日志**：记录 `reason=capability_not_declared` 作为诊断字段

- **错误响应最小化（Minimize Error Surface）**
  - 主流网关实践倾向于：对外响应尽量少暴露上下文（tenant/project/user/role 等），避免信息泄露与枚举攻击。
  - 因此对 **D2** 的推荐是：严格执行 `docs/contracts/api-and-events-draft.md#2.1`
    - `ErrorResponse` 的字段保持最小集合
    - 需要的上下文进入：结构化日志 + 审计落库（可通过 requestId 聚合取证）

- **审计策略（Security Event Logging）**
  - 最佳实践：对“安全相关失败”也要审计（登录失败、鉴权失败、越权、敏感资源访问），否则追溯链断裂。
  - 但必须遵守：不记录密钥、token 原文、密码原文（只记录摘要/原因码）。

- **前端纳入范围（渐进式落地）**
  - 主流做法是：后端先提供稳定 auth 接口与错误模型；前端在最小闭环里只做 token 保存与请求注入。
  - 因此对 **D3** 的推荐组合是：
    - 若你们当前主要在打通后端骨架：先选 A（后端）并明确“下一任务接入前端”
    - 若希望严格对齐 `docs/tasks.md` 的交付：选 B，但把前端范围限定为“登录态 + 请求头注入”，不扩展 UI 体系

### 3.5 推荐的决策组合（默认建议）
- **D1**：默认拒绝；对外返回 `FORBIDDEN`，并在审计/日志里记录 `reason=capability_not_declared`
- **D2**：严格执行 contracts（对外不返回 context；context 进日志/审计）
- **D3**：B（前端最小接入：登录态 + token 注入 + 失败提示）

## 4. Execution Plan（执行蓝图）

### 4.1 Task 3.1：JWT 登录与 token 生命周期
- **API 端点（建议）**：`POST /api/v1/auth/login`
  - 请求：`username/password`（最小字段集合；密码不得写审计原文）
  - 响应：`accessToken`（JWT）、`tokenType`（Bearer）、`expiresInSeconds`（可选）
- **鉴权依赖（建议）**：
  - 统一 FastAPI dependency：`require_auth()`
  - 输出：将 `userId/role` 注入 `request.state` + `RequestContext`
- **配置（必须外部化并校验）**：
  - `GANGQING_JWT_SECRET`
  - `GANGQING_JWT_ALGORITHM`
  - `GANGQING_JWT_EXPIRE_SECONDS`
- **错误码映射**：
  - 无效凭证：`AUTH_ERROR`
  - token 缺失/无效/过期：`AUTH_ERROR`

### 4.2 Task 3.2：RBAC capability 模型与双层门禁
- **能力点命名规范**：`domain:resource:action`
- **最小角色集合（对齐 design/requirements）**：
  - `plant_manager` / `dispatcher` / `maintainer` / `finance`
- **能力点最小集合（建议先覆盖已存在 API）**：
  - `chat:stream`（对齐现有）
  - `audit:read`（对齐现有）
  - （可选扩展，若你希望把更多 API 纳入 RBAC）：`semantic:*`、`data:*` 等
- **API 层门禁**：
  - 每个受保护端点必须显式声明 capability（依赖注入）
- **工具层门禁（必须落地）**：
  - 统一工具执行入口（例如 `run_tool(tool_name, args, ctx)`）在执行前调用 `require_capability(tool_required_capability)`
  - 工具注册处必须声明 `required_capability`

### 4.3 Task 3.3：审计与拒绝策略
- **审计事件类型（最小集合 + 本任务新增）**：
  - `login.success` / `login.failure`
  - `auth.failure`（缺 token/无效 token/缺 tenant/project）
  - `rbac.forbidden`（capability 缺失）
  - `tool_call`（工具调用）
  - `response`（响应摘要；不含敏感原文）
- **审计字段最小集合**（对齐 contracts 4.2）：
  - `requestId/tenantId/projectId/userId/role/resource/actionSummary/result/errorCode`
- **拒绝策略矩阵（必须写成表并在测试覆盖）**：
  - 缺少 `X-Tenant-Id` 或 `X-Project-Id`：`AUTH_ERROR`
  - 缺 token/无效/过期：`AUTH_ERROR`
  - capability 缺失：`FORBIDDEN`
- **脱敏红线**：
  - 禁止落库/日志：密码、JWT 原文、secret、上游凭证

## 5. Deliverables（文件与模块落点：规划级）
- `backend/gangqing/api/auth.py`：登录端点（规划目标）
- `backend/gangqing/common/auth.py`：JWT 编解码、鉴权依赖（规划目标）
- `backend/gangqing/common/rbac.py`：capability 映射、校验依赖（扩展现有）
- `backend/gangqing_db/audit_log.py`：审计落库（复用现有；补齐事件覆盖策略）
- `backend/scripts/auth_smoke_test.py`：冒烟测试脚本（若不存在则新增）
- `backend/tests/test_auth_*.py`：单元测试（错误码、拒绝、审计断言）

（前端最小接入，D3=B）
- `web/`：最小登录态与 token 存储（例如 localStorage/sessionStorage；具体由实现阶段决定，但必须可配置与可清理）
- `web/`：请求封装层统一注入 `Authorization: Bearer <token>` + `X-Tenant-Id` + `X-Project-Id` + `X-Request-Id`
- `web/`：收到 `AUTH_ERROR/FORBIDDEN` 时的最小提示与重试引导（文案允许中文；但上报/日志字段保留英文 `code/message`）

## 6. Verification Plan（验收与测试口径）

### 6.1 单元测试（必须）
- `pytest -q` 覆盖：
  - 登录成功返回 token（仅断言结构）
  - 无效凭证返回 `AUTH_ERROR`，且 `ErrorResponse.message` 英文
  - 缺少 tenant/project 返回 `AUTH_ERROR`
  - 缺少/无效 token 返回 `AUTH_ERROR`
  - 越权返回 `FORBIDDEN`
  - 关键拒绝场景必须写审计（至少断言“写入函数被调用/落库记录存在且 requestId 匹配”——实现阶段按可行方式落地）

（前端最小接入，D3=B）
- `npm -C web test`（若仓库已有测试框架；若没有则在实现阶段补齐最小可运行测试）覆盖：
  - token 持久化与清理
  - 请求头注入（含 `Authorization/X-Tenant-Id/X-Project-Id/X-Request-Id`）
  - 对 `AUTH_ERROR/FORBIDDEN` 的错误处理分支（UI 提示 + 状态复位）

### 6.2 冒烟测试（必须，真实服务）
- `backend/scripts/auth_smoke_test.py`
  - 前置：真实 FastAPI + 真实 Postgres
  - 场景：
    - 成功登录
    - 携 token 访问受保护端点成功
    - 触发一次 `AUTH_ERROR` 与一次 `FORBIDDEN`
    - 验证审计落库可按 `requestId` 查询到对应事件

## 7. 风险与控制点
- **契约一致性风险**：ErrorResponse 字段与 `details.context` 的冲突需在实现阶段解决（见 D2）。
- **绕过风险**：若工具层未统一入口做 capability guard，仍可能绕过 API 层校验。
- **审计缺失风险**：需要把“必须审计点位清单”转成自动化断言，避免靠人工检查。

## 8. 下一步（等待你确认后进入实现）
请你确认 D1/D2/D3 三个决策点；确认后我会切到执行模式，按 3.1/3.2/3.3 拆子任务落地并跑完 `pytest -q` 与 `backend/scripts/auth_smoke_test.py`。
