# Task 25 - 知识图谱（可选增强）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 25 组任务：知识图谱（可选增强）：设备-故障-现象-备件-工艺-事件 的关系抽取与多跳检索。
你的角色是 **技术负责人/架构师**。
你的目标是定义图谱数据模型与权限域、增量更新、以及多跳检索的 evidence 路径表达。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端对外 I/O/配置用 Zod；后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic。
- **Evidence-First**: 多跳推理必须附带可追溯路径与引用（节点/边来源、时间范围、版本）。
- **RBAC + 审计 + requestId 贯穿**: 图谱查询必须按权限域隔离并审计。
- **结构化错误**: message 英文，字段齐全。
- **配置外部化**: 图数据库/存储连接配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实图谱存储；缺配置必须失败并英文报错。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#47）
- tasks: `docs/tasks.md`（Task 25）

# Execution Plan
1) Task 25.1 - 图谱数据模型与存储选型（权限域隔离）
2) Task 25.2 - 关系抽取/增量更新管线（审计）
3) Task 25.3 - 多跳检索 API/工具：返回可追溯路径（Evidence）
4) Task 25.4 - 冒烟：kg_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/kg_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 25.1 - 数据层：图谱 schema（节点/边）与权限域

```markdown
# Context
你正在执行子任务：25.1 - 图谱 schema。
你的目标是建立节点/边模型、权限域字段与查询索引。

# Critical Rules
- **Schema 单一事实源**: 模型用 Pydantic。
- **RBAC**: 权限域必须作为查询过滤默认条件。

# References
- tasks: `docs/tasks.md`（Task 25）

# Execution Plan
1) 定义节点类型与边类型。
2) 定义权限域字段。

# Verification
- 单元测试：无权限域访问被拒。

# Output Requirement
- 输出代码与测试。
```

### Task 25.2 - 增量更新：抽取->写入（受控写入 + 审计）

```markdown
# Context
你正在执行子任务：25.2 - 图谱增量更新。
你的目标是实现增量更新管线，写入必须审计且可回放。

# Critical Rules
- **Read-Only Default**: 图谱写入属于受控数据写入，需要权限与审计；不触发任何 OT 控制写操作。
- **结构化错误**: message 英文。

# References
- tasks: `docs/tasks.md`（Task 25）

# Execution Plan
1) 定义更新事件模型。
2) 写入审计日志。

# Verification
- 单元测试：写入审计字段存在。

# Output Requirement
- 输出代码与测试。
```

### Task 25.3 - 多跳检索：可追溯路径输出（Evidence）

```markdown
# Context
你正在执行子任务：25.3 - 多跳检索。
你的目标是实现多跳检索并输出 evidence：路径上的节点/边来源与引用。

# Critical Rules
- **Evidence-First**: 必须输出可追溯路径。

# References
- tasks: `docs/tasks.md`（Task 25）

# Execution Plan
1) 定义输出模型：path_nodes/path_edges + citations。
2) 组装 evidence。

# Verification
- 单元：path 与 citations 非空。

# Output Requirement
- 输出代码与测试。
```

### Task 25.4 - 冒烟：kg_smoke_test.py

```markdown
# Context
你正在执行子任务：25.4 - KG 冒烟。
你的目标是连接真实图谱存储并跑一条多跳检索链路。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 25）

# Execution Plan
1) 探活图谱存储。
2) 发起多跳查询并断言 evidence。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（多跳路径引用）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（图谱写入为受控数据写入）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
