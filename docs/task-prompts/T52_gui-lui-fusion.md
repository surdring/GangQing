### Task 52 - （L2）GUI/LUI 融合：圈选提问（图表/报表圈选）与证据定位高亮（Umbrella）

```markdown
# Context
你正在执行第 52 号任务：GUI/LUI 融合：圈选提问与证据定位高亮。
角色：**技术负责人/架构师**。
目标是规划圈选上下文（clientContext）契约、后端绑定 Evidence、前端高亮定位交互，以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源（强制）**: clientContext/事件/配置前端 Zod；后端 Pydantic。
- **Evidence-First（强制）**: 圈选上下文必须绑定证据与可追溯引用；高亮定位不得伪造引用。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R13.4）
- TDD: docs/design.md（2.2）
- tasks: docs/tasks.md（任务 52）
- contracts: docs/contracts/api-and-events-draft.md（chat clientContext）

# Execution Plan
1) Task 52.1（clientContext schema：选区/图表元素引用）
2) Task 52.2（证据定位：evidenceId/sourceLocator 映射到 UI 高亮）
3) Task 52.3（E2E 冒烟：圈选->提问->证据高亮）

# Verification
- Unit: `npm -C web test && pytest -q`
- Smoke: `npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 52.1 - 圈选上下文：Zod schema + 后端 Pydantic 对齐

```markdown
# Context
你正在执行子任务：52.1 - 圈选上下文：Zod schema + 后端 Pydantic 对齐。

# Critical Rules
- **不得出现 any**。

# References
- tasks: docs/tasks.md（52.1）

# Execution Plan
1) 定义 Zod schema 并推导类型。
2) 后端定义对应 Pydantic 模型。

# Verification
- **Unit**: `npm -C web test && pytest -q`
- **Smoke**: `backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（证据高亮）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
