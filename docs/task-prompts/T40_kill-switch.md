### Task 40 - 写操作 Kill Switch 与熔断：一键禁用写入路径（可审计、可配置）（Umbrella）

```markdown
# Context
你正在执行第 40 号任务：写操作 Kill Switch 与熔断。
角色：**技术负责人/架构师**。
目标是规划 Kill Switch 的配置外部化、启停接口、熔断时的结构化错误与审计策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Kill Switch（强制）**: 开启后所有写相关请求必须被阻断。
- **审计（强制）**: 启停操作必须写审计并可告警。
- **结构化错误（强制）**: 被熔断的写请求返回结构化错误（英文 message）。
- **RBAC（强制）**: 仅管理员可启停。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R5.4）
- TDD: docs/design.md（2.9）
- tasks: docs/tasks.md（任务 40）
- contracts: docs/contracts/api-and-events-draft.md（10 Kill Switch）

# Execution Plan
1) Task 40.1（Kill Switch 状态模型与配置）
2) Task 40.2（启停接口与 RBAC）
3) Task 40.3（熔断阻断与错误映射）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/kill_switch_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 40.1 - Kill Switch：启停与阻断写路径

```markdown
# Context
你正在执行子任务：40.1 - Kill Switch：启停与阻断写路径。

# Critical Rules
- **管理员权限**。
- **阻断必须可审计**。

# References
- tasks: docs/tasks.md（40.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 定义状态存储与读写接口。
2) 在写路径入口统一检查 Kill Switch。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/kill_switch_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（启停/阻断审计）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？（启停需 requestId）
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
