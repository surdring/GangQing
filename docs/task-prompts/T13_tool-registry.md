### Task 13 - 编排层：工具链注册与 Function Calling（可控调用 + 可追溯证据）（Umbrella）

```markdown
# Context
你正在执行第 13 号任务：编排层：工具链注册与 Function Calling（可控调用 + 可追溯证据）。
角色：**技术负责人/架构师**。
目标是规划工具注册机制、可用工具集合的门禁（角色+意图+数据域）、SSE 事件输出（tool.call/tool.result）、以及与 Evidence/审计绑定。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **工具白名单（强制）**: 可用工具集合必须由“角色 + 意图 + 数据域”决定，禁止模型自由调用任意工具。
- **Schema 单一事实源（强制）**: 工具参数/输出 Pydantic；对外事件/响应对齐 contracts。
- **Evidence-First（强制）**: 每次工具调用必须产出 Evidence 或可追溯引用。
- **RBAC + 审计 + requestId（强制）**。
- **结构化错误（强制）**: 工具失败必须输出结构化 `error` 事件，并随后 `final`（按 contracts）。

# References
- PRD: docs/requirements.md（R15.3）
- TDD: docs/design.md（2.5.3/3.5.1）
- tasks: docs/tasks.md（任务 13）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 13.1（工具注册：配置化目录与元数据）
2) Task 13.2（门禁：allowed tools 计算与校验）
3) Task 13.3（SSE 事件：tool.call/tool.result + 审计）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/tool_registry_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 13.1 - 工具注册：配置化工具目录与元数据

```markdown
# Context
你正在执行子任务：13.1 - 工具注册：配置化工具目录与元数据。
目标是实现工具注册表，使编排层能枚举工具、声明参数 schema 与能力边界。

# Critical Rules
- **配置外部化**: 工具启用/禁用、超时等通过配置。
- **审计**: 记录每次工具调用的 toolName 与参数摘要（脱敏）。

# References
- tasks: docs/tasks.md（13.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 定义工具元数据模型（Pydantic）。
2) 实现注册与发现。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/tool_registry_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 13.2 - 工具调用事件输出：`tool.call`/`tool.result` + 结构化错误

```markdown
# Context
你正在执行子任务：13.2 - 工具调用事件输出：`tool.call`/`tool.result` + 结构化错误。
目标是让前端可分段渲染工具阶段，并可追溯到 Evidence。

# Critical Rules
- **SSE**: 事件字段必须与 contracts 对齐。
- **错误事件结构化**: `error` payload 为 ErrorResponse。

# References
- PRD: docs/requirements.md（R6.1）
- tasks: docs/tasks.md（13.2）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 在编排层工具调用包装器中发出 `tool.call`。
2) 成功时发出 `tool.result`（脱敏摘要 + evidence 引用）。
3) 失败时发出 `error` + `final`。

# Verification
- **Unit**: `pytest -q` 覆盖事件序列。
- **Smoke**: `backend/scripts/tool_registry_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（tool->evidence 绑定）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
