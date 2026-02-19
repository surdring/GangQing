### Task 4 - 落地数据域隔离与脱敏策略（Umbrella）

```markdown
# Context
你正在执行第 4 号任务：落地数据域隔离与脱敏策略（默认过滤 + 字段级脱敏 + 可审计）。
你的角色是 **技术负责人/架构师**。
目标是规划隔离维度（`tenantId/projectId`/产线等）、默认过滤规则、字段级脱敏策略、审计记录方式与测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Isolation（强制）**: 所有数据读写必须默认按 `tenantId/projectId` 过滤；检测到跨隔离访问返回 `AUTH_ERROR` 并写审计。
- **脱敏（强制）**: 财务/工艺参数/敏感配方等按角色脱敏；证据链展示默认脱敏。
- **RBAC + 审计 + requestId 贯穿（强制）**。
- **结构化错误（强制）**。
- **Schema 单一事实源（强制）**。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R1.3/R10.2）
- TDD: docs/design.md（4.4）
- tasks: docs/tasks.md（任务 4）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 4.1（数据域过滤：工具层强制叠加）
- 定义过滤注入点：所有工具查询必须带 scope 条件。

2) Task 4.2（字段级脱敏：按角色配置）
- 定义字段白名单/脱敏规则配置方式与审计记录字段。

3) Task 4.3（审计与证据展示策略）
- 审计记录“命中策略/脱敏摘要”，禁止记录敏感原文。

# Verification
- Unit: `pytest -q` 覆盖：跨域访问被拒、脱敏规则生效。
- Smoke: `backend/scripts/rbac_and_masking_smoke_test.py`。

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
- **Isolation（强制）**: 缺少 `X-Tenant-Id/X-Project-Id` 返回 `AUTH_ERROR`。
- **审计（强制）**: 记录过滤命中信息摘要。

# References
- PRD: docs/requirements.md（R1.3）
- tasks: docs/tasks.md（4.1）
- contracts: docs/contracts/api-and-events-draft.md（1/2）

# Execution Plan
1) 在工具层统一入口注入 scope 过滤条件。
2) 增加跨域访问检测与错误映射（`AUTH_ERROR`）。

# Verification
- **Unit**: `pytest -q`（缺 scope/跨 scope 必须失败）。
- **Smoke**: `backend/scripts/rbac_and_masking_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
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

# References
- PRD: docs/requirements.md（R10.2）
- tasks: docs/tasks.md（4.2）

# Execution Plan
1) 定义角色 -> 字段白名单/脱敏策略配置。
2) 在响应序列化前应用脱敏（含 Evidence 展示字段）。

# Verification
- **Unit**: `pytest -q` 覆盖：不同角色返回字段差异。
- **Smoke**: `backend/scripts/rbac_and_masking_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（Evidence 默认脱敏与可追溯要求已包含）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
