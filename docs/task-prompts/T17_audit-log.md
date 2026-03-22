### Task 17 - 审计落库与不可篡改策略（append-only + 查询也要被审计）（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 17 号任务：审计落库与不可篡改策略（append-only + 查询也要被审计）。
你的角色是 **技术负责人/架构师**。
你的目标是制定任务 17 的详细执行计划，明确审计事件模型、落库策略（append-only）、审计查询的二次审计、权限边界，以及与 `requestId` 全链路贯穿的对齐方式。

# Critical Rules (核心约束)
- **NO CODE IMPLEMENTATION**: 在本 Umbrella 阶段禁止输出任何具体实现代码。
- **PLANNING ONLY**: 仅输出“怎么做/分几步/改哪些文件/接口长什么样/验收怎么跑”。
- **RBAC & Audit (MUST)**:
  - 审计写入必须覆盖：`query/tool.call/tool.result/response/error`，并预留 `approval/write_operation`。
  - **审计查询本身也必须写审计**（二次审计）。
  - 审计数据读取必须受控：最小权限，按能力点（capability）或角色限制。
- **Append-only (MUST)**:
  - 审计写入不可修改/不可删除（至少在应用层强制 + DB 权限策略）。
  - 任何“更正/补录”只能追加新事件，且需可追溯到原事件（通过 `correlation_id` 或 `supersedes_event_id` 之类的关联字段；字段名称以对外契约为准）。
- **RequestContext & Observability (MUST)**:
  - `requestId` 必须贯穿 HTTP -> 编排 -> 工具调用 -> SSE 事件 -> 审计落库。
  - 必须在审计中记录 `tenantId/projectId/sessionId`（若存在）与关键执行阶段标识（如 `stepId/toolCallId`）。
- **Structured Errors (MUST)**:
  - 对外错误必须结构化：`code` + 英文 `message` + `requestId` + `retryable` + `details?`。
  - 审计中记录错误时，必须同时记录 `code/message`（`message` 必须为英文）。
- **Schema Single Source of Truth (MUST)**:
  - 后端：审计事件、审计查询请求/响应使用 Pydantic。
  - 前端（如涉及审计展示/导出）：使用 Zod 对齐并进行运行时校验。
- **Data Protection (MUST)**:
  - 审计事件中的参数与结果摘要必须脱敏；严禁把密钥、token、密码、连接串等写入审计。
- **Real Integration (No Skip)**:
  - 测试必须连接真实服务（真实 FastAPI + 真实 Postgres）；配置缺失或服务不可用必须失败，不得 skip。

# References
- PRD: docs/requirements.md（R11.1/R11.2）
- TDD: docs/design.md（2.8.1）
- tasks: docs/tasks.md（任务 17）
- contracts: docs/contracts/api-and-events-draft.md（4 Audit Event）

# Execution Plan (执行蓝图)

1) Task 17.1（审计事件模型与字段口径）
- Goal: 统一审计事件 schema、事件类型枚举与最小字段集合，确保能按 `requestId` 聚合与追溯。
- Deliverables:
  - Pydantic 审计事件模型与枚举
  - 审计落库写入接口/服务边界（仅规划，不写实现）
  - 脱敏策略口径（哪些字段必须脱敏/如何摘要）

2) Task 17.2（落库与 append-only 不可篡改策略）
- Goal: 设计数据库表结构与索引，明确不可篡改策略（应用层 + DB 权限），并定义“更正只能追加”的机制。
- Deliverables:
  - `audit_log` 表字段与索引规划
  - DB 权限策略（应用账号最小权限）
  - 不可篡改策略说明与约束清单

3) Task 17.3（审计查询 API 与二次审计）
- Goal: 设计审计查询接口（过滤/分页/时间范围/按 requestId 聚合等），并确保每次查询本身产生审计事件。
- Deliverables:
  - 审计查询请求/响应契约（Pydantic）
  - RBAC 权限边界与拒绝策略
  - 查询的二次审计事件口径

# Deliverables Definition (交付物定义)
- [ ] **Directory / Files**: 明确新增/修改的文件列表（以实际仓库结构为准，例如 `backend/gangqing_db/audit_log.py`、`backend/gangqing_db/audit_query.py`、对应的 Pydantic models 与 API route）。
- [ ] **Audit Event Contract**: 审计事件 schema（字段、类型、约束、脱敏）必须与 `docs/contracts/api-and-events-draft.md` 对齐。
- [ ] **Append-only Strategy**: 应用层限制 + DB 权限限制的双层方案；说明其安全边界。
- [ ] **RBAC**: 谁能写、谁能读、谁能查（按 capability/角色），以及越权错误码。
- [ ] **Error Model**: 错误码枚举与结构化错误响应（`code/message/requestId/retryable/details?`）。
- [ ] **Observability**: `requestId` 贯穿与审计字段映射；必须可按 `requestId` 回溯工具调用与证据引用（如适用）。

# Verification Plan (整体验收)
- **Automated Tests**:
  - Unit: `pytest -q`
  - Smoke: `backend/scripts/audit_log_smoke_test.py`
