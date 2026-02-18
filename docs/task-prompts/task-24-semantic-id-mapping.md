# Task 24 - 统一语义层（实体与 ID 映射）（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 24 组任务：统一语义层（实体与 ID 映射）：设备/点位/物料/炉次/订单 的全域映射与冲突治理。
你的角色是 **技术负责人/架构师**。
你的目标是定义统一 ID 模型、映射冲突治理策略、以及在 Evidence 中回填统一 ID 的规范。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 语义层对外 I/O 必须 Pydantic；前端展示用 Zod。
- **Evidence-First**: 工具查询结果与 citations 必须包含统一 ID（可用则回填），并标注映射来源。
- **RBAC + 审计 + requestId**: 映射查询也需鉴权并审计。
- **结构化错误**: message 英文。
- **配置外部化**: 外部系统 ID 映射源配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实数据源并覆盖冲突样本。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#43-46）
- tasks: `docs/tasks.md`（Task 24）

# Execution Plan
1) Task 24.1 - 映射表与冲突检测（版本化）
2) Task 24.2 - 查询工具/API：给定外部 ID -> 统一 ID
3) Task 24.3 - Evidence 回填：工具输出统一 ID
4) Task 24.4 - 冒烟：semantic_id_mapping_smoke_test.py

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/semantic_id_mapping_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 24.1 - 数据层：实体映射表 + 冲突检测

```markdown
# Context
你正在执行子任务：24.1 - 映射表与冲突检测。
你的目标是建立映射表、冲突检测规则与版本字段。

# Critical Rules
- **真实集成测试（No Skip）**: 必须真实 Postgres。

# References
- tasks: `docs/tasks.md`（Task 24）

# Execution Plan
1) 定义 mapping 表（entity_type、external_system、external_id、unified_id、valid_from/valid_to）。
2) 实现冲突检测（同 external_id 映射多个 unified_id）。

# Verification
- 单元：冲突样本检测。

# Output Requirement
- 输出迁移/SQL 与测试。
```

### Task 24.2 - 工具/API：查询统一 ID（Pydantic）

```markdown
# Context
你正在执行子任务：24.2 - 统一 ID 查询接口。
你的目标是提供查询接口返回统一 ID 与映射证据。

# Critical Rules
- **Schema 单一事实源**: 输入/输出 Pydantic。
- **RBAC + 审计**: 查询必须审计。

# References
- tasks: `docs/tasks.md`（Task 24）

# Execution Plan
1) 定义请求/响应模型。
2) 实现查询与权限过滤。

# Verification
- 单元：不存在/冲突返回结构化错误。

# Output Requirement
- 输出代码与测试。
```

### Task 24.3 - Evidence：工具结果回填 unified_id（可追溯）

```markdown
# Context
你正在执行子任务：24.3 - Evidence 回填 unified_id。
你的目标是让所有工具调用在可用时回填统一 ID，并记录映射来源。

# Critical Rules
- **Evidence-First**: 映射来源必须可追溯。

# References
- tasks: `docs/tasks.md`（Task 24）

# Execution Plan
1) 在 evidence citations 中加入 unified_id 字段。
2) 对冲突：输出 warning 并提示用户选择。

# Verification
- 单元：冲突 -> warning。

# Output Requirement
- 输出代码与测试。
```

### Task 24.4 - 冒烟：semantic_id_mapping_smoke_test.py

```markdown
# Context
你正在执行子任务：24.4 - 语义映射冒烟。
你的目标是实现冒烟脚本覆盖：正常映射与冲突映射两条路径。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置/服务不可用必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 24）

# Execution Plan
1) seed 映射与冲突样本。
2) 发起查询并断言返回/警告。

# Verification
- 冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（unified_id 回填）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
