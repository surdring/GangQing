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
输出修改文件完整内容 + 测试命令。
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
输出修改文件完整内容 + 测试命令。
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
