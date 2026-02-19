### Task 47 - （L1）前端 Context Panel 强化：“证据缺失/不可验证/降级态”表达与可追溯展开（Umbrella）

```markdown
# Context
你正在执行第 47 号任务：前端 Context Panel 强化。
角色：**技术负责人/架构师**。
目标是规划 Context Panel 的状态模型（完整/缺失/冲突/降级）、可追溯展开交互、与后端 warning/evidence 事件对齐。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 只展示可追溯证据；不可验证必须显式 UI 表达。
- **Schema 单一事实源**: 前端对外数据结构用 Zod。
- **TypeScript Strict**。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R6.2/R14.4/R13.3）
- TDD: docs/design.md（5.1）
- tasks: docs/tasks.md（任务 47）

# Execution Plan
1) Task 47.1（Evidence UI 状态：缺失/冲突/降级）
2) Task 47.2（可追溯展开：sourceLocator/timeRange/lineageVersion）

# Verification
- Unit: `npm -C web test`
- Smoke: `npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 47.1 - Context Panel：证据缺失/不可验证/降级态 UI

```markdown
# Context
你正在执行子任务：47.1 - Context Panel：证据缺失/不可验证/降级态 UI。

# Critical Rules
- **不得展示伪造引用**。

# References
- tasks: docs/tasks.md（47.1）

# Execution Plan
1) 定义 EvidenceViewModel schema（Zod）。
2) 根据 `validation`/`warning` 渲染 UI。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（本任务核心）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
