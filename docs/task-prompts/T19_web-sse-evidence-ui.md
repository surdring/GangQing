### Task 19 - 前端三栏式布局 + SSE 流式渲染 + 证据链可视化（Context Panel/Trust Pill）（Umbrella）

```markdown
# Context
你正在执行第 19 号任务：前端三栏式布局 + SSE 流式渲染 + 证据链可视化（Context Panel/Trust Pill）。
角色：**技术负责人/架构师**。
目标是规划前端信息架构（三栏）、SSE 客户端事件解析与状态机、证据链可视化组件、断线重连策略，以及与后端事件契约对齐。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源（强制）**:
  - 前端对外 I/O、SSE 事件、配置：Zod。
  - 后端对外 I/O/Evidence：Pydantic。
- **Streaming（强制）**: message.delta/progress/evidence.update/error 必须可分段渲染。
- **Evidence-First（强制）**: 数值胶囊（Trust Pill）必须可展开到 Evidence；缺证据必须明确 UI 降级表达。
- **结构化错误（强制）**: 前端必须能解析 `code/message(英文)/details?/retryable/requestId`。
- **真实集成测试（No Skip）**: E2E 冒烟必须连真实后端 SSE。

# References
- PRD: docs/requirements.md（R13.1/R13.2/R13.3/R6.2/R6.3）
- TDD: docs/design.md（2.2/3.5）
- tasks: docs/tasks.md（任务 19）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 19.1（三栏布局与组件结构）
2) Task 19.2（SSE 客户端：事件解析与渲染）
3) Task 19.3（Evidence UI：Context Panel/Trust Pill）
4) Task 19.4（断线重连与错误/取消）

# Verification
- Unit: `npm -C web test`
- Smoke: `npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 19.1 - 三栏式布局与基础组件集成

```markdown
# Context
你正在执行子任务：19.1 - 三栏式布局与基础组件集成。

# Critical Rules
- **TypeScript Strict**: 禁止 `any`。
- **Zod**: 对外配置/事件 schema 校验。

# References
- tasks: docs/tasks.md（19.1）
- PRD: docs/requirements.md（R13.1）

# Execution Plan
1) 梳理 `web/` 目录内布局组件职责。
2) 确保中间对话区与右侧 Context Panel 的数据流明确。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `npm -C web run build`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Task 19.2 - SSE 流式渲染：message.delta/progress/evidence.update/error

```markdown
# Context
你正在执行子任务：19.2 - SSE 流式渲染：message.delta/progress/evidence.update/error。

# Critical Rules
- **事件 schema 校验**: 前端用 Zod 校验事件。
- **结构化错误可解析**。

# References
- tasks: docs/tasks.md（19.2）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 实现 SSE 事件解析器与状态更新。
2) `message.delta` 分段渲染；`evidence.update` 增量渲染。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？（前端解析要求 message 英文）
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（Context Panel/Trust Pill）
- [x] 是否包含只读默认与审批链要求？（全局规则保留）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（前端需透传/展示 requestId）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
