## 5. 给 AI 提示词生成器的元指令

如果你正在使用 AI（如 ChatGPT/Claude）来为你生成项目提示词，请使用以下 Prompt：

```text
请参考《提示词标准2.0.md》，为我生成 GangQing（钢擎）项目 Task {N} 的完整提示词文档。

要求：
1. 请严格遵守 "Umbrella + Sub-tasks" 的模式。
2. 首先生成 Umbrella Prompt，重点在于规划和约束，禁止包含代码。
3. 然后依次生成 Task {N}.1 到 {N}.M 的 Sub-task Prompts，重点在于具体的文件修改和测试策略。

4. 所有 Context / Constraint 必须与 GangQing 项目上下文一致，并明确引用以下权威文档：
- PRD: docs/requirements.md
- TDD: docs/design.md
- tasks: docs/tasks.md
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/*.md

5. 必须显式写入且不可弱化的硬约束（在 Umbrella 与每个 Sub-task 的 `# Critical Rules` 中都要出现，按适用性裁剪）：
- Schema 单一事实源：前端对外 I/O/配置用 Zod；后端对外 I/O/工具参数/Evidence/审计事件用 Pydantic。
- 证据链（Evidence-First）：数值结论与关键建议必须可追溯（数据源、时间范围、口径版本、工具调用、数据质量）。不可验证则降级为“仅展示数据与来源/不确定项”。
- 只读默认（Read-Only Default）：未显式授权与审批前不得执行写操作；写操作只允许“草案 -> 审批/多签 -> 受控执行 -> 回滚点 -> 审计”。
- RBAC + 审计：所有接口/工具必须做权限检查并记录审计；`requestId` 必须贯穿（HTTP 入站 -> Agent 编排 -> 工具调用 -> 对外响应）。
- 结构化错误：对外错误必须包含 `code`/`message`(英文)/`details?`/`retryable`/`requestId`。
- 流式输出：长耗时场景优先 SSE/流式事件，事件中错误也必须结构化可解析。
- 配置外部化：URL/端口/超时/重试/API Key 不得硬编码；必须通过统一配置加载并校验。
- 真实集成测试（No Skip）：
  - 测试必须连接真实服务；配置缺失或服务不可用必须失败并给出英文错误信息。
  - 禁止使用 mock/stub 替代外部服务连接层（单元测试允许依赖注入 fake，但必须保留真实错误语义）。

6. 输出格式要求：
- 按顺序输出：Umbrella Prompt -> Task {N}.1 ... Task {N}.M。
- 每个 Prompt 必须包含：`# Context` / `# Critical Rules` / `# References` / `# Execution Plan` / `# Verification` / `# Output Requirement`。
- `# References` 必须使用仓库真实路径（例如 `docs/产品需求.md`），禁止虚构路径。

7. 生成后自检清单（必须在文末输出一份 Checklist，并逐项打勾/标注结果）：
- 是否所有错误 `message` 都是英文？
- 是否包含结构化错误模型字段？
- 是否包含证据链要求与字段？
- 是否包含只读默认与审批链要求（如涉及写操作）？
- 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- 是否包含真实集成测试且不可 skip 的要求？