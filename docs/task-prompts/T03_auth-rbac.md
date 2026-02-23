### Task 3 - 建立认证与权限：JWT 登录 + RBAC 权限检查（Umbrella）

```markdown
# Context
你正在执行第 3 号任务：建立认证与权限：JWT 登录 + RBAC 权限检查（API 与工具双层门禁）。
你是 GangQing（钢擎）项目负责落地与验收的工程师，角色为 **技术负责人/架构师**。
目标是规划认证、权限模型、能力点（capabilities）、拒绝策略、审计字段与测试口径，确保后续实现不会出现绕过 RBAC 或审计缺失。

本任务覆盖 L1 阶段必须落地的最小闭环：
- JWT 登录与 token 生命周期（R1.1）
- RBAC 权限检查（R1.2），并在 API 层与工具层实施“双层门禁”
- `requestId`、`tenantId`、`projectId` 的上下文贯穿与审计可追溯（R11.1）

本任务不引入任何写操作能力；任何写操作相关能力必须按只读默认策略拦截或进入 L4 治理流程。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 此 Umbrella 阶段禁止输出任何具体实现代码/函数体。
- **PLANNING ONLY**: 只允许输出“怎么做/分几步/文件结构/契约长什么样/验收怎么验”。
- **Schema First（强制）**:
  - 后端：所有对外 I/O（request/response）、鉴权上下文、RBAC 策略、审计事件均使用 Pydantic 作为单一事实源。
  - 前端：对外 I/O 与配置使用 Zod（若本任务包含前端最小接入）。
- **RBAC 双层门禁（强制）**: API 层 capability 校验 + 工具层再次校验（防止绕过）。
- **Isolation（强制）**: L1 起必须启用 `tenantId/projectId` 隔离；缺失或不一致按鉴权失败处理。
- **requestId 贯穿（强制）**: HTTP 入站 -> 依赖注入/上下文 -> 工具调用 -> 审计落库 -> 对外响应。
- **Structured Errors（强制）**: 对外错误必须为 `ErrorResponse`，字段仅允许：
  - `code` / `message`（英文）/ `details?` / `retryable` / `requestId`
- **RBAC & Audit（强制）**: 所有鉴权失败、越权访问、登录成功/失败、敏感资源访问均必须写审计事件。
- **Read-Only Default（强制）**: 未显式授权与审批通过前不得执行写操作；本任务只做门禁与拒绝策略。
- **Real Integration (No Skip)（强制）**:
  - 单元测试可以用依赖注入的等价 fake（模拟真实错误语义）。
  - 冒烟/集成测试必须连接真实服务（真实 FastAPI + 真实 Postgres）；配置缺失或服务不可用必须失败，不得跳过。

# References
- PRD: docs/requirements.md（R1.1/R1.2/R1.3/R5.1/R11.1）
- TDD: docs/design.md（3.1、4.4、6.1）
- tasks: docs/tasks.md（L1 - Task 3）
- contracts: docs/contracts/api-and-events-draft.md（RequestContext、ErrorResponse、Audit Event）
- api docs: docs/api/openapi.yaml（登录端点与错误响应）

# Execution Plan
1) Task 3.1（JWT 登录与 token 生命周期）
- Goal:
  - 定义并落地登录端点契约（request/response）
  - 定义 token 过期/无效/缺失的判定语义与错误码映射
  - 定义鉴权上下文注入（`userId/role/tenantId/projectId/requestId`）
- Deliverables（仅定义，不写代码）:
  - 登录接口与错误响应契约（对齐 `ErrorResponse`）
  - JWT 配置项清单（secret/algorithm/expireSeconds）与校验要求（缺失快速失败，英文错误）
  - 审计事件：`login.success` / `login.failure`（动作摘要脱敏）

2) Task 3.2（RBAC capability 模型与 API/工具双层门禁）
- Goal:
  - 定义角色与 capability 映射（最小闭环：厂长/调度员/维修工/财务）
  - 统一 capability 命名与声明位置（API 端点与工具注册处）
  - 统一拒绝策略：缺 capability -> `FORBIDDEN`
- Key Decisions:
  - 能力点命名规范：`domain:resource:action`
  - capability 校验必须在 API 与工具两处均可复用同一策略/同一错误模型

3) Task 3.3（审计与拒绝策略：可追溯、可检索、可取证）
- Goal:
  - 明确“哪些事件必须审计、审计字段最小集合、脱敏规则”
  - 定义如何通过 `requestId` 聚合整条链路的审计证据
  - 明确拒绝策略与错误码（`AUTH_ERROR` vs `FORBIDDEN`）
- Deliverables:
  - 审计事件类型与最小字段（对齐 contracts 第 4 章）
  - 关键场景审计点位清单：登录、鉴权失败、越权、工具调用（含参数摘要）、响应摘要

# Deliverables Definition
- [ ] **Directory / Modules**: 认证、RBAC、审计、配置加载分别落在哪些模块（只需规划到目录/模块名级别）。
- [ ] **Environment Variables**: JWT 与鉴权相关配置项清单与校验要求（必须对齐 `docs/design.md#2.9` 的“配置外部化与快速失败”）。
- [ ] **API Contracts**:
  - 登录端点的 request/response schema
  - 错误响应统一为 `ErrorResponse`（字段严格对齐 contracts 2.1）
