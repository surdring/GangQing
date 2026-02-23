### Task 9 - 工具参数 schema 校验与契约校验（Pydantic 单一事实源）（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 9 号任务：工具参数 schema 校验与契约校验（Pydantic 单一事实源）。
你的角色是 **技术负责人/架构师**。
你的目标是制定 Task 9 的详细执行计划，并定义统一的“入参校验 + 输出校验 + 错误映射 + 审计留痕 + 契约测试门禁”机制，避免工具链与模型输出发生契约漂移。

# Critical Rules (核心约束)
- **NO CODE IMPLEMENTATION**: 在此阶段禁止输出任何具体的函数实现或业务代码。
- **PLANNING ONLY**: 你的输出应该聚焦于“怎么做”、“分几步”、“改哪些文件”、“接口/模型长什么样”。
- **Schema 单一事实源（强制）**:
  - 后端：工具参数 / 工具输出 / 对外响应 / SSE 事件载荷 / Evidence / 审计事件必须以 **Pydantic** 为单一事实源（模型定义 + 校验）。
  - 前端：对外 I/O 与 SSE 事件解析以 **Zod** 对齐（schema -> type）。
- **Structured Errors（强制）**:
  - 参数无效 => `VALIDATION_ERROR`
  - 输出不符合契约 => `CONTRACT_VIOLATION`
  - 对外错误必须结构化：`code` + `message`(英文) + `requestId` + `retryable` + `details?`。
- **RBAC & Audit & requestId 贯穿（强制）**:
  - 任何一次校验失败都必须写审计（含 `requestId`、`toolName`、阶段/stepId（如有））。
  - `details` 禁止包含敏感信息（包括密钥、原始 SQL、完整行数据等）。
- **真实集成测试（No Skip）**:
  - 冒烟/集成测试必须连接真实服务（真实 FastAPI + 真实 Postgres + 真实 llama.cpp）。
  - 缺配置/依赖不可用 => 测试必须失败并输出清晰英文错误。

# References
- PRD: docs/requirements.md（R8.2 工具参数校验 / R9.3 输出结构化校验）
- TDD: docs/design.md（6 错误处理 / 7 测试策略 / 3.5 SSE 错误事件规则）
- tasks: docs/tasks.md（任务 9）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/openapi.yaml

# Execution Plan (执行蓝图)

1) 工具入参校验与错误映射（Task 9.1）
- Goal:
  - 建立工具调用的统一参数校验入口，所有工具参数必须通过 Pydantic 校验。
  - 校验失败可稳定映射为 `VALIDATION_ERROR`，并输出结构化错误模型（含 `requestId`）。
- Deliverables:
  - 工具参数 Pydantic 模型清单与落点文件规划。
  - 统一异常捕获与错误映射规则（VALIDATION_ERROR）。
  - 审计事件字段约定（失败阶段、toolName、错误码、requestId）。

2) 工具输出/模型输出的“对外前”契约校验（Task 9.2）
- Goal:
  - 在“即将对外输出”（REST 响应 / SSE event payload）之前执行 Pydantic schema 断言。
  - 校验失败稳定映射为 `CONTRACT_VIOLATION`，并确保 SSE `error` 事件与 REST 错误响应同构。
- Deliverables:
  - 工具输出 Pydantic 模型（Result Models）规划。
  - SSE error 事件载荷与 REST ErrorResponse 的字段对齐策略。
  - 审计字段约定（违规字段摘要、来源模块、requestId）。

3) 契约测试与门禁（Task 9.3）
- Goal:
  - 建立“契约漂移不可发布”的测试门禁：最少包含单元测试 + 真实服务冒烟测试。
  - 覆盖两类失败：入参校验失败（VALIDATION_ERROR）与输出校验失败（CONTRACT_VIOLATION）。
