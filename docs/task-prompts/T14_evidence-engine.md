### Task 14 - 证据链引擎：Claim/Citation/Lineage/ToolCallTrace 组装与增量更新（Umbrella）

```markdown
# Context
你正在执行第 14 号任务：证据链引擎：Claim/Citation/Lineage/ToolCallTrace 组装与增量更新。
角色：**技术负责人/架构师**。
目标是规划证据链核心数据结构、组装规则、增量更新事件、降级语义与测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 数值回答必须绑定 citation+time_range；计算必须绑定 `lineage_version`。
- **不可验证必须降级（强制）**: 输出 `warning` 事件并在最终答复明确不确定。
- **Schema 单一事实源（强制）**: Evidence/Claim/审计事件后端 Pydantic；前端解析 Zod。
- **RBAC + 脱敏（强制）**: Evidence 默认脱敏。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R2.2/R6.2/R14.4）
- TDD: docs/design.md（3.3/5.1）
- tasks: docs/tasks.md（任务 14）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 14.1（证据链数据模型：Claim/Citation/Lineage/ToolCallTrace）
2) Task 14.2（增量更新：`evidence.update` 事件与前端渲染契约）
3) Task 14.3（降级策略：缺证据/不一致/越界）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/evidence_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 14.1 - EvidenceChain 组装规则与校验

```markdown
# Context
你正在执行子任务：14.1 - EvidenceChain 组装规则与校验。
目标是实现证据链组装与一致性校验，并在不满足规则时触发降级。

# Critical Rules
- **数值必须有证据**。
- **lineage_version 强制**（计算型结论）。
- **结构化 warning/error**。

# References
- tasks: docs/tasks.md（14.1）
- contracts: docs/contracts/api-and-events-draft.md（Evidence）

# Execution Plan
1) 定义 Pydantic EvidenceChain 模型。
2) 实现校验器：缺 citation/time_range -> 标记 not_verifiable。

# Verification
- **Unit**: `pytest -q` 覆盖：缺证据触发降级。
- **Smoke**: `backend/scripts/evidence_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 14.2 - Evidence 增量更新：SSE `evidence.update`

```markdown
# Context
你正在执行子任务：14.2 - Evidence 增量更新：SSE `evidence.update`。
目标是工具返回后立刻输出可渲染的证据增量，支持 Context Panel 实时更新。

# Critical Rules
- **SSE 事件可解析**: schema 对齐 contracts。
- **脱敏**: 默认脱敏。

# References
- PRD: docs/requirements.md（R6.2）
- tasks: docs/tasks.md（14.2）
- contracts: docs/contracts/api-and-events-draft.md（SSE/Evidence）

# Execution Plan
1) 定义 evidence.update payload 结构（增量 or 引用）。
2) 在工具调用完成时发出事件，并携带 `requestId`。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/evidence_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（本任务核心）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
