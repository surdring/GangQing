### Task 15 - SSE 服务端输出：进度/消息增量/证据增量/结构化错误/结束事件完整序列（Umbrella）

```markdown
# Context
你正在执行第 15 号任务：SSE 服务端输出：进度/消息增量/证据增量/结构化错误/结束事件完整序列。
角色：**技术负责人/架构师**。
目标是规划 SSE 端点、事件序列、取消传播要求、以及与前端渲染/契约/测试对齐。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Streaming（强制）**: 长耗时必须 SSE；事件需可分段渲染。
- **结构化错误（强制）**: 发生错误尽快输出 `error`（ErrorResponse），随后 `final`。
- **requestId 贯穿（强制）**: SSE 事件必须携带。
- **取消传播（强制）**: 客户端断开需停止后续输出/停止后续工具调用（至少可验证）。
- **真实集成测试（No Skip）**: `backend/scripts/sse_smoke_test.py` 必须通过。

# References
- PRD: docs/requirements.md（R6.1/R6.3）
- TDD: docs/design.md（3.5/6.4）
- tasks: docs/tasks.md（任务 15）
- contracts: docs/contracts/api-and-events-draft.md（6.1）

# Execution Plan
1) Task 15.1（SSE endpoint 与事件序列契约对齐）
2) Task 15.2（错误流式处理：error+final）
3) Task 15.3（取消传播验证）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/sse_smoke_test.py`

# 联调检查清单（服务端视角）
- [ ] 事件 envelope 是否与 `docs/contracts/api-and-events-draft.md` 一致（字段名、嵌套层级、可选字段）？
- [ ] 每个事件是否都携带 `requestId`（以及若契约要求则携带 `sessionId`）？
- [ ] 事件类型是否覆盖并只覆盖：
  - [ ] `progress`
  - [ ] `tool.call`
  - [ ] `tool.result`
  - [ ] `message.delta`
  - [ ] `evidence.update`
  - [ ] `warning`
  - [ ] `error`
  - [ ] `final`
- [ ] 最小可用事件序列是否可稳定复现：`progress` -> `tool.call` -> `tool.result` -> `message.delta`(>=1) -> `final`？
- [ ] `message.delta` 是否保证“增量”语义（前端可逐段追加渲染，而非重复全量）？
- [ ] `evidence.update` 是否满足“增量更新”语义（可多次发送；前端可合并更新而非覆盖丢失）？
- [ ] `error` payload 是否为结构化错误（ErrorResponse），且包含：
  - [ ] `code`
  - [ ] `message`（英文）
  - [ ] `requestId`
  - [ ] `retryable`
  - [ ] `details?`（仅结构化上下文，禁止敏感信息）
- [ ] 不可恢复错误路径是否严格输出：`error` -> `final`，且 `final` 后不再输出任何事件？
- [ ] 客户端断开/取消时：
  - [ ] 后端是否停止继续写入 SSE（避免 BrokenPipe 循环）？
  - [ ] 是否停止后续工具调用/推理（至少可验证）？
- [ ] `backend/scripts/sse_smoke_test.py` 是否验证了：
  - [ ] 正常链路的最小事件序列
  - [ ] 至少 1 条错误链路（校验结构化 `error` 字段 + 英文 message）
  - [ ] `requestId` 贯穿

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 15.1 - SSE 事件序列：progress/tool/message/evidence/final

```markdown
# Context
你正在执行子任务：15.1 - SSE 事件序列：progress/tool/message/evidence/final。
目标是实现服务端 SSE 输出并严格遵守 contracts 的事件字段与序列。

# Critical Rules
- **事件可解析**: 每个事件 schema 清晰。
- **requestId 强制**。

# References
- tasks: docs/tasks.md（15.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 实现 SSE 事件编码器与统一 envelope。
2) 输出最小序列：`progress` -> `tool.call` -> `tool.result` -> `message.delta` -> `final`。

# Verification
- **Unit**: `pytest -q` 覆盖事件字段。
- **Smoke**: `backend/scripts/sse_smoke_test.py`。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 15.2 - SSE 错误处理：`error` + `final`

```markdown
# Context
你正在执行子任务：15.2 - SSE 错误处理：`error` + `final`。

# Critical Rules
- **错误必须尽快输出**。
- **payload 同构 ErrorResponse**。

# References
- tasks: docs/tasks.md（15.2）
- TDD: docs/design.md（6.4）

# Execution Plan
1) 统一异常捕获并在流中输出 `error`。
2) 对不可恢复错误输出 `final` 并终止。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/sse_smoke_test.py`（覆盖一次错误路径）。

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（evidence.update）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
