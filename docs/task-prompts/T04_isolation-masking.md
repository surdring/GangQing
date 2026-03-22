### Task 4 - 落地数据域隔离与脱敏策略（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 4 号任务：落地数据域隔离与脱敏策略（默认过滤 + 字段级脱敏 + 可审计）。
你的角色是 **技术负责人/架构师**。
你的目标是：为 L1 阶段建立**可执行、可验收、可审计**的数据域隔离与脱敏方案，并把关键决策落到“改哪些文件/哪些 schema/哪些测试断言/哪些冒烟脚本”层面。

本任务关注：
- **Isolation（数据域隔离）**：`tenantId/projectId` 作为强制 scope，缺失即拒绝；显式 scope 只能“更严格”不能“越权”。
- **Masking（字段级脱敏）**：按角色/域/字段路径脱敏；对 Evidence / 审计 / 日志默认脱敏。
- **Audit（可审计）**：隔离拒绝、RBAC 拒绝、脱敏命中都必须留下可追溯审计摘要（禁止敏感原文）。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 本阶段禁止输出任何具体实现代码（函数实现/SQL/路由实现等）。
- **PLANNING ONLY**: 只输出“怎么做/分几步/改哪些文件/契约与验收口径”。
- **Isolation（强制）**: 所有数据读写必须默认按 `tenantId/projectId`（以及产线等扩展维度）过滤。
  - 检测到跨隔离访问：必须返回结构化错误（默认 `AUTH_ERROR`，若接口契约约定用 `FORBIDDEN` 则以契约为准），并写入审计。
  - 缺少隔离上下文：必须快速失败（不要悄悄放行/不要返回全量数据）。
- **Masking（强制）**: 财务/工艺参数/敏感配方等按角色脱敏；Evidence/审计/日志中的字段默认脱敏（只记录摘要与策略命中信息）。
- **RBAC + 审计 + requestId 贯穿（强制）**: HTTP 入站 → 工具调用 → Evidence → SSE/REST 输出 → 审计落库。
- **Structured Errors（强制）**: 对外错误必须结构化（`code`/`message`/`requestId`/`retryable`/`details?`），且 `message` 必须为英文。
- **Schema Single Source of Truth（强制）**: 对外 I/O、工具参数、Evidence、审计事件必须以 schema 为单一事实源（后端 Pydantic；前端如涉及展示/事件校验用 Zod）。
- **Config Externalization（强制）**: 隔离/脱敏策略、开关、默认行为必须配置化；禁止硬编码租户/产线/字段名白名单到业务逻辑中。
- **Real Integration (No Skip)（强制）**: 冒烟/集成测试必须连真实 FastAPI + 真实 Postgres；缺配置/依赖不可用必须失败，不得跳过。

补充工程现实（用于约束执行计划）：
- 当前代码中 RequestContext 的 scope 入口为 `backend/gangqing/common/context.py::build_request_context`（从 `X-Tenant-Id/X-Project-Id` 读取）。
- 当前工具层 scope 注入/越权拒绝的入口为 `backend/gangqing/tools/isolation.py`（`resolve_scope/build_scope_where_sql/require_rows_in_scope`）。
- 当前脱敏引擎入口为 `backend/gangqing/common/masking.py::apply_role_based_masking`（策略加载点见 `backend/gangqing/api/audit.py`）。
- 当前审计写入入口为 `backend/gangqing/common/audit.py::write_audit_event/write_tool_call_event`。

# References
- PRD: docs/requirements.md（R1.3 数据域隔离；R10.2 敏感信息脱敏）
- TDD: docs/design.md（4.4 数据域隔离与脱敏落地；6 统一错误模型）
- tasks: docs/tasks.md（L1 - 4. 落地数据域隔离与脱敏策略）
- contracts: docs/contracts/api-and-events-draft.md（错误模型 / Evidence / 审计事件 / SSE 事件如适用）
- api docs: docs/api/openapi.yaml（相关 API 的错误响应与 requestId 约束，如已有）

补充约束来源：
- RLS（可选第二道防线）的决策与前置条件以 `docs/design.md#4.4.1` 为准。

