### Task 50 - （L2）设备诊疗专家外部系统接入：EAM 工单/备件/BOM 只读连接器与证据链输出（Umbrella）

```markdown
# Context
你正在执行第 50 号任务：EAM 工单/备件/BOM 只读连接器接入。
角色：**技术负责人/架构师**。
目标是规划连接器参数 schema、只读边界、字段脱敏、RBAC、Evidence 输出与超时重试策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default（强制）**: 连接器只读。
- **Schema 单一事实源（强制）**: 工具参数/输出 Pydantic。
- **RBAC + 脱敏 + 审计（强制）**。
- **Evidence-First（强制）**: 输出 Evidence，含 sourceSystem=EAM、timeRange、sourceLocator。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R3.2/R3.3）
- TDD: docs/design.md（2.5.3）
- tasks: docs/tasks.md（任务 50）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 50.1（EAM 连接器：配置与参数校验）
2) Task 50.2（只读查询与 Evidence 输出）
3) Task 50.3（冒烟：真实 EAM 服务连接）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/eam_connector_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 50.1 - EAM 只读连接器：参数校验 + 超时 + Evidence

```markdown
# Context
你正在执行子任务：50.1 - EAM 只读连接器：参数校验 + 超时 + Evidence。

# Critical Rules
- **配置外部化**: HOST/PORT/timeout。
- **参数脱敏**。

# References
- tasks: docs/tasks.md（50.1）

# Execution Plan
1) 定义 Pydantic 参数模型。
2) 实现只读查询与 evidence.

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/eam_connector_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（EAM evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