- Deliverables:
  - 单元测试集合（覆盖异常映射与错误结构）。
  - 冒烟脚本：连接真实服务并触发一次失败路径，断言结构化错误。

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确新增/修改的目录树与文件清单。
- [ ] **API Contracts**: 明确对外错误模型与 SSE error 事件字段（与 `docs/contracts/api-and-events-draft.md` 对齐）。
- [ ] **Tool Contracts**: 每个工具的 Params/Result Pydantic 模型清单与落点。
- [ ] **Error Model**: `VALIDATION_ERROR`/`CONTRACT_VIOLATION` 的触发条件与 `details` 脱敏规则。
- [ ] **Audit**: 审计事件类型与最小字段集（requestId、toolName、result、errorCode）。
- [ ] **Test Gate**: 单元测试与冒烟测试的覆盖点与断言目标。

# Verification Plan (整体验收)
- Automated Tests:
  - `pytest -q`
  - `backend/scripts/contract_validation_smoke_test.py`

# Output Requirement
请输出一份详细的 Markdown 执行计划，包含上述所有章节。
**不要写代码**。
```

---

### Task 9.1 - 工具入参校验：Pydantic schema + `VALIDATION_ERROR`

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：9.1 - 工具入参校验：Pydantic schema + `VALIDATION_ERROR`。
你的角色是 **高级开发工程师**。
你的目标是在“工具调用边界”建立统一参数校验机制，并确保错误结构化、可审计、可被 SSE/REST 下游解析。

# Critical Rules (核心约束)
- **Schema First**: 工具参数必须使用 Pydantic 模型校验（单一事实源）。
- **Structured Errors**: 校验失败必须返回结构化错误：`VALIDATION_ERROR` + 英文 `message` + `requestId` + `retryable` + `details?`。
- **RBAC & Audit**: 记录审计事件，字段至少包含：`requestId`、`toolName`、失败阶段（如 `tool.params.validate`）、`errorCode`。
- **No Sensitive Details**: `details` 禁止包含敏感信息与原始大对象（例如完整 SQL、完整 rows）。
- **Real Integration (No Skip)**: 冒烟/集成测试必须连真实服务；缺配置/依赖不可用必须失败。

# References
- PRD: docs/requirements.md（R8.2）
- TDD: docs/design.md（6.1 统一错误模型 / 7 测试策略）
- tasks: docs/tasks.md（9.1）
- contracts: docs/contracts/api-and-events-draft.md（ErrorResponse）

# Target Files (建议落点；以仓库现状为准)
- backend/gangqing/common/errors.py（复用/扩展错误模型，确保 requestId 字段对齐）
- backend/gangqing/tools/base.py（工具协议边界，参数类型约束）
- backend/gangqing/tools/*（各工具 params 模型落地与调用入口）
- backend/gangqing/common/audit.py（写审计：tool call/validation failure）
- backend/tests/**（单元测试）

# Execution Plan (具体步骤)
1) 建立统一参数校验入口
- 目标：所有工具调用前执行 `PydanticModel.model_validate(...)`（或等价校验）。
- 失败：捕获 Pydantic 校验异常，组装 `VALIDATION_ERROR`（英文 message），并携带 `requestId`。

2) 细化 `details` 脱敏策略
- 目标：`details` 仅包含字段级摘要，例如 `{"fieldErrors": [{"path": "...", "reason": "..."}]}`。
- 禁止：原始输入全文、密钥、token、完整 SQL、完整 rows。

3) 审计记录
- 目标：校验失败必须写审计事件，至少包含 `toolName` 与 `errorCode=VALIDATION_ERROR`。

4) 测试
- 单元测试：覆盖
  - 非法参数 -> `VALIDATION_ERROR`
  - message 为英文（可用简单正则/关键词断言）
  - response 包含 requestId
- 冒烟测试：在真实服务下触发一次非法参数调用并断言结构化错误（不可 skip）。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/contract_validation_smoke_test.py`

# Output Requirement
- 输出所有修改或创建的文件路径清单。
- 输出必要的关键片段（最小必要）。
- 输出测试命令与关键输出摘要（文本）。