# Execution Plan
1) Task 4.1（数据域过滤：工具层强制叠加）
- Goal:
  - 明确 scope 的**权威来源**与**拒绝策略**（缺 header / scope 不匹配 / 数据命中跨域）。
  - 明确工具层如何“默认注入” scope，以及如何在工具返回前再次做“cross-scope data hit”检测（Defense-in-Depth）。
- Deliverables:
  - 约束清单：scope 注入点、拒绝场景、错误码选择（`AUTH_ERROR` vs `FORBIDDEN`）与审计事件。
  - 目标文件范围（供执行阶段落地）：`backend/gangqing/common/context.py`、`backend/gangqing/tools/isolation.py`、`backend/gangqing/tools/postgres_readonly.py`。

2) Task 4.2（字段级脱敏：按角色配置）
- Goal:
  - 定义“角色 → 允许查看的域/字段路径/关键字片段”的策略表达，并明确默认动作（mask/deny/allow）。
  - 明确脱敏对外边界：API 响应、Evidence、审计 actionSummary、日志字段。
- Deliverables:
  - 脱敏策略的 schema 与加载失败行为（无效策略必须视为 `CONTRACT_VIOLATION` 并审计）。
  - 目标文件范围（供执行阶段落地）：`backend/gangqing/common/masking.py`、`backend/gangqing/api/audit.py`（以及如需要的策略配置加载模块）。

3) Task 4.3（审计与证据展示策略）
- Goal:
  - 明确审计事件的最小集合（query/tool_call/response/error + 可选 data_masked/rbac_denied 等）与必填字段（含 `requestId/tenantId/projectId`）。
  - 明确脱敏摘要格式：只允许记录规则 ID / 策略版本 / 命中字段路径等，不得记录敏感原文。
  - 明确 Evidence 默认脱敏与“可展开”能力的权限点（如需，必须配套审计事件）。
- Deliverables:
  - 审计事件字段与落库/查询 API 的脱敏策略一致性口径。
  - 目标文件范围（供执行阶段落地）：`backend/gangqing/common/audit.py`、`backend/gangqing/api/audit.py`、`backend/gangqing/common/audit_event_types.py`。

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确新增/修改的目录与文件列表（后端/前端/脚本/文档）。
- [ ] **Environment Variables & Config**: 明确隔离/脱敏相关 ENV 与配置 schema（缺失必须快速失败，英文错误）。
- [ ] **Isolation Model**: 隔离维度定义（`tenantId/projectId`/产线等）、默认过滤规则、跨域检测与拒绝策略。
- [ ] **Masking Policy**: 角色→字段白名单/脱敏规则/展开权限；Evidence/审计/日志的脱敏边界。
- [ ] **Audit Events**: 审计事件类型（query/tool_call/response/error 等）与必须字段（含 requestId）。
- [ ] **Error Model**: 错误码与结构化错误响应/事件（英文 message）。
- [ ] **Test Plan**: 单元测试覆盖点 + 冒烟测试链路（真实服务，不可 skip）。

# Verification
- **Unit**: `pytest -q`
  - 必测断言（至少）：
    - 缺少 `X-Tenant-Id/X-Project-Id` => `AUTH_ERROR`（英文 message）
    - 显式传入 scope 且与 ctx 不一致 => `AUTH_ERROR`（英文 message）
    - 工具返回数据命中跨域 => `AUTH_ERROR`（英文 message）
    - 不同角色对相同 payload 的脱敏结果不同，且返回结果携带脱敏元信息（如 policyId/version/maskedKeys）
    - 审计 actionSummary 中不出现敏感原文（只允许脱敏摘要与策略命中信息）
- **Smoke**: `backend/scripts/rbac_and_masking_smoke_test.py`
  - 必测链路（至少）：
    - 成功路径：带合法 scope + 合法 role，返回结果被默认过滤且敏感字段被脱敏
    - 失败路径：跨域/越权访问，返回结构化错误（含 `code/message/requestId/retryable`）并可在审计中看到拒绝摘要

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 4.1 - 数据域过滤（工具层强制叠加）

