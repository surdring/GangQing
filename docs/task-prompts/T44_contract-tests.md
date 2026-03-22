### Task 44 - 契约测试体系：前端 Zod + 后端 Pydantic + SSE 事件 schema 自动断言（Umbrella）

```markdown
# Context
你正在执行第 44 号任务：契约测试体系。
角色：**技术负责人/架构师**。
目标是规划契约测试覆盖对象（REST 响应、SSE 事件、Evidence、错误模型）、测试门禁策略（不一致阻止合并/发布），以及单元/冒烟测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Schema 单一事实源（强制）**: 前端 Zod、后端 Pydantic，且对外输出前必须 schema 断言。
- **结构化错误（强制）**: 错误模型字段齐全，英文 message。
- **真实集成测试（No Skip）**: 契约冒烟必须连真实服务；缺配置必须失败。

# References
- PRD: docs/requirements.md（R9.3）
- TDD: docs/design.md（7.4）
- tasks: docs/tasks.md（任务 44）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# Execution Plan
1) Task 44.1（后端 Pydantic 契约断言：REST/SSE）
2) Task 44.2（前端 Zod 事件/响应解析断言）
3) Task 44.3（门禁：CI 阻断策略）

# Verification
- Unit: `pytest -q && npm -C web test`
- Smoke:
  - `backend/scripts/contract_tests_smoke_test.py`
  - `backend/scripts/sse_smoke_test.py`

# 联调检查清单（契约/联调门禁）
- [ ] `docs/contracts/api-and-events-draft.md` 是否被视为对外契约的单一事实源（任何实现/测试以它为准）？
- [ ] 是否同时覆盖以下对象的 schema 断言：
  - [ ] REST 响应（HTTP 状态码 + body）
  - [ ] SSE 事件 envelope（统一字段 + payload）
  - [ ] Evidence（claims/citations/lineage/tool traces 的字段完整性）
  - [ ] ErrorResponse（`code/message(英文)/details?/retryable/requestId`）
- [ ] SSE 事件类型枚举是否与契约一致（不多不少），至少包含：`progress/tool.call/tool.result/message.delta/evidence.update/warning/error/final`？
- [ ] SSE 事件类型判定是否以 JSON 字段 `type` 为准（不依赖 SSE 的 `event:` 行）？
- [ ] `final.payload` 是否仅包含 `status: success|error|cancelled`（禁止输出 `done` 等冗余字段）？
- [ ] `message.delta` 是否允许多次出现，且每次为增量片段（契约/测试需覆盖“多 delta”场景）？
- [ ] `evidence.update` 是否允许多次出现，且为增量合并语义（契约/测试需覆盖“多 update”场景）？
- [ ] 契约失败时是否统一映射为 `CONTRACT_VIOLATION`，并在 `details` 中给出字段路径/原因摘要（禁止敏感信息）？
- [ ] 前端 Zod 校验失败时是否进入结构化错误路径（可观测、可定位 requestId），而不是 console.warn 后继续渲染？
- [ ] `backend/scripts/contract_tests_smoke_test.py` 是否满足“真实服务 No Skip”：
  - [ ] 真实 FastAPI + 真实 Postgres + 真实 llama.cpp（或按当前阶段的真实推理服务）
  - [ ] 配置缺失 => 测试失败（英文错误消息）
  - [ ] 至少覆盖 1 个成功链路 + 1 个失败链路（错误模型可解析）

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 44.1 - SSE/REST 契约断言：失败即 `CONTRACT_VIOLATION`

```markdown
# Context
你正在执行子任务：44.1 - SSE/REST 契约断言：失败即 `CONTRACT_VIOLATION`。

# Critical Rules
- **输出前必须校验**。
- **失败必须可定位**: `details` 给出字段路径摘要（去敏）。

# References
- tasks: docs/tasks.md（44.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 为 REST 响应与 SSE 事件定义 Pydantic 模型。
2) 在输出前做校验，失败映射 `CONTRACT_VIOLATION`。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/contract_tests_smoke_test.py`

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
- [x] 证据链要求与字段？（契约覆盖 Evidence）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？（契约失败也需审计）
- [x] Schema（Zod/Pydantic）？（本任务核心）
- [x] 真实集成测试 No Skip？