# Checklist（子任务自检）
- [ ] 是否明确列出了 **Target Files**（要修改哪些文件）？
- [ ] 是否在代码层实现了 **Pydantic 入参校验**，并且校验发生在“工具调用边界”？
- [ ] 非法参数是否稳定映射为 `VALIDATION_ERROR`？
- [ ] 对外错误是否为结构化模型（`code/message/requestId/retryable/details?`）？
- [ ] 是否确保所有错误 `message` 均为英文？
- [ ] `details` 是否已脱敏（不包含密钥/token/原始 SQL/完整 rows 等）？
- [ ] 是否写入审计事件并包含最小字段集（`requestId/toolName/errorCode/阶段或 stepId`）？
- [ ] 是否运行并通过：单元测试 + 真实服务冒烟测试（No Skip）？
```

---

### Task 9.2 - 工具输出/模型输出契约校验：`CONTRACT_VIOLATION`

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：9.2 - 工具输出/模型输出契约校验：`CONTRACT_VIOLATION`。
你的角色是 **高级开发工程师**。
你的目标是在“对外输出之前”对数据进行 Pydantic schema 断言，避免下游解析失败与证据链断裂。

# Critical Rules (核心约束)
- **Validate Before Output**: 对外输出（REST/SSE）之前必须完成契约校验，失败必须阻断输出。
- **Structured Errors**: 返回 `CONTRACT_VIOLATION`，英文 `message`，并携带 `requestId`、`retryable`、`details?`。
- **SSE 同构错误**: SSE `error` 事件载荷必须与 REST 错误响应字段同构，便于前端统一解析。
- **Audit**: 记录违规字段摘要与来源模块（去敏），并绑定 `requestId`。
- **Real Integration (No Skip)**: 冒烟/集成测试必须连真实服务；缺配置/依赖不可用必须失败。

# References
- PRD: docs/requirements.md（R9.3）
- TDD: docs/design.md（6.4 SSE 错误事件规则 / 7.4 契约测试）
- tasks: docs/tasks.md（9.2）
- contracts: docs/contracts/api-and-events-draft.md

# Target Files (建议落点；以仓库现状为准)
- backend/gangqing/common/errors.py
- backend/gangqing/tools/*（各工具 result 模型）
- backend/gangqing/api/**（对外输出层，REST/SSE 输出前校验）
- backend/tests/**

# Execution Plan (具体步骤)
1) 定义/补齐工具输出与对外事件载荷的 Pydantic 模型
- 目标：工具 result / SSE event payload 可被模型校验。

2) 在输出边界执行校验
- 目标：在数据离开后端之前统一校验。
- 失败：组装 `CONTRACT_VIOLATION`，`details` 仅包含字段摘要与错误类型。

3) 审计记录
- 目标：记录 `source=output_validation`、违规字段摘要、`errorCode=CONTRACT_VIOLATION`。

4) 测试
- 单元测试：缺字段/类型错 -> `CONTRACT_VIOLATION`；断言结构化错误字段齐全。
- 冒烟测试：真实服务下触发一次输出契约失败并断言 SSE/REST 错误同构。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/contract_validation_smoke_test.py`

# Output Requirement
- 输出所有修改或创建的文件路径清单。
- 输出必要的关键片段（最小必要）。
- 输出测试命令与关键输出摘要（文本）。