```markdown
# Context
你正在执行子任务：4.1 - 数据域过滤（工具层强制叠加）。
目标是实现“默认过滤”，并确保任何查询都不会绕过 scope。

# Critical Rules
- **Isolation（强制）**: 缺少隔离上下文（如 `X-Tenant-Id/X-Project-Id` 或等价上下文字段）必须快速失败并返回结构化错误（默认 `AUTH_ERROR`，以契约为准）。
- **No Escapes（强制）**: 任何路径不得绕过默认过滤（包括工具层直接调用、内部服务调用、批量查询）。
- **审计（强制）**: 记录过滤命中信息摘要与策略版本（如有），禁止记录敏感原文。
- **English Message（强制）**: 对外错误的 `message` 必须为英文。

# References
- PRD: docs/requirements.md（R1.3）
- tasks: docs/tasks.md（4.1）
- TDD: docs/design.md（4.4 数据域隔离与脱敏落地；6 统一错误模型）
- contracts: docs/contracts/api-and-events-draft.md（Error Model / Audit Event Schema，如已定义）

# Target Files (预期改动范围)
- backend/gangqing/common/context.py（`X-Tenant-Id/X-Project-Id` scope headers 强制校验）
- backend/gangqing/tools/isolation.py（`resolve_scope/require_rows_in_scope/build_scope_where_sql`）
- backend/gangqing/tools/postgres_readonly.py（scope where 注入点，避免任何“漏过滤”路径）
- backend/gangqing/common/audit.py（隔离拒绝的审计事件写入，actionSummary 仅保留摘要）
- backend/scripts/rbac_and_masking_smoke_test.py（冒烟覆盖：默认过滤成功 + 跨域失败）

# Execution Plan
1) 在工具层统一入口注入 scope 过滤条件。
2) 增加跨域访问检测与错误映射（`AUTH_ERROR`）。
3) 增加“cross-scope data hit”防线：工具返回前检查行内 `tenant_id/project_id`（如存在）不越界。

# Verification
- **Unit**: `pytest -q`（缺 scope/跨 scope 必须失败）。
- **Smoke**: `backend/scripts/rbac_and_masking_smoke_test.py`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 4.2 - 字段级脱敏策略（按角色）

```markdown
# Context
你正在执行子任务：4.2 - 字段级脱敏策略（按角色）。
目标是按角色配置可见字段与脱敏规则，并确保 Evidence/审计不泄露敏感原文。

# Critical Rules
- **脱敏强制**: 默认脱敏，只有具备权限可展开。
- **审计脱敏**: 参数摘要不得包含敏感原文。
- **Evidence 默认脱敏（强制）**: Evidence/引用/过滤条件必须以脱敏后版本展示；如需“可展开”，必须有明确权限点与审计记录。
- **显式 Unmask 开关（强制）**: 仅具备 `data:unmask:read` 能力不足以默认返回原文；必须在 API/请求中显式声明（例如 `unmask=true`）且通过 RBAC 校验，才允许返回未脱敏内容。
- **English Message（强制）**: 对外错误的 `message` 必须为英文。

# References
- PRD: docs/requirements.md（R10.2）
- tasks: docs/tasks.md（4.2）
- TDD: docs/design.md（4.4 数据域隔离与脱敏落地；6 统一错误模型）
- contracts: docs/contracts/api-and-events-draft.md（Error Model / Evidence Schema / Audit Event Schema，如已定义）

# Target Files (预期改动范围)
- backend/gangqing/common/masking.py（`apply_role_based_masking`，输出 masking meta：policyId/version/maskedKeys）
- backend/gangqing/common/rbac.py（如需新增/复用 capability：控制“可展开查看原文”）
- backend/gangqing/api/audit.py（审计查询接口返回 actionSummary 的脱敏与策略命中审计；如支持 `unmask`，必须是显式参数且需 `data:unmask:read`）
- backend/gangqing/common/audit.py（记录 data_masked 摘要事件，禁止敏感原文）
- backend/scripts/rbac_and_masking_smoke_test.py（冒烟覆盖：不同角色输出差异 + 审计可查询且已脱敏）

