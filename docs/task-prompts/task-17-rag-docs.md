# Task 17 - L2 文档库 + RAG（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 17 组任务：L2 文档库 + RAG：设备手册/故障库/工艺规范 的检索增强（含间接注入防护）。
你的角色是 **技术负责人/架构师**。
你的目标是定义文档入库与权限域、检索与引用（citations）契约、以及间接注入防护策略与验收口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端对外 I/O/配置用 Zod；后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic。
- **Evidence-First**: RAG 结论必须输出 citations（文档来源、段落定位、时间/版本信息）；不可验证必须降级为“不确定项/仅展示来源”。
- **Read-Only Default**: 默认只读；文档入库属于受控数据写入，必须走权限与审计（若引入审批则预留）。
- **RBAC + 审计 + requestId 贯穿**: 文档访问必须按权限域控制并审计；`requestId` 贯穿检索与引用。
- **结构化错误**: `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- **流式输出（SSE）**: 检索与生成过程需输出 progress；错误事件结构化。
- **配置外部化**: 向量库/索引服务地址、超时、重试不得硬编码；统一配置加载并校验。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实文档库/向量索引服务；缺配置或服务不可用必须失败并给出英文错误。
- **安全（间接注入防护）**: 外部内容隔离；禁止把检索内容当作系统指令执行。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#3、F2.1、知识库）
- TDD: `docs/技术设计文档-最佳实践版.md`（#10.1、#3.1）
- tasks: `docs/tasks.md`（Task 17）

# Execution Plan
1) Task 17.1 - 文档数据模型与入库管线（版本化、权限域、审计）
2) Task 17.2 - 检索工具（只读）与 citations 生成（Evidence 对齐）
3) Task 17.3 - 间接注入防护：内容隔离、过滤、提示词分区
4) Task 17.4 - 冒烟：rag_smoke_test.py（真实服务）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/rag_smoke_test.py`

# Output Requirement
输出 Markdown 规划与验收口径，不要写实现代码。
```

## Sub-task Prompts

### Task 17.1 - 文档入库：版本化 + 权限域 + 审计

```markdown
# Context
你正在执行子任务：17.1 - 文档入库管线。
你的目标是实现文档元数据模型、存储与入库接口（含版本化、权限域、审计），并保证敏感内容不被越权访问。

# Critical Rules
- **RBAC + 审计**: 入库与访问必须鉴权并审计。
- **Schema 单一事实源**: 入参/出参用 Pydantic。
- **结构化错误**: message 英文。

# References
- tasks: `docs/tasks.md`（Task 17）

# Execution Plan
1) 定义文档元数据表/模型。
2) 实现入库接口与审计落库。

# Verification
- 冒烟：可入库并可按权限查询。

# Output Requirement
- 输出代码与测试。
```

### Task 17.2 - RAG 检索工具：输出 citations（文档来源/段落定位）

```markdown
# Context
你正在执行子任务：17.2 - RAG 检索与 citations。
你的目标是实现检索工具与引用生成，把检索结果以 Evidence citations 形式输出。

# Critical Rules
- **Evidence-First**: citations 必须包含来源文档、段落定位、版本/时间信息。
- **Read-Only Default**: 检索只读。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#5）
- tasks: `docs/tasks.md`（Task 17）

# Execution Plan
1) 定义检索输出模型。
2) 组装 citations 并脱敏。

# Verification
- 单元测试：citations 字段完整。

# Output Requirement
- 输出代码与测试。
```

### Task 17.3 - 安全：间接注入防护（内容隔离 + 过滤）

```markdown
# Context
你正在执行子任务：17.3 - 间接注入防护。
你的目标是确保检索内容不会改变系统策略，不会被当成系统指令执行。

# Critical Rules
- **安全分区**: 外部内容必须隔离为“参考材料”，不得覆盖系统规则。
- **输出过滤**: 过滤恶意指令与敏感信息泄露特征。

# References
- TDD: `docs/技术设计文档-最佳实践版.md`（#10.1）
- tasks: `docs/tasks.md`（Task 17）

# Execution Plan
1) 定义内容分区与安全标签。
2) 增加过滤/清洗策略。

# Verification
- 单元测试：恶意内容被降级/剔除并产生 warning。

# Output Requirement
- 输出代码与测试。
```

### Task 17.4 - 冒烟：rag_smoke_test.py（真实文档库/索引服务）

```markdown
# Context
你正在执行子任务：17.4 - RAG 冒烟。
你的目标是实现 `backend/scripts/rag_smoke_test.py`，连接真实文档库/向量索引服务，验证检索->引用->回答链路。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置或服务不可用必须失败并输出英文错误。

# References
- tasks: `docs/tasks.md`（Task 17）

# Execution Plan
1) 读取配置并探活依赖服务。
2) 发起检索并断言 citations 存在。

# Verification
- 冒烟脚本通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（RAG citations）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？（文档入库按受控写入处理）
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