# Checklist（子任务自检）
- [ ] 是否明确列出了 **Target Files**（要修改哪些文件）？
- [ ] 是否定义/补齐了工具输出与对外事件载荷的 Pydantic 模型，并在输出边界完成校验？
- [ ] 输出契约失败是否稳定映射为 `CONTRACT_VIOLATION`？
- [ ] 对外错误是否为结构化模型（`code/message/requestId/retryable/details?`）？
- [ ] 是否确保所有错误 `message` 均为英文？
- [ ] `details` 是否仅包含字段级摘要并完成脱敏（不包含原始大对象/敏感数据）？
- [ ] SSE `error` 事件与 REST 错误响应是否字段同构（至少 `code/message/requestId/retryable/details?`）？
- [ ] 是否写入审计事件并包含最小字段集（`requestId/errorCode/来源模块/字段摘要`）？
- [ ] 是否运行并通过：单元测试 + 真实服务冒烟测试（No Skip）？
```

---

### Task 9.3 - 契约测试与门禁：Unit + Smoke（真实服务，No Skip）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行子任务：9.3 - 契约测试与门禁：Unit + Smoke（真实服务，No Skip）。
你的角色是 **高级开发工程师**。
你的目标是把“契约漂移不可发布”落到自动化测试上：既要覆盖局部单元测试，也要覆盖端到端真实服务冒烟测试。

# Critical Rules (核心约束)
- **Real Integration (No Mock / No Skip)**:
  - 冒烟测试必须连接真实 FastAPI + 真实 Postgres + 真实 llama.cpp。
  - 配置缺失或依赖不可用：测试必须失败，并输出清晰英文错误。
- **Two Failure Classes Must Be Covered**:
  - 入参校验失败：`VALIDATION_ERROR`
  - 输出契约失败：`CONTRACT_VIOLATION`
- **Structured Errors**: 测试必须断言结构化错误字段：`code/message/requestId/retryable/details?`。

# References
- TDD: docs/design.md（7 测试策略 / 6.4 SSE 错误事件规则）
- tasks: docs/tasks.md（9.3）

# Target Files (建议落点；以仓库现状为准)
- backend/tests/**
- backend/scripts/contract_validation_smoke_test.py

# Execution Plan (具体步骤)
1) 单元测试门禁
- 覆盖：参数无效 -> `VALIDATION_ERROR`
- 覆盖：输出缺字段/类型错 -> `CONTRACT_VIOLATION`
- 断言：结构化错误字段齐全，且 message 为英文

2) 冒烟脚本门禁（真实服务）
- 覆盖：至少 1 条成功链路（证明服务可用）
- 覆盖：至少 1 条失败链路（VALIDATION_ERROR 或 CONTRACT_VIOLATION），并断言结构化错误可解析

3) 失败可诊断
- 配置缺失时：抛出清晰英文错误（例如缺少 DB/LLM URL）
- 依赖不可用时：失败原因需可读（连接失败/超时等）

# Verification (验收标准)
- Unit: `pytest -q`
- Smoke: `backend/scripts/contract_validation_smoke_test.py`

# Output Requirement
- 输出所有修改或创建的文件路径清单。
- 输出测试命令与关键输出摘要（文本）。

# Checklist（子任务自检）
- [ ] 是否明确列出了 **Target Files**（要修改哪些文件）？
- [ ] 单元测试是否覆盖两类失败：`VALIDATION_ERROR` 与 `CONTRACT_VIOLATION`？
- [ ] 冒烟脚本是否连接真实 FastAPI + Postgres + llama.cpp（No Mock / No Skip）？
- [ ] 冒烟测试是否至少覆盖：1 条成功链路 + 1 条失败链路？
- [ ] 测试是否断言结构化错误字段（`code/message/requestId/retryable/details?`）且 `message` 为英文？
- [ ] 配置缺失或依赖不可用时，测试是否明确失败并输出清晰英文错误（不可 skip）？
```

---

### Checklist（自检）
- [ ] Umbrella 是否包含 `# Critical Rules` 且明确禁止写代码？
- [ ] Umbrella 的 `# Execution Plan` 是否覆盖 9.1/9.2/9.3 全部子任务？
- [ ] 是否定义了 Schema 单一事实源（后端 Pydantic / 前端 Zod 对齐）与边界校验位置？
- [ ] 是否明确了结构化错误模型（`code/message/requestId/retryable/details?`）且 `message` 为英文？
- [ ] 是否明确了 `details` 脱敏规则（禁止密钥/原始 SQL/完整 rows 等）？
- [ ] 是否明确了审计字段与 requestId 贯穿要求（含 toolName/阶段或 stepId）？
- [ ] 是否强调了真实集成测试（No Mock / No Skip），并写明单元 + 冒烟两类门禁？