- [ ] **Auth & RBAC**: 角色/能力点/拒绝策略定义，能力点命名规范与声明位置。
- [ ] **Audit Events**: 审计事件最小字段、脱敏策略与取证策略（按 requestId 聚合）。
- [ ] **Observability**: `requestId/tenantId/projectId/userId/role` 在日志与审计中的贯穿约束。

# Verification
- Automated Tests（必须可自动化断言）：
  - Unit: `pytest -q`
    - 登录成功返回 token（仅断言结构与字段，不要求具体算法细节）
    - 无效凭证返回 `AUTH_ERROR`（`ErrorResponse.message` 必须英文）
    - 缺少/无效 token 返回 `AUTH_ERROR`
    - 角色越权返回 `FORBIDDEN`
    - 缺少 `X-Tenant-Id` 或 `X-Project-Id` 返回 `AUTH_ERROR`
  - Smoke: `backend/scripts/auth_smoke_test.py`
    - 必须连接真实服务（真实 FastAPI + 真实 Postgres）
    - 若脚本不存在：子任务必须补齐该脚本并纳入验证链路

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 3.1 - JWT 登录与 token 校验

```markdown
# Context
你正在执行子任务：3.1 - JWT 登录与 token 校验。
目标是实现登录端点、token 验证依赖/中间件，并与统一错误模型、审计与 requestId 贯穿对齐。

本子任务的重点是把“认证”做成可复用的基础设施能力，为后续所有 API 与工具调用提供一致的身份上下文。

# Critical Rules
- **结构化错误**: 无效凭证返回 `AUTH_ERROR`，英文 `message`。
- **RBAC & 审计**: 登录尝试与失败原因摘要需要写审计（禁止记录明文密码）。
- **配置外部化**: JWT secret/算法/过期时间通过配置加载并校验。
- **真实集成测试（No Skip）**: `backend/scripts/auth_smoke_test.py` 必须可运行。
- **Isolation（强制）**: 所有受保护端点必须要求 `X-Tenant-Id/X-Project-Id`；缺失返回 `AUTH_ERROR`。
- **ErrorResponse（强制）**: 错误响应必须严格对齐 `docs/contracts/api-and-events-draft.md#2.1`（字段不多不少）。

# References
- PRD: docs/requirements.md（R1.1）
- tasks: docs/tasks.md（3.1）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse/RequestContext）

# Execution Plan
1) 定义 Pydantic 请求/响应模型与错误响应（ErrorResponse）。
2) 定义登录端点：请求字段、响应字段、失败场景与错误码映射（`AUTH_ERROR`）。
3) 定义 token 校验机制：
   - 缺少/无效/过期 token 的判定语义
   - 将 `userId/role/tenantId/projectId/requestId` 注入到服务端上下文（RequestContext 或等价对象）
4) 增补审计记录：`login.success` / `login.failure`。
5) 明确脱敏规则：审计与日志禁止记录明文密码、token 原文、secret。

# Verification
- **Unit**: `pytest -q`
  - 登录成功返回 token
  - 无效凭证返回 `AUTH_ERROR`
  - token 过期返回 `AUTH_ERROR`
- **Smoke**: `backend/scripts/auth_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 3.2 - RBAC capability 模型与 API/工具双层门禁

```markdown
# Context
你正在执行子任务：3.2 - RBAC capability 模型与 API/工具双层门禁。
目标是定义角色、capabilities 映射与校验机制，确保任何工具调用都不能绕过权限。

