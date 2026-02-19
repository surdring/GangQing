### Task 27 - 前端图表动态生成 + 移动端适配（弱网/离线/语音降级）（Umbrella）

```markdown
# Context
你正在执行第 27 号任务：前端图表动态生成 + 移动端适配（弱网/离线/语音降级）。
角色：**技术负责人/架构师**。
目标是规划图表组件（瀑布图/趋势/占比/表格）、移动端布局、弱网重连、离线缓存与“offline data”标识，以及语音输入降级策略。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **TypeScript Strict（强制）**: 禁止 `any`。
- **Schema 单一事实源**: 前端对外 I/O 与配置 Zod。
- **Evidence-First**: 图表数据必须可追溯到 Evidence/lineage_version；不可验证必须降级表达。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R13.4/R13.5/R18.1/R18.2）
- TDD: docs/design.md（3.11）
- tasks: docs/tasks.md（任务 27）

# Execution Plan
1) Task 27.1（图表组件与数据契约）
2) Task 27.2（移动端布局与弱网）
3) Task 27.3（离线缓存与语音降级）

# Verification
- Unit: `npm -C web test`
- Smoke: `npm -C web run build && backend/scripts/mobile_weaknet_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 27.1 - 图表动态生成：瀑布图/趋势/占比/表格

```markdown
# Context
你正在执行子任务：27.1 - 图表动态生成。

# Critical Rules
- **Zod schema**: 图表数据输入校验。
- **Evidence 引用**: 图表必须展示来源摘要。

# References
- tasks: docs/tasks.md（27.1）
- PRD: docs/requirements.md（R13.4）

# Execution Plan
1) 定义图表数据 schema（Zod）。
2) 实现组件渲染与降级策略。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `npm -C web run build`

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
