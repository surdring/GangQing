### Task 43 - 配置外部化与配置校验：`.env.example` 完整列举 + 启动快速失败（英文错误）（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 43 号任务：配置外部化与配置校验。
你的角色是 **技术负责人/架构师**。
你的目标是制定统一配置加载机制、配置 schema 校验、关键配置缺失的快速失败策略（英文错误）、以及 `.env.example` 文档化要求的详细执行计划，并定义技术规范与验收口径。

# Critical Rules (核心约束)
- **NO CODE IMPLEMENTATION**: 在此阶段**禁止**输出任何具体的函数实现或业务代码。
- **PLANNING ONLY**: 你的输出应该聚焦于"怎么做"、"分几步"、"文件结构如何"、"接口长什么样"。
- **配置外部化（强制）**: 所有 URL、端口、超时时间、重试次数、API Key、模型路由策略、配额、开关（如 kill switch）必须外部化（环境变量或配置文件），**禁止硬编码**。
- **Schema 单一事实源（强制）**:
  - 前端配置使用 **Zod** schema 校验，类型从 schema 推导（`z.infer`）。
  - 后端配置使用 **Pydantic** 模型作为单一事实源。
- **缺配置必须快速失败（强制）**:
  - 关键配置缺失时服务启动必须**立即失败**（fail fast）。
  - 错误消息必须为**英文**，便于日志检索与自动分析。
  - 禁止 silent default 或交互式询问获取配置。
- **本地开发 `.env.local`（强制）**:
  - 本地开发与测试默认从仓库根目录 `.env.local` 加载配置（如存在）。
  - 优先级：进程环境变量 > `.env.local`。
  - `.env.local` 仅用于本地开发，**不得提交到仓库**。
  - `.env.example` 必须完整枚举所有配置项并说明用途。
- **结构化错误（强制）**: 对外错误必须结构化：`code` + `message`（英文） + `requestId` + `retryable` + `details?`。
- **真实集成测试（No Skip）**: 冒烟/集成测试必须连真实服务；配置缺失或依赖不可用必须导致测试失败，不得 skip。
- **RBAC & Audit**: 配置加载过程如涉及敏感操作（如审计开关、kill switch），需记录审计并贯穿 `requestId`。

# References
- PRD: docs/requirements.md（R14.5 私有化部署、配置需求）
- TDD: docs/design.md（2.9 配置与密钥管理、强制配置外部化约束）
- AGENTS: AGENTS.md（配置化开发原则、`.env.local` 约束）
- tasks: docs/tasks.md（任务 43）
- contracts: docs/contracts/api-and-events-draft.md（错误码、结构化错误模型）
- env: .env.example（目标文件，需完整列举）

# Execution Plan (执行蓝图)

1) Task 43.1 - 配置加载与 schema 校验：缺配置快速失败（英文错误）
- Goal: 实现前端和后端的统一配置加载机制，使用 schema 进行配置校验，确保关键配置缺失时服务启动立即失败并输出清晰英文错误。
- Key Decisions:
  - 后端使用 Pydantic BaseSettings 实现配置模型，支持从环境变量和 `.env.local` 加载。
  - 前端使用 Zod schema 定义配置结构，加载时进行运行时校验。
  - 配置分类：数据库、LLM 服务、安全/认证、审计日志、工具超时/重试、模型路由/配额。
- Dependencies: 无（本任务为基础设施）
- Deliverables:
  - `backend/gangqing/config.py` - Pydantic 配置模型
  - `web/src/config/` - Zod schema 与配置加载

2) Task 43.2 - 配置错误消息规范与错误码定义
- Goal: 统一定义配置相关的错误码、错误消息格式、以及配置校验失败的日志输出规范。
- Key Decisions:
  - 定义标准错误码：`CONFIG_MISSING`、`CONFIG_INVALID`、`CONFIG_TYPE_ERROR`。
  - 错误消息模板：`"Missing required configuration: {CONFIG_NAME}. Please set {ENV_VAR} in .env.local or environment."`
  - 日志结构化输出：包含 `code`、`config_key`、`requestId`（如启动阶段有）、timestamp。
- Dependencies: Task 43.1（配置加载机制）
- Deliverables:
  - 错误码补充到全局错误码定义
  - 配置校验失败日志格式规范

3) Task 43.3 - `.env.example` 完整性与文档同步
- Goal: 完整列举所有配置项到 `.env.example`，并确保与代码中 schema 定义同步。
- Key Decisions:
  - `.env.example` 按功能分组：Database、LLM、Security、Audit、Tools、Observability。
  - 每个配置项必须包含：变量名、说明、是否必填、默认值（如有）、示例值。
  - 建立配置变更同步机制：新增/修改配置必须同步更新 `.env.example`。