- **Must Cover (Scenarios)**:
  - 写入审计事件成功（包含 `requestId/tenantId/projectId`）
  - 发生错误时审计记录包含 `code` 与英文 `message`
  - 审计查询成功，且查询操作本身产生二次审计事件
  - RBAC 拒绝：无权限读取审计时返回结构化错误（`FORBIDDEN`/`AUTH_ERROR` 以契约为准）

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 17.1 - 审计事件模型：query/tool.call/tool.result/response/error（预留 approval/write_operation）

```markdown
# Context
你正在执行子任务：17.1 - 审计事件模型。
你的角色是 **高级开发工程师**。
你的目标是实现审计事件 Pydantic 模型（以及必要的枚举/校验），并提供落库写入的模块边界，确保能按 `requestId` 聚合。

# Critical Rules
- **Schema First (Pydantic)**: 审计事件模型必须是单一事实源，并在写入前完成校验。
- **最小字段集合（MUST）**（字段名以对外契约为准，以下为语义口径）：
  - identity: `requestId/tenantId/projectId/sessionId?`
  - actor: `userId/role`
  - event: `eventType/timestamp`
  - target/action: `resource/action`
  - payload summary: `actionSummary/resultSummary`
  - linkage: `toolCallId?/stepId?/evidenceRefs?`
  - error (optional): `error.code/error.message`（英文 message）
- **脱敏（MUST）**:
  - `actionSummary/resultSummary` 必须脱敏。
  - 严禁把敏感凭证写入审计（token/password/connection string 等）。
- **RequestId (MUST)**: `requestId` 允许由服务端生成，但落库时必须存在。

# References
- tasks: docs/tasks.md（17.1）
- contracts: docs/contracts/api-and-events-draft.md（4.2）

# Execution Plan
1) 定义审计事件模型与枚举
- Files: 以现有模块划分为准（优先复用 `backend/gangqing_db/` 下的模型与写入逻辑）。
- Action: 定义 Pydantic model + 枚举（eventType/status 等），并补充字段校验（如必填/长度/类型）。

2) 定义写入边界（append-only）
- Action: 暴露一个“仅追加写入”的接口（函数/类皆可），禁止 update/delete 路径。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/audit_log_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 17.2 - append-only 与权限：不可篡改与受控读取

```markdown
# Context
你正在执行子任务：17.2 - append-only 与权限：不可篡改与受控读取。
你的角色是 **高级开发工程师**。
你的目标是把“不可篡改”落到可验证的工程约束：应用层只追加 + DB 权限最小化，并补齐受控读取的权限边界。

# Critical Rules
- **append-only**。
- **RBAC**: 只有审计员/管理员可读（按能力点约束）。
- **No Hard Delete/Update**: 不允许任何对审计表的更新/删除路径（包括管理接口）。

# References
- PRD: docs/requirements.md（R11.2）
- tasks: docs/tasks.md（17.2）

# Execution Plan
1) DB 策略与约束
- Action:
  - 设计/确认 `audit_log` 表的写入路径只允许 INSERT。
  - 规划 DB 权限：应用账号最小权限（至少 INSERT；SELECT 是否允许需与“受控读取”设计一致）。

2) 读取权限边界
- Action:
  - 审计读取 API/服务必须做 capability 校验。
  - 对越权访问返回结构化错误（英文 `message`）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/audit_log_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 17.3 - 审计查询与二次审计（查询也要被审计）

```markdown
# Context
你正在执行子任务：17.3 - 审计查询与二次审计。
你的角色是 **高级开发工程师**。
你的目标是实现“可控的审计查询能力”，并确保每一次审计查询都会产生一条新的审计事件（二次审计），满足合规追溯。

# Critical Rules
- **RBAC (MUST)**: 审计查询仅对具备能力点/角色的用户开放。
- **Query Is Audited (MUST)**: 每次查询必须写入审计事件（事件类型建议为 `audit.query` 或等价枚举，以契约为准）。
- **No Sensitive Leak (MUST)**: 查询条件与结果摘要必须脱敏；禁止返回或记录敏感原文。

# References
- PRD: docs/requirements.md（R11.1/R11.2）
- TDD: docs/design.md（2.8.1）
- tasks: docs/tasks.md（17.3）
- contracts: docs/contracts/api-and-events-draft.md（Audit Query / Audit Event）

# Execution Plan
1) 定义审计查询请求/响应契约（Pydantic）
- Action:
  - 支持按 `timeRange`、`eventType`、`requestId`、`userId`、`toolName` 等过滤（字段集合以实际需求为准）。
  - 支持分页（limit/offset 或 cursor），并限制最大返回量（防止批量导出倾向）。

2) 实现受控读取与二次审计
- Action:
  - capability 校验通过后才允许读取。
  - 读取成功/失败都要写入审计事件（至少记录查询摘要、结果条数摘要、耗时、错误码）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/audit_log_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检）
- [x] 是否所有对外错误 `message` 都是英文？
- [x] 是否所有对外错误都包含 `code/message/requestId/retryable/details?`？
- [x] 是否审计事件包含 `requestId/tenantId/projectId/userId/role/eventType/timestamp` 等最小集合？
- [x] 是否对 `actionSummary/resultSummary` 做了脱敏且不会记录密钥/token？
- [x] 是否 append-only（无 update/delete 路径），且更正/补录采用追加策略？
- [x] 是否审计查询具备 RBAC 且查询操作本身被审计（二次审计）？
- [x] 是否单元测试与冒烟测试均可运行且不可 skip（真实 FastAPI + 真实 Postgres）？
