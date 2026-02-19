### Task 3 - 建立认证与权限：JWT 登录 + RBAC 权限检查（Umbrella）

```markdown
# Context
你正在执行第 3 号任务：建立认证与权限：JWT 登录 + RBAC 权限检查（API 与工具双层门禁）。
你是 GangQing（钢擎）项目负责落地与验收的工程师，角色为 **技术负责人/架构师**。
目标是规划认证、权限模型、能力点（capabilities）、拒绝策略、审计字段与测试口径，确保后续实现不会出现绕过 RBAC 或审计缺失。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **RBAC + 审计（强制）**: 所有 API 与工具调用必须权限检查并记录审计。
- **requestId 贯穿（强制）**。
- **结构化错误（强制）**: `code/message(英文)/details?/retryable/requestId`。
- **Read-Only Default（强制）**: 未授权不得执行写操作。
- **Schema 单一事实源**: 前端 Zod；后端 Pydantic。
- **真实集成测试（No Skip）**: `backend/scripts/auth_smoke_test.py` 必须连接真实服务并失败即失败。

# References
- PRD: docs/requirements.md（R1.1/R1.2/R5.1/R11.1）
- TDD: docs/design.md（3.1/6.1）
- tasks: docs/tasks.md（任务 3）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# Execution Plan
1) Task 3.1（JWT 登录与 token 生命周期）
- 端点与契约：登录请求/响应、token 过期语义、错误码。

2) Task 3.2（RBAC capability 模型与双层门禁）
- API 层 capability 校验；工具层再次校验（防止绕过）。
- 能力点命名规范：`domain:resource:action`。

3) Task 3.3（审计与拒绝策略）
- 登录/鉴权失败/越权访问都要审计（至少 query/tool_call/error）。

# Verification
- Unit: `pytest -q`（覆盖登录成功/失败、越权返回 `FORBIDDEN`、缺 token 返回 `AUTH_ERROR`）。
- Smoke: `backend/scripts/auth_smoke_test.py`。

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 3.1 - JWT 登录与 token 校验

```markdown
# Context
你正在执行子任务：3.1 - JWT 登录与 token 校验。
目标是实现登录端点、token 验证依赖/中间件，并与统一错误模型、审计与 requestId 贯穿对齐。

# Critical Rules
- **结构化错误**: 无效凭证返回 `AUTH_ERROR`，英文 `message`。
- **RBAC & 审计**: 登录尝试与失败原因摘要需要写审计（禁止记录明文密码）。
- **配置外部化**: JWT secret/算法/过期时间通过配置加载并校验。
- **真实集成测试（No Skip）**: `backend/scripts/auth_smoke_test.py` 必须可运行。

# References
- PRD: docs/requirements.md（R1.1）
- tasks: docs/tasks.md（3.1）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse/RequestContext）

# Execution Plan
1) 定义 Pydantic 请求/响应模型与错误响应。
2) 实现登录端点与 token 生成。
3) 实现 token 校验依赖，并把 `userId/role` 注入 RequestContext。
4) 增补审计记录：login.success/login.failure。

# Verification
- **Unit**: `pytest -q`
  - 登录成功返回 token
  - 无效凭证返回 `AUTH_ERROR`
  - token 过期返回 `AUTH_ERROR`
- **Smoke**: `backend/scripts/auth_smoke_test.py`

# Output Requirement
输出所有修改/新增文件完整内容 + 测试命令与关键输出。
```

---

### Task 3.2 - RBAC capability 模型与 API/工具双层门禁

```markdown
# Context
你正在执行子任务：3.2 - RBAC capability 模型与 API/工具双层门禁。
目标是定义角色、capabilities 映射与校验机制，确保任何工具调用都不能绕过权限。

# Critical Rules
- **RBAC 强制**: API 与工具必须双层校验。
- **结构化错误**: 越权返回 `FORBIDDEN`。
- **审计**: 越权访问必须写审计（含 capability 缺失信息摘要）。

# References
- PRD: docs/requirements.md（R1.2）
- tasks: docs/tasks.md（3.2）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 定义角色与 capability 列表（最小闭环：厂长/调度员/维修工/财务）。
2) 实现 capability 校验依赖与工具层 guard。
3) 为关键 API/工具补齐 capability 声明。

# Verification
- **Unit**: `pytest -q` 覆盖：维修工访问财务资源返回 `FORBIDDEN`。
- **Smoke**: 在 `auth_smoke_test.py` 中增加一次越权场景断言。

# Output Requirement
输出修改文件完整内容 + 测试命令。
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
