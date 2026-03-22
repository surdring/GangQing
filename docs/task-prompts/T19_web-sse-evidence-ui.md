- [x] Doc References Updated
### Task 19 - 前端三栏式布局 + SSE 流式渲染 + 证据链可视化（Context Panel/Trust Pill）（Umbrella）

```markdown
# Context
你正在执行第 19 号任务：前端三栏式布局 + SSE 流式渲染 + 证据链可视化（Context Panel/Trust Pill）。
角色：**技术负责人/架构师**。
目标是基于现有 `web/` 前端原型进行改造（不从零重写 UI），规划前端信息架构（三栏）、SSE 客户端事件解析与状态机、证据链可视化组件、断线重连策略，以及与后端事件契约对齐。

本任务必须移除原型中的硬编码 mock 数据流，改为真实后端 SSE 事件驱动渲染，并对 SSE 事件进行 Zod schema 校验。

本任务交付物是“可落地的实现蓝图（Prompt）”：要求你输出清晰的文件级改动计划、事件与数据流状态机、关键 schema 列表与验证策略，使另一位工程师可以按图施工实现并通过测试。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源（强制）**:
  - 前端对外 I/O、SSE 事件、配置：Zod。
  - 后端对外 I/O/Evidence：Pydantic。
- **Streaming（强制）**: message.delta/progress/evidence.update/error 必须可分段渲染。
- **Evidence-First（强制）**: 数值胶囊（Trust Pill）必须可展开到 Evidence；缺证据必须明确 UI 降级表达。
- **结构化错误（强制）**: 前端必须能解析 `code/message(英文)/details?/retryable/requestId`。
- **真实集成测试（No Skip）**: E2E 冒烟必须连真实后端 SSE。

# Non-Negotiable Contract Alignment（强制对齐点）
本任务的“契约权威来源”优先级如下：
1) `docs/contracts/api-and-events-draft.md`（对外契约草案）
2) `docs/design.md`（3.5 SSE 事件模型、2.10.1/2.10.2 前端核心组件约束、6.4 SSE 错误规则）
3) `docs/requirements.md`（R6.1/R6.2/R6.3/R13.1/R13.2/R13.3）

你在输出蓝图时必须显式声明：所有事件解析与 UI 行为以以上文档为准；如发现冲突，必须指出冲突点并给出“以谁为准”的裁决与原因。

# SSE Envelope & Event Semantics（前端必须显式实现）
前端 SSE 解析必须以“统一 Envelope + payload”的事件结构为核心假设，并在 Zod 层做运行时校验：

- envelope 必含：
  - `requestId`
  - `tenantId`（强制存在；缺失视为契约错误）
  - `projectId`（强制存在；缺失视为契约错误）
  - `sessionId`（如后端提供则透传到 UI 状态/日志）
  - `timestamp`
  - `sequence`（单调递增；用于检测乱序/丢包）
- 事件类型（至少覆盖）：
  - `meta`
  - `progress`
  - `tool.call`
  - `tool.result`
  - `message.delta`
  - `evidence.update`
  - `warning`
  - `error`
  - `final`

客户端必须对 `sequence` 做基本一致性检查：
- 发现非递增或跳号：必须进入可观测路径（至少 console/error-report），并在 UI 以“数据可能不完整”降级提示（不得静默吞掉）。

# UI State Machine（强制）
SSE 客户端必须实现显式状态机（最小集）：
- `idle`
- `connecting`
- `streaming`
- `error`
- `done`

并要求在 UI 上“可感知”：连接中/生成中/已完成/已断开/重连中/重连失败。

# Cancel/Stop Propagation（强制）
当用户点击“停止生成”、离开页面或主动断开 SSE：
- 前端必须停止本地 loading 状态并冻结本次消息追加。
- 必须触发后端取消传播（按后端约定的取消机制），避免出现“前端停止但后端继续推理/继续工具调用”。

# Evidence UI Rules（Context Panel / Trust Pill）
Context Panel 必须支持 `evidence.update` 的增量合并（append/merge），并保留历史 evidence，禁止覆盖导致回退。

Trust Pill 渲染规则（必须明确写入你的蓝图）：
- 仅对“可追溯数值”渲染 Trust Pill（至少包含 citation/时间范围/提取时间等关键字段；以设计文档 3.3/2.10.5 的 Evidence 字段要求为准）。
- 对缺失 Evidence 或 `validation=not_verifiable` 的结论：
  - UI 必须进入降级态（例如虚线边框/灰态/提示文案），并引导用户查看缺失原因。
- 对 `validation=out_of_bounds` 或 `validation=mismatch`：
  - UI 必须明显提示“越界/冲突”，并展示可追溯来源（不得给出确定性解释来掩盖冲突）。

脱敏要求（前端视角）：
- Evidence 默认展示脱敏后的字段；若后端下发 redactions/脱敏说明，Context Panel 必须展示“已脱敏”标识与原因摘要。

# References
- PRD: docs/requirements.md（R13.1/R13.2/R13.3/R6.2/R6.3）
- TDD: docs/design.md（2.2/3.5）
- tasks: docs/tasks.md（任务 19）
- prototype: docs/项目现状分析.md（前端原型范围与局限性）
- contracts: docs/contracts/api-and-events-draft.md
- deployment: REAM.md（部署运行指南）

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
- [ ] 是否显式实现并使用 SSE Envelope 字段（`requestId/tenantId/projectId/sequence/timestamp/sessionId?`），并校验 `tenantId/projectId` 缺失为契约错误？
- [ ] 是否实现 `sequence` 基础一致性检查（非递增/跳号可观测且 UI 降级提示）？
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
- [ ] Trust Pill / Context Panel 是否正确表达 `validation`（`verifiable/not_verifiable/out_of_bounds/mismatch`）对应的 UI 风险态？
- [ ] Evidence 是否默认脱敏展示，并在可用时展示 redactions/脱敏说明？
- [ ] 结构化错误是否可解析并展示必要信息：
  - [ ] `code`
  - [ ] `message`（英文；前端可用中文提示，但必须保留英文 message 供日志检索）
  - [ ] `requestId`（UI 可复制/可定位）
  - [ ] `retryable`（驱动“重试”按钮是否可用）
- [ ] 断线重连策略是否明确且可感知（连接中/已断开/重连中/重连失败）？
- [ ] 重连是否为“指数退避”，并有最大重试次数/最大等待时间的上限策略（由配置驱动，禁止硬编码魔法数字）？
- [ ] 取消/中断是否会停止 UI 的 loading，并触发后端取消传播（按后端协议），避免“前端取消但后端继续跑”导致审计/成本异常？
- [ ] `backend/scripts/web_sse_e2e_smoke_test.py` 是否验证：
  - [ ] 真实后端 SSE 可连接（禁止 mock server）
  - [ ] 最小事件序列可解析（含 `message.delta` 与 `final`；如有 `evidence.update` 更佳）
  - [ ] 错误链路可解析结构化 `error`（含英文 `message` + `requestId` + `retryable`）

# Output Requirement
输出执行蓝图，禁止写代码。

输出必须包含：
1) **文件级改动清单**：按 `web/...` 文件路径列出“要改什么/为什么改/与哪个契约条款对应”。
2) **前端数据流与状态机**：SSE 事件如何驱动 Chat 区与 Context Panel；取消/重连如何改变状态。
3) **Schema 清单**：需要新增/修改的 Zod schema（事件 Envelope、payload、error、evidence、配置），以及如何在运行时用于校验。
4) **可观测性**：前端日志字段最小集（至少 requestId/sessionId/sequence/eventType）与错误上报策略（不含敏感信息）。
5) **验证策略**：单元测试与冒烟测试分别覆盖的链路、成功/失败路径与断言点。

禁止输出：
- 任何大段实现代码（包括完整组件源码、完整 Hook 源码）。
- 任何依赖 mock server 的“假联调”方案。

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
