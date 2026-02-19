### Task 53 - （L2+）工具链扩展：ERP/MES/DCS/LIMS 连接器规范化接入（统一参数校验、超时重试、脱敏、审计、Evidence）（Umbrella）

```markdown
# Context
你正在执行第 53 号任务：工具链扩展：连接器规范化接入。
角色：**技术负责人/架构师**。
目标是规划连接器适配模板（统一参数校验、超时重试、脱敏、审计、Evidence）、能力矩阵与观测字段，并确保只读默认。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Read-Only Default（强制）**: 默认只读连接器；写能力必须走 L4 治理。
- **Schema 单一事实源（强制）**: 工具参数/输出 Pydantic。
- **超时重试/错误映射（强制）**: `UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE` 等。
- **脱敏 + 审计 + requestId（强制）**。
- **Evidence-First（强制）**: 每次连接器调用必须生成 Evidence。
- **真实集成测试（No Skip）**: 必须连真实外部系统（按环境变量配置）；缺配置必须失败。

# References
- PRD: docs/requirements.md（R15.3）
- TDD: docs/design.md（2.5.3）
- tasks: docs/tasks.md（任务 53）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/data-api.md（connectors list）

# Execution Plan
1) Task 53.1（连接器模板：参数校验/超时/重试/脱敏/审计）
2) Task 53.2（能力矩阵与工具注册）
3) Task 53.3（冒烟：真实连接器集成）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/connectors_integration_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 53.1 - 连接器规范：统一参数校验、超时重试、脱敏、审计、Evidence

```markdown
# Context
你正在执行子任务：53.1 - 连接器规范：统一参数校验、超时重试、脱敏、审计、Evidence。

# Critical Rules
- **禁止 mock 外部系统**（集成测试）。
- **缺配置必须失败**。

# References
- tasks: docs/tasks.md（53.1）

# Execution Plan
1) 定义 ConnectorBase 接口与 Pydantic 模型。
2) 实现审计与 evidence 输出。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/connectors_integration_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
