### Task 41 - 沙箱仿真与培训模式：明确沙箱标识、模拟执行与后果推演、培训案例沉淀（Umbrella）

```markdown
# Context
你正在执行第 41 号任务：沙箱仿真与培训模式。
角色：**技术负责人/架构师**。
目标是规划沙箱隔离边界（不影响真实生产）、模拟工具链、风险提示与规程引用、培训案例沉淀与权限控制。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **安全隔离（强制）**: 沙箱必须与真实生产隔离，禁止任何 OT 写入与真实写操作。
- **Read-Only Default（强制）**: 沙箱仅模拟执行，不得触发真实写入。
- **Evidence-First（强制）**: 推演结果与风险提示必须可追溯（引用规程/历史案例/模拟规则版本）。
- **RBAC + 审计（强制）**: 进入沙箱/执行模拟/导出案例都需权限与审计。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**: 冒烟需验证沙箱标识、隔离与模拟链路。

# References
- PRD: docs/requirements.md（R5.5）
- TDD: docs/design.md（3.6）
- tasks: docs/tasks.md（任务 41）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 41.1（沙箱模式开关与隔离策略）
2) Task 41.2（模拟执行与后果推演模型）
3) Task 41.3（培训案例沉淀与权限）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/sandbox_training_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 41.1 - 沙箱隔离：显式标识 + 禁止真实写入

```markdown
# Context
你正在执行子任务：41.1 - 沙箱隔离：显式标识 + 禁止真实写入。

# Critical Rules
- **必须有沙箱标识**。
- **必须阻断真实写入**。

# References
- tasks: docs/tasks.md（41.1）

# Execution Plan
1) 定义 SandboxContext schema。
2) 在写路径入口统一阻断。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/sandbox_training_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（推演引用）
- [x] 只读默认与审批链？（沙箱仅模拟）
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