- Dependencies: Task 43.1（明确所有配置项）
- Deliverables:
  - `.env.example` 完整更新
  - 配置项与 schema 一致性校验脚本（可选）

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 
  - `backend/gangqing/config.py` - 后端配置模型
  - `web/src/config/index.ts` - 前端配置加载
  - `web/src/schemas/config.ts` - Zod schema（如已存在则更新）
  - `.env.example` - 完整配置示例
- [ ] **Environment Variables Schema**:
  - 后端 Pydantic 模型：字段类型、默认值、验证器
  - 前端 Zod schema：字段类型、默认值、转换逻辑
- [ ] **Error Model**: 
  - 错误码：`CONFIG_MISSING`、`CONFIG_INVALID`、`CONFIG_TYPE_ERROR`
  - 结构化错误字段：`code`、`message`（英文）、`config_key`、`details?`
- [ ] **Observability**: 
  - 配置加载日志：包含 `timestamp`、`code`、`config_key`、`status`
  - 启动失败审计：记录配置缺失导致的启动失败

# Verification Plan (整体验收)
- 自动化断言：
  - **单元测试**: `pytest -q` 通过后端的配置模型测试
    - 正常配置加载测试
    - 缺配置快速失败测试
    - 配置类型错误测试
  - **冒烟测试**: `backend/scripts/config_validation_smoke_test.py`
    - 验证配置缺失时服务启动失败
    - 验证错误消息为英文
    - 验证 `.env.local` 加载机制
- **配置一致性验证**:
  - 检查 `.env.example` 中所有配置项在后端 Pydantic 模型中有对应定义
  - 检查前端 Zod schema 与后端模型的一致性
- **快速失败验证**:
  - 移除必需配置项，验证服务启动立即失败
  - 验证错误消息清晰且为英文

# Output Requirement
请输出一份详细的 **Markdown 执行计划**，包含上述所有章节。
**不要写代码**，请确认你理解了全局设计后再输出计划。
```

---

### Task 43.1 - 配置加载与 schema 校验：缺配置快速失败（英文错误）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行配置外部化与配置校验下的子任务：43.1 - 配置加载与 schema 校验：缺配置快速失败（英文错误）。
你的角色是 **高级开发工程师**。
你的目标是编写代码，实现统一配置加载机制和 schema 校验，确保关键配置缺失时服务启动立即失败并输出英文错误。

# Critical Rules (核心约束)
- **TypeScript Strict**: 禁止 `any`（若改动前端）。
- **Schema First**: 
  - 前端：对外 I/O、配置使用 Zod 校验，类型从 schema 推导。
  - 后端：配置使用 Pydantic BaseSettings 作为单一事实源。
- **不得硬编码**: 所有配置项必须通过环境变量或配置文件加载。
- **缺配置直接抛错并使测试失败**:
  - 关键配置缺失时服务启动必须立即失败（fail fast）。
  - 配置缺失导致的测试失败**不得 skip**。
- **错误 message 英文**: 对外错误消息必须为英文，便于日志检索。
- **Real Integration (No Skip)**: 测试必须连接真实服务；配置缺失或服务不可用**测试必须失败**并给出清晰英文错误。
- **Structured Errors**: 配置错误也应结构化或抛出清晰的英文异常消息。

# References
- PRD: docs/requirements.md（R14.5）
- TDD: docs/design.md（2.9 配置与密钥管理）
- AGENTS: AGENTS.md（配置化开发原则、`.env.local` 约束）
- tasks: docs/tasks.md（43.1）
- contracts: docs/contracts/api-and-events-draft.md（错误码）

# Execution Plan (具体步骤)

1) 后端实现配置模型与加载
- Files: `backend/gangqing/config.py`
- Action: 
  - 使用 Pydantic BaseSettings 定义配置模型
  - 支持从环境变量和 `.env.local` 加载（优先级：环境变量 > `.env.local`）
  - 配置分类：Database、LLM、Security、Audit、Tools、Observability
  - 实现配置校验器（validator）
  - 缺配置时抛出英文异常并使服务启动失败

2) 前端实现配置 schema 与加载
- Files: `web/src/config/index.ts`, `web/src/schemas/config.ts`
- Action:
  - 使用 Zod 定义配置 schema
  - 实现配置加载函数，支持运行时校验
  - 缺配置时在控制台输出英文错误并阻止应用启动

3) 编写测试用例
- Files: `backend/tests/test_config.py`, `web/src/config/config.test.ts`
- Action:
  - 单元测试：正常配置加载、缺配置快速失败、配置类型错误
  - 冒烟测试：`backend/scripts/config_validation_smoke_test.py`
  - 验证错误消息为英文

# Verification (验收标准)
- **Automated Tests**:
  - 后端单元测试 `pytest backend/tests/test_config.py -v` 必须通过
    - 正常配置加载（Happy Path）
    - 缺配置快速失败（至少 2 个关键配置项测试）
    - 配置类型错误（至少 2 个 Edge Cases）
  - 冒烟测试 `backend/scripts/config_validation_smoke_test.py` 必须通过
    - 验证配置缺失时服务启动失败
    - 验证错误消息为英文且清晰
- **Manual Verification**:
  - 移除 `DATABASE_URL`，运行 `python -m backend.gangqing.config`，验证立即失败并输出英文错误
  - 检查 `.env.local` 加载优先级是否正确

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段（如 Pydantic 模型定义、Zod schema、配置加载逻辑）。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Task 43.2 - 配置错误消息规范与错误码定义

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行配置外部化与配置校验下的子任务：43.2 - 配置错误消息规范与错误码定义。
你的角色是 **高级开发工程师**。
你的目标是统一定义配置相关的错误码、错误消息格式、以及配置校验失败的日志输出规范。

# Critical Rules (核心约束)
- **错误 message 英文**: 所有对外错误消息必须为英文。
- **结构化错误**: 配置错误应遵循全局错误模型：`code` + `message` + `requestId` + `retryable` + `details?`。
- **Schema First**: 后端使用 Pydantic 定义错误响应模型。

# References
- TDD: docs/design.md（6. 错误处理）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan (具体步骤)

1) 定义配置相关错误码
- Files: `backend/gangqing/errors.py`（或全局错误定义）
- Action:
  - 新增错误码：`CONFIG_MISSING`、`CONFIG_INVALID`、`CONFIG_TYPE_ERROR`
  - 定义标准错误消息模板
  - 更新全局错误码枚举

2) 更新配置校验失败处理
- Files: `backend/gangqing/config.py`
- Action:
  - 配置校验失败时抛出结构化错误
  - 日志结构化输出：包含 `code`、`config_key`、`timestamp`

3) 更新文档
- Files: `docs/contracts/api-and-events-draft.md`
- Action:
  - 补充配置相关错误码到错误码清单
  - 补充配置错误消息示例

# Verification (验收标准)
- **Automated Tests**:
  - 单元测试验证配置错误码正确定义
  - 测试配置校验失败时错误消息为英文且结构化
- **Manual Verification**:
  - 触发配置错误，检查日志输出格式

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**。
```