# Execution Plan
1) 定义角色 -> 字段白名单/脱敏策略配置。
2) 在响应序列化前应用脱敏（含 Evidence 展示字段）。
3) 确认“默认脱敏”边界覆盖：API 响应 + Evidence + 审计 actionSummary（至少这三类）。

# Verification
- **Unit**: `pytest -q` 覆盖：不同角色返回字段差异。
- **Smoke**: `backend/scripts/rbac_and_masking_smoke_test.py`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 4.3 - 审计与证据展示策略（命中策略/脱敏摘要，禁止敏感原文）

```markdown
# Context
你正在执行子任务：4.3 - 审计与证据展示策略。
目标是定义并落地：审计事件的字段与脱敏边界、Evidence 默认脱敏的展示规则、以及“策略命中信息”的可追溯记录方式。

# Critical Rules
- **Audit Coverage（强制）**: 至少覆盖 query/tool_call/response/error；所有事件必须携带 `requestId`。
- **No Sensitive Raw Data（强制）**: 审计/日志/Evidence 不得包含敏感原文；只允许记录脱敏摘要与策略命中信息（例如规则 ID、字段名、脱敏类型、是否可展开）。
- **Audit Write-Boundary Masking（强制）**: 审计落库前必须对 `actionSummary` 执行默认脱敏；禁止任何路径把敏感原文写入审计表（即使具备 `data:unmask:read` 能力也不例外）。
- **显式 Unmask 开关（强制）**: 若审计查询接口支持 `unmask=true`，必须满足“显式请求 + `data:unmask:read` RBAC 通过”；无权限请求必须返回结构化 `FORBIDDEN`（英文 `message`）。
- **Structured Errors（强制）**: 错误入库与对外输出必须包含稳定 `code` 与英文 `message`。

# References
- PRD: docs/requirements.md（R10.2, R11.1 审计）
- TDD: docs/design.md（2.8 审计；4.4 隔离与脱敏；6 统一错误模型）
- tasks: docs/tasks.md（4.3）
- contracts: docs/contracts/api-and-events-draft.md（Audit Event / Evidence / Error Model）

# Target Files (预期改动范围)
- backend/gangqing/common/audit.py（写入审计事件：最小字段集合 + actionSummary 脱敏摘要）
- backend/gangqing/common/audit_event_types.py（审计事件类型枚举：rbac_denied/data_masked/tool_call 等）
- backend/gangqing/api/audit.py（审计查询接口：按角色返回脱敏后的 actionSummary，并可记录 policyHits 审计）
- backend/gangqing/common/masking.py（用于审计 actionSummary 脱敏）
- backend/scripts/rbac_and_masking_smoke_test.py（冒烟覆盖：触发拒绝 + 通过审计 API 查询到摘要记录）

# Execution Plan
1) 定义审计事件 schema（字段、必填项、脱敏摘要格式、禁止字段列表）。
2) 定义 Evidence 展示字段白名单与“可展开”授权条件（权限点 + 审计记录）。
3) 在关键链路加入审计写入：过滤命中摘要、脱敏命中摘要、错误码与 requestId。

# Verification
- **Unit**: `pytest -q`
  - 覆盖：审计事件包含 `requestId`；审计不包含敏感原文；错误事件包含 `code/message(英文)/requestId/retryable`。
- **Smoke**: `backend/scripts/rbac_and_masking_smoke_test.py`
  - 覆盖：真实服务运行时，触发 1 次跨域/越权失败，并验证审计落库（或可查询）记录了“策略命中摘要”而非敏感原文。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检）
- [x] Umbrella 是否包含 `# Critical Rules` 且明确 **NO CODE IMPLEMENTATION**？
- [x] Umbrella 的 `# Execution Plan` 是否覆盖 4.1/4.2/4.3？
- [x] 是否包含 **Deliverables Definition**（目录/ENV/契约/隔离模型/脱敏策略/审计事件/错误模型/测试计划）？
- [x] 是否明确结构化错误模型字段，且对外 `message` 为英文？
- [x] 是否明确 Evidence/审计/日志的默认脱敏边界与“可展开”的授权条件？
- [x] 是否强调真实集成测试（不可 skip）并给出单元/冒烟测试命令？
