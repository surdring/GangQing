### Task 12 - 实现意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）（Umbrella）

```markdown
# Context
你正在执行第 12 号任务：实现意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）。
角色：**技术负责人/架构师**。
目标是规划意图分类输出契约、置信度与澄清策略、以及高风险意图拦截（只读默认）与审计。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default（强制）**: 写操作倾向必须进入只读默认流程，禁止直接执行。
- **意图不明确必须澄清（强制）**: 不得猜测执行。
- **结构化错误（强制）**: 高风险拦截返回 `GUARDRAIL_BLOCKED` 或 `FORBIDDEN`（按 contracts），英文 `message`。
- **RBAC + 审计 + requestId 贯穿（强制）**。
- **Schema 单一事实源（强制）**: 意图输出结构化模型（Pydantic），对外事件/响应与 Zod 对齐。

# References
- PRD: docs/requirements.md（R15.1/R5.1）
- TDD: docs/design.md（2.4/3.9）
- tasks: docs/tasks.md（任务 12）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 12.1（意图模型与输出契约）
- 输出：意图类别 + 置信度 + 需要澄清时的澄清问题结构。

2) Task 12.2（策略路由：工具白名单 + 写意图拦截）
- 角色+意图+数据域联合决定可用工具。

3) Task 12.3（测试与验收）
- 单元覆盖：不明确 -> 澄清；写意图 -> 拦截。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/intent_routing_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 12.1 - 意图识别输出：类别 + 置信度 + 澄清

```markdown
# Context
你正在执行子任务：12.1 - 意图识别输出：类别 + 置信度 + 澄清。
目标是实现意图识别模块，产出结构化结果并可被审计与观测。

# Critical Rules
- **不明确必须澄清**。
- **结构化输出**: Pydantic 模型校验。
- **审计**: 记录意图结果与置信度（去敏）。

# References
- tasks: docs/tasks.md（12.1）
- TDD: docs/design.md（2.4.1/3.9）

# Execution Plan
1) 定义 Pydantic 模型：IntentResult。
2) 实现识别逻辑与澄清问题生成。

# Verification
- **Unit**: `pytest -q` 覆盖：模糊输入 -> 需要澄清。
- **Smoke**: `backend/scripts/intent_routing_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 12.2 - 策略路由：写意图拦截与只读默认

```markdown
# Context
你正在执行子任务：12.2 - 策略路由：写意图拦截与只读默认。
目标是将意图结果转为工具调用策略，写相关意图必须拦截或生成草案（L4）。

# Critical Rules
- **Read-Only Default**。
- **RBAC**: 任何工具调用都必须 capability 校验。
- **结构化错误**: 拦截使用 `GUARDRAIL_BLOCKED`（或 contracts 指定）。

# References
- PRD: docs/requirements.md（R5.1/R15.1）
- tasks: docs/tasks.md（12.2）

# Execution Plan
1) 实现路由表：intent -> allowed tools。
2) ACTION_* 意图输出“需要审批/草案”的结构化响应。

# Verification
- **Unit**: `pytest -q` 覆盖：ACTION_EXECUTE -> 拦截。
- **Smoke**: `backend/scripts/intent_routing_smoke_test.py`。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局约束保留）
- [x] 是否包含只读默认与审批链要求？（强制出现）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