---

### Task 43.3 - `.env.example` 完整性与文档同步

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行配置外部化与配置校验下的子任务：43.3 - `.env.example` 完整性与文档同步。
你的角色是 **高级开发工程师**。
你的目标是完整列举所有配置项到 `.env.example`，并确保与代码中 schema 定义同步。

# Critical Rules (核心约束)
- **完整性**: `.env.example` 必须完整枚举所有配置项。
- **同步性**: 新增/修改配置必须同步更新 `.env.example`。
- **文档化**: 每个配置项必须包含说明、是否必填、默认值、示例值。

# References
- AGENTS: AGENTS.md（`.env.local` 约束）
- env: `.env.example`（目标文件）

# Execution Plan (具体步骤)

1) 分析现有配置需求
- Action:
  - 从后端 Pydantic 模型提取所有配置项
  - 从前端 Zod schema 提取所有配置项
  - 整理配置分类：Database、LLM、Security、Audit、Tools、Observability

2) 更新 `.env.example`
- Files: `.env.example`
- Action:
  - 按功能分组组织配置项
  - 每个配置项添加注释说明
  - 标注必填/选填、默认值、示例值

3) 建立同步机制（可选）
- Action:
  - 创建配置一致性校验脚本（可选，推荐）
  - 或建立 PR 检查清单强制同步

# Verification (验收标准)
- **Manual Verification**:
  - 检查 `.env.example` 与代码中配置模型的一致性
  - 验证 `.env.example` 中每个配置项都有说明
  - 验证 `.env.example` 未提交敏感信息

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**。
```

---

### Checklist（自检）

#### Umbrella 检查点
- [x] 是否包含了 `# Critical Rules` 并明确禁止写代码？
- [x] `# Execution Plan` 是否覆盖了该任务组下的所有子任务（43.1、43.2、43.3）？
- [x] 是否定义了全局性的技术标准（Schema 单一事实源、结构化错误、配置外部化、快速失败、真实集成测试）？
- [x] 是否包含最终的集成验收标准？

#### Sub-task 检查点
- [x] Task 43.1 是否明确列出了 **Target Files**？
- [x] Task 43.1 验收标准中是否包含具体的 **自动化测试断言**？
- [x] Task 43.1 是否强调了 **真实环境集成 (Real Integration)** 而非 Mock，并且明确"不可 skip"？
- [x] Task 43.1 是否包含了契约校验要求（Zod / Pydantic）？
- [x] Task 43.1 是否包含缺配置快速失败和英文错误消息要求？
- [x] 是否包含鉴权/RBAC/审计字段与结构化错误要求（如适用）？
- [x] Schema（Zod/Pydantic）？（本任务核心）
- [x] 真实集成测试 No Skip？
- [x] Doc References Updated