本子任务的验收重点是“拒绝正确、审计完整、可追溯”，而不是角色/权限点是否覆盖所有未来场景。

# Critical Rules
- **RBAC 强制**: API 与工具必须双层校验。
- **结构化错误**: 越权返回 `FORBIDDEN`。
- **审计**: 越权访问必须写审计（含 capability 缺失信息摘要）。
- **Capabilities 命名规范**: `domain:resource:action`（必须一致，便于审计与检索）。

# References
- PRD: docs/requirements.md（R1.2）
- tasks: docs/tasks.md（3.2）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 定义角色与 capability 列表（最小闭环：厂长/调度员/维修工/财务）。
2) 实现 capability 校验依赖与工具层 guard。
3) 为关键 API/工具补齐 capability 声明。

建议同时明确（以文档/表格形式）：
- 哪些能力点属于“敏感财务数据读取”
- 哪些能力点属于“核心工艺参数读取”
- 默认拒绝策略：未声明 capability 的端点/工具是否一律拒绝（推荐：拒绝并报 `CONTRACT_VIOLATION` 或 `FORBIDDEN`，以仓库既有错误码策略为准）

# Verification
- **Unit**: `pytest -q` 覆盖：维修工访问财务资源返回 `FORBIDDEN`。
- **Smoke**: 在 `auth_smoke_test.py` 中增加一次越权场景断言。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 3.3 - 审计与拒绝策略（Auth/RBAC/Audit 一致性）

```markdown
# Context
你正在执行子任务：3.3 - 审计与拒绝策略（Auth/RBAC/Audit 一致性）。
目标是把“认证失败/越权拒绝/工具调用/响应摘要”等关键安全事件做到：可落库、可检索、可按 `requestId` 聚合取证，并确保对外错误模型与审计事件之间可关联。

# Critical Rules
- **Audit Mandatory**: 以下场景必须写审计：
  - 登录尝试（成功/失败）
  - 缺少/无效 token（AUTH_ERROR）
  - 越权访问（FORBIDDEN）
  - 工具调用（tool_call，参数摘要脱敏）
  - API 响应摘要（不得包含敏感原文与密钥）
- **Structured Errors**: REST 错误体必须为 `ErrorResponse`；`message` 必须英文。
- **Correlation**: 审计事件必须包含 `requestId/tenantId/projectId/userId/role`，并能通过 `requestId` 聚合整条链路。
- **No Secrets**: 审计与日志禁止记录 token 原文、密码、JWT secret、上游凭证。

# References
- PRD: docs/requirements.md（R11.1/R11.2）
- TDD: docs/design.md（2.8.1、6.1、6.4）
- tasks: docs/tasks.md（3）
- contracts: docs/contracts/api-and-events-draft.md（4.1-4.3 审计事件最小字段；2.1 ErrorResponse）
- security: docs/security/auth-rbac-audit-policy.md（拒绝策略矩阵/审计事件类型/脱敏规则权威口径）

# Execution Plan
1) 明确审计事件模型（最小字段集合）与事件类型：至少覆盖 `query/tool_call/error`，并在本任务新增 `login.success/login.failure`（命名可内部映射到 eventType）。
2) 明确审计落库策略与索引策略：至少能按 `requestId` 检索并聚合。
3) 明确拒绝策略矩阵（必须写成表格）：
   - 缺少 token -> `AUTH_ERROR`
   - token 无效/过期 -> `AUTH_ERROR`
   - capability 缺失 -> `FORBIDDEN`
   - tenantId/projectId 缺失或不一致 -> `AUTH_ERROR`
4) 定义审计脱敏规则：参数摘要 `argsSummary` 与 `actionSummary` 允许记录哪些字段；哪些字段必须脱敏或完全禁止记录。

# Verification
- **Unit**: `pytest -q`
  - 任一拒绝场景都必须写入审计事件（至少断言“有审计记录且 requestId 匹配”）
  - 审计记录不包含敏感字段（token/password/secret）
- **Smoke**: `backend/scripts/auth_smoke_test.py`
  - 通过真实服务触发一次 `AUTH_ERROR` 与一次 `FORBIDDEN`，并能通过审计查询接口或数据库查询验证审计落库

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局约束已包含；本任务不直接产出 Evidence）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
