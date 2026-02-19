### Task 17 - 审计落库与不可篡改策略（append-only + 查询也要被审计）（Umbrella）

```markdown
# Context
你正在执行第 17 号任务：审计落库与不可篡改策略（append-only + 查询也要被审计）。
角色：**技术负责人/架构师**。
目标是规划审计事件模型、落库策略（append-only）、审计查询的二次审计、权限边界，以及与 `requestId` 贯穿的对齐方式。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **RBAC + 审计（强制）**: 审计查询本身也必须写审计；审计数据访问必须受控。
- **append-only（强制）**: 审计写入不可修改/不可删除（至少在应用层强制 + DB 权限策略）。
- **结构化错误（强制）**: 统一错误模型，英文 `message`。
- **Schema 单一事实源（强制）**: 审计事件对外/对内使用 Pydantic；前端展示与导出对齐 Zod（如适用）。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R11.1/R11.2）
- TDD: docs/design.md（2.8.1）
- tasks: docs/tasks.md（任务 17）
- contracts: docs/contracts/api-and-events-draft.md（4 Audit Event）

# Execution Plan
1) Task 17.1（审计事件类型与最小字段）
2) Task 17.2（落库与 append-only 策略）
3) Task 17.3（审计查询与二次审计）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/audit_log_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 17.1 - 审计事件模型：query/tool_call/response/error（预留 approval/write_operation）

```markdown
# Context
你正在执行子任务：17.1 - 审计事件模型。
目标是实现审计事件 Pydantic 模型与落库接口，确保能按 `requestId` 聚合。

# Critical Rules
- **字段最小集合**: `eventType/timestamp/requestId/tenantId/projectId/userId/role/resource/actionSummary/result`。
- **脱敏**: `actionSummary` 必须脱敏。

# References
- tasks: docs/tasks.md（17.1）
- contracts: docs/contracts/api-and-events-draft.md（4.2）

# Execution Plan
1) 定义 Pydantic 审计事件模型。
2) 实现审计写入接口（append-only）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/audit_log_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Task 17.2 - append-only 与权限：不可篡改与受控读取

```markdown
# Context
你正在执行子任务：17.2 - append-only 与权限：不可篡改与受控读取。

# Critical Rules
- **append-only**。
- **RBAC**: 只有审计员/管理员可读（按能力点约束）。

# References
- PRD: docs/requirements.md（R11.2）
- tasks: docs/tasks.md（17.2）

# Execution Plan
1) DB 权限策略：应用账号仅 INSERT。
2) 读接口进行 capability 校验。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/audit_log_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（审计应可引用 evidenceId/摘要，按项目实现）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（本任务核心）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
