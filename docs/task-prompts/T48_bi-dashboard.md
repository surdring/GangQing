### Task 48 - （L2）管理驾驶舱/自然语言 BI：成本卡片、瀑布图/趋势图、结构化渲染与 lineage_version 绑定（Umbrella）

```markdown
# Context
你正在执行第 48 号任务：管理驾驶舱/自然语言 BI。
角色：**技术负责人/架构师**。
目标是规划 BI 卡片与图表数据契约、后端分析型查询模板、`lineage_version` 强制绑定、以及前后端结构化渲染与证据链展示。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源（强制）**: 前端 BI 卡片/图表数据用 Zod；后端分析响应/Evidence 用 Pydantic。
- **Evidence-First（强制）**: BI 数值必须可追溯，且计算必须绑定 `lineage_version`。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R2.3/R13.4）
- TDD: docs/design.md（3.4）
- tasks: docs/tasks.md（任务 48）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 48.1（前端：成本卡片与图表 schema + 渲染）
2) Task 48.2（后端：分析查询模板与 lineage_version 绑定）
3) Task 48.3（证据链：图表与卡片的 evidence 引用）

# Verification
- Unit: `pytest -q && npm -C web test`
- Smoke: `backend/scripts/bi_query_smoke_test.py && npm -C web run build`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 48.1 - BI 卡片与图表：结构化渲染 + evidence 引用

```markdown
# Context
你正在执行子任务：48.1 - BI 卡片与图表：结构化渲染 + evidence 引用。

# Critical Rules
- **Zod schema**。
- **lineage_version 展示**。

# References
- tasks: docs/tasks.md（48.1）

# Execution Plan
1) 定义 Card/Chart schema。
2) 渲染并支持降级表达。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `npm -C web run build`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
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
