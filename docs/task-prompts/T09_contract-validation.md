### Task 9 - 工具参数 schema 校验与契约校验（Pydantic 单一事实源）（Umbrella）

```markdown
# Context
你正在执行第 9 号任务：工具参数 schema 校验与契约校验（Pydantic 单一事实源）。
你是 GangQing（钢擎）项目负责落地与验收的工程师，角色为 **技术负责人/架构师**。
目标是规划“输入参数校验 + 输出结果校验 + 失败映射与审计”的统一机制，确保工具链与模型输出不会发生契约漂移。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源（强制）**: 工具参数/工具输出/对外响应/Evidence/审计事件必须以 **Pydantic** 为单一事实源；前端对应事件/响应解析以 **Zod** 对齐。
- **结构化错误（强制）**: 
  - 参数无效 => `VALIDATION_ERROR`
  - 输出不符合契约 => `CONTRACT_VIOLATION`
  - `message` 必须英文，包含 `code/message/details?/retryable/requestId`。
- **RBAC + 审计 + requestId 贯穿（强制）**: 任何校验失败必须写审计，并能按 `requestId` 聚合。
- **真实集成测试（No Skip）**: 冒烟脚本必须连接真实服务，缺配置/依赖不可用必须失败。

# References
- PRD: docs/requirements.md（R8.2/R9.3）
- TDD: docs/design.md（6.1/7.4）
- tasks: docs/tasks.md（任务 9）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# Execution Plan
1) Task 9.1（工具入参校验与错误映射）
- 统一校验入口；失败返回 `VALIDATION_ERROR`，并补齐 `details`（去敏）。

2) Task 9.2（工具输出/模型输出契约校验）
- 输出前 Pydantic 校验；失败返回 `CONTRACT_VIOLATION`；写审计与日志。

3) Task 9.3（契约测试与门禁）
- 单元：覆盖校验失败路径；冒烟：触发一次校验失败并断言结构化错误。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/contract_validation_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 9.1 - 工具入参校验：Pydantic schema + `VALIDATION_ERROR`

```markdown
# Context
你正在执行子任务：9.1 - 工具入参校验：Pydantic schema + `VALIDATION_ERROR`。
目标是在工具层建立统一的参数校验机制，并确保错误结构化、可审计。

# Critical Rules
- **Pydantic 单一事实源**: 工具参数必须 Pydantic 校验。
- **结构化错误**: 校验失败返回 `VALIDATION_ERROR` + 英文 `message` + `requestId`。
- **审计**: 记录失败阶段与工具名（`toolName`）、`stepId`（如有）。

# References
- tasks: docs/tasks.md（9.1）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse）

# Execution Plan
1) 为每个工具定义参数 Pydantic 模型；在调用入口统一 `model_validate`。
2) 将 Pydantic 校验异常映射为 `VALIDATION_ERROR`。
3) 确保 `details` 不包含敏感信息。

# Verification
- **Unit**: `pytest -q` 覆盖：非法参数 -> `VALIDATION_ERROR`。
- **Smoke**: `backend/scripts/contract_validation_smoke_test.py` 覆盖：触发一次非法参数调用并失败。

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Task 9.2 - 工具输出/模型输出契约校验：`CONTRACT_VIOLATION`

```markdown
# Context
你正在执行子任务：9.2 - 工具输出/模型输出契约校验：`CONTRACT_VIOLATION`。
目标是对“即将对外输出”的数据进行 schema 断言，避免下游解析失败。

# Critical Rules
- **输出前必须校验**: Pydantic 校验失败必须阻断输出。
- **结构化错误**: 返回 `CONTRACT_VIOLATION`，英文 `message`。
- **审计**: 记录违规字段摘要与来源模块（去敏）。

# References
- PRD: docs/requirements.md（R9.3）
- tasks: docs/tasks.md（9.2）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 定义工具输出/模型输出 Pydantic 模型。
2) 输出前进行校验；失败映射 `CONTRACT_VIOLATION`。
3) 在 SSE `error` 事件中保持同构错误模型。

# Verification
- **Unit**: `pytest -q` 覆盖：缺字段/类型错误 -> `CONTRACT_VIOLATION`。
- **Smoke**: `backend/scripts/contract_validation_smoke_test.py`（确保真实服务可触发并断言）。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局约束保留）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
