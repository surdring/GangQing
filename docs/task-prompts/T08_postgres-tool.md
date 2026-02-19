### Task 8 - 实现 Postgres 只读查询工具（Umbrella）

```markdown
# Context
你正在执行第 8 号任务：实现 Postgres 只读查询工具（模板化 SQL + 仅 SELECT + 证据对象输出）。
角色：**技术负责人/架构师**。
目标是规划工具接口、参数 schema、只读约束（仅 SELECT）、字段白名单、行级过滤（scope）、超时策略、审计与 Evidence 输出形态，并明确测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default（强制）**: 工具必须只读；禁止任何写入。
- **Schema 单一事实源（强制）**: 工具参数与输出使用 Pydantic；对外输出前进行 schema 校验。
- **RBAC + 数据域过滤（强制）**: 工具层必须校验 capability 并默认叠加 scope 过滤。
- **Evidence-First（强制）**: 工具输出必须生成 Evidence（含 `timeRange/filters/extracted_at` 等可追溯字段）。
- **结构化错误（强制）**: 超时返回 `UPSTREAM_TIMEOUT`；契约违规 `CONTRACT_VIOLATION`。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R8.1）
- TDD: docs/design.md（2.5.2/3.3/6.3）
- tasks: docs/tasks.md（任务 8）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 8.1（工具参数与模板化查询）
- 参数模型：时间范围、实体/指标选择、过滤条件（脱敏）。
- 查询模板：避免模型自由拼接 SQL。

2) Task 8.2（只读与安全）
- 只允许 SELECT；字段白名单；scope 过滤与 RBAC。

3) Task 8.3（Evidence 与审计）
- 输出 Evidence + tool call trace；审计记录脱敏参数摘要与耗时。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/postgres_tool_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 8.1 - Postgres 只读查询工具：模板化查询 + Evidence 输出

```markdown
# Context
你正在执行子任务：8.1 - Postgres 只读查询工具：模板化查询 + Evidence 输出。
目标是实现只读查询工具，并把查询结果与 Evidence/审计绑定到 `requestId`。

# Critical Rules
- **仅 SELECT**: 任何非 SELECT 必须被拒绝并返回结构化错误。
- **RBAC + scope**: capability 与 `tenantId/projectId` 强制。
- **Evidence**: 输出必须含 `timeRange/filters/extracted_at/sourceLocator`。

# References
- PRD: docs/requirements.md（R8.1）
- tasks: docs/tasks.md（8.1）
- contracts: docs/contracts/api-and-events-draft.md（Evidence/ErrorResponse）

# Execution Plan
1) 定义工具参数 Pydantic schema。
2) 实现模板化查询生成与参数化执行。
3) 生成 Evidence 与审计事件。

# Verification
- **Unit**: `pytest -q` 覆盖：拒绝非 SELECT；缺 scope/越权拒绝。
- **Smoke**: `backend/scripts/postgres_tool_smoke_test.py`

# Output Requirement
输出所有修改/新增文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求？（工具只读）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
