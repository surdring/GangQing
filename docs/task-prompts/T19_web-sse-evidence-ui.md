### Task 19 - 前端三栏式布局 + SSE 流式渲染 + 证据链可视化（Context Panel/Trust Pill）（Umbrella）

```markdown
# Context
你正在执行第 19 号任务：前端三栏式布局 + SSE 流式渲染 + 证据链可视化（Context Panel/Trust Pill）。
角色：**技术负责人/架构师**。
目标是基于现有 `web/` 前端原型进行改造（不从零重写 UI），规划前端信息架构（三栏）、SSE 客户端事件解析与状态机、证据链可视化组件、断线重连策略，以及与后端事件契约对齐。

本任务必须移除原型中的硬编码 mock 数据流，改为真实后端 SSE 事件驱动渲染，并对 SSE 事件进行 Zod schema 校验。

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
- prototype: docs/项目现状分析.md（前端原型范围与局限性）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 19.1（三栏布局与组件结构）
2) Task 19.2（SSE 客户端：事件解析与渲染）
3) Task 19.3（Evidence UI：Context Panel/Trust Pill）
4) Task 19.4（断线重连与错误/取消）

# Verification
- Unit: `npm -C web test`
- Smoke: `npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`

补充要求：如果 `backend/scripts/web_sse_e2e_smoke_test.py` 不存在，必须在本任务中补齐该脚本；脚本至少验证：
- 真实后端 SSE 连接可建立（不可使用 mock server）
- 能收到并解析最小事件序列（含 `message.delta` 与 `final`；如有 `evidence.update` 更佳）
- 异常路径可解析结构化错误（含 `code/message(英文)/requestId/retryable`）

# 联调检查清单（前端视角）
- [ ] 是否已移除原型中的硬编码 mock 数据流（包括：mock SSE 事件、mock 对话回复、假 evidence）？
- [ ] SSE 事件解析是否以 `docs/contracts/api-and-events-draft.md` 为准（事件名、字段名、可选字段）？
- [ ] 是否对每条 SSE 事件做 Zod runtime 校验，且校验失败进入可观测错误路径（不能静默吞掉）？
- [ ] UI 是否覆盖并能分段渲染以下事件：
  - [ ] `progress`（阶段进度）
  - [ ] `message.delta`（回答增量）
  - [ ] `evidence.update`（证据链增量）
  - [ ] `warning`（降级/不确定项）
  - [ ] `error`（结构化错误）
  - [ ] `final`（结束）
- [ ] `message.delta` 是否为“追加渲染”而非重复覆盖（避免闪烁/重复）？
- [ ] `evidence.update` 是否为“增量合并”而非覆盖丢失（保证 citations/claims 不被回退）？
- [ ] Trust Pill 是否只对“可追溯数值”渲染（至少具备 citation/time_range/extracted_at 等关键字段）；缺证据是否有明确降级态 UI？
- [ ] 结构化错误是否可解析并展示必要信息：
  - [ ] `code`
  - [ ] `message`（英文；前端可用中文提示，但必须保留英文 message 供日志检索）
  - [ ] `requestId`（UI 可复制/可定位）
  - [ ] `retryable`（驱动“重试”按钮是否可用）
- [ ] 断线重连策略是否明确且可感知（连接中/已断开/重连中/重连失败）？
- [ ] 取消/中断是否会停止 UI 的 loading，并触发后端取消传播（按后端协议），避免“前端取消但后端继续跑”导致审计/成本异常？
- [ ] `backend/scripts/web_sse_e2e_smoke_test.py` 是否验证：
  - [ ] 真实后端 SSE 可连接（禁止 mock server）
  - [ ] 最小事件序列可解析（含 `message.delta` 与 `final`；如有 `evidence.update` 更佳）
  - [ ] 错误链路可解析结构化 `error`（含英文 `message` + `requestId` + `retryable`）

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 19.1 - 三栏式布局与基础组件集成

```markdown
# Context
你正在执行子任务：19.1 - 三栏式布局与基础组件集成。

本子任务必须基于现有 `web/` 前端原型改造，禁止为“重做 UI”而重写三栏布局。重点是把原型中的演示数据流改造成可接入真实后端 SSE 的布局与数据流骨架。

# Critical Rules
- **TypeScript Strict**: 禁止 `any`。
- **Zod**: 对外配置/事件 schema 校验。

# References
- tasks: docs/tasks.md（19.1）
- PRD: docs/requirements.md（R13.1）
- prototype: docs/项目现状分析.md（前端原型范围与局限性）

# Execution Plan
1) 梳理 `web/` 目录内布局组件职责。
2) 确保中间对话区与右侧 Context Panel 的数据流明确。

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

### Task 19.2 - SSE 流式渲染：message.delta/progress/evidence.update/error

```markdown
# Context
你正在执行子任务：19.2 - SSE 流式渲染：message.delta/progress/evidence.update/error。

本子任务必须移除原型中的硬编码 mock 响应，改为真实后端 SSE 事件驱动渲染，并对 SSE 事件做 Zod schema 校验；校验失败必须进入可观测的错误路径。

# Critical Rules
- **事件 schema 校验**: 前端用 Zod 校验事件。
- **结构化错误可解析**。

# References
- tasks: docs/tasks.md（19.2）
- contracts: docs/contracts/api-and-events-draft.md
- prototype: docs/项目现状分析.md（前端原型范围与局限性）

# Execution Plan
1) 实现 SSE 事件解析器与状态更新。
2) `message.delta` 分段渲染；`evidence.update` 增量渲染。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `backend/scripts/web_sse_e2e_smoke_test.py`

补充要求：如果 `backend/scripts/web_sse_e2e_smoke_test.py` 不存在，必须在本任务中补齐该脚本；脚本至少验证：
- 真实后端 SSE 连接可建立（不可使用 mock server）
- 能收到并解析最小事件序列（含 `message.delta` 与 `final`；如有 `evidence.update` 更佳）
- 异常路径可解析结构化错误（含 `code/message(英文)/requestId/retryable`）

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
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
- [x] Doc References Updated（文档引用已同步）
