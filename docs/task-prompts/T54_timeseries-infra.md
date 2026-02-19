### Task 54 - （L3+）数据基础设施演进：工业时序数据接入与冷热分层（支撑事件对齐与分析链路）（Umbrella）

```markdown
# Context
你正在执行第 54 号任务：数据基础设施演进：工业时序数据接入与冷热分层。
角色：**技术负责人/架构师**。
目标是规划时序数据存储与查询策略、冷热分层、与事件模型/时间对齐的集成点，以及权限隔离与证据链要求。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Isolation（强制）**: 时序数据读写必须按 `tenantId/projectId` 隔离。
- **Evidence-First（强制）**: 时序查询结果必须可追溯（点位/系统/时间窗口/对齐规则版本）。
- **结构化错误**: 英文 message。
- **配置外部化（强制）**: 数据源地址、窗口大小、冷热分层策略不得硬编码。
- **真实集成测试（No Skip）**: 冒烟必须连接真实时序数据服务（按环境变量）。

# References
- PRD: docs/requirements.md（R16.2）
- TDD: docs/design.md（2.6/5.4）
- tasks: docs/tasks.md（任务 54）

# Execution Plan
1) Task 54.1（时序接入：点位模型/采样/质量码）
2) Task 54.2（冷热分层：存储/查询策略）
3) Task 54.3（与时间对齐/分析链路集成）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/timeseries_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 54.1 - 时序数据接入：点位模型 + 质量码 + Evidence

```markdown
# Context
你正在执行子任务：54.1 - 时序数据接入：点位模型 + 质量码 + Evidence。

# Critical Rules
- **质量码与评分**: 与 `docs/api/data-api.md` 的 `quality_code` 语义一致。

# References
- tasks: docs/tasks.md（54.1）
- api docs: docs/api/data-api.md

# Execution Plan
1) 定义点位数据 schema。
2) 输出 evidence 记录采样窗口与质量摘要。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/timeseries_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
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
