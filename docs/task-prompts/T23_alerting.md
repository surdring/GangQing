### Task 23 - 异常主动推送与告警升级（库存/设备报警/成本超标）：可订阅与可审计（Umbrella）

```markdown
# Context
你正在执行第 23 号任务：异常主动推送与告警升级（库存/设备报警/成本超标）：可订阅与可审计。
角色：**技术负责人/架构师**。
目标是规划告警规则（阈值配置化）、订阅机制（SSE/站内通知）、告警升级策略、审计字段与测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **配置外部化（强制）**: 阈值、升级策略、通道开关不得硬编码。
- **RBAC + 审计（强制）**: 告警订阅与推送都要权限检查并写审计。
- **结构化错误（强制）**: 错误模型字段齐全，英文 message。
- **Evidence-First**: 告警触发必须可追溯到数据源与时间范围；Evidence 中体现阈值版本/规则 ID（摘要）。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R2.4）
- TDD: docs/design.md（2.4.1）
- tasks: docs/tasks.md（任务 23）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 23.1（告警规则与阈值配置）
2) Task 23.2（推送通道：SSE/站内通知）
3) Task 23.3（审计与证据链）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/alerting_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 23.1 - 告警规则：阈值配置化 + 升级策略

```markdown
# Context
你正在执行子任务：23.1 - 告警规则：阈值配置化 + 升级策略。

# Critical Rules
- **配置外部化**。
- **Evidence**: 告警必须有数据源与时间范围。

# References
- tasks: docs/tasks.md（23.1）
- PRD: docs/requirements.md（R2.4）

# Execution Plan
1) 定义规则模型与阈值配置 schema。
2) 实现升级：未处理升级告警级别。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/alerting_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
