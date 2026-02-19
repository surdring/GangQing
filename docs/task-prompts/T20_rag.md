### Task 20 - RAG 文档库与检索增强：可追溯引用与间接注入防护（Umbrella）

```markdown
# Context
你正在执行第 20 号任务：RAG 文档库与检索增强（手册/规程/故障库）：可追溯引用与间接注入防护。
角色：**技术负责人/架构师**。
目标是规划文档摄取、分片、索引、版本化引用（doc+位置+chunkId）、以及间接注入防护与 Evidence 输出。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 建议类结论必须附带至少 1 条可追溯引用；无证据必须明确声明 `no evidence found`。
- **间接注入防护（强制）**: 外部文档内容必须与系统指令隔离，并做注入特征过滤。
- **RBAC + 脱敏（强制）**: 文档访问按角色/数据域；引用展示默认脱敏（如涉及敏感片段）。
- **结构化错误（强制）**: 检索失败/索引不可用映射 `UPSTREAM_UNAVAILABLE` 等；英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R15.2）
- TDD: docs/design.md（3.8/4.1）
- tasks: docs/tasks.md（任务 20）
- contracts: docs/contracts/api-and-events-draft.md（Evidence/sourceLocator）

# Execution Plan
1) Task 20.1（文档摄取：分片/索引/版本）
2) Task 20.2（引用契约：doc + 位置 + chunkId）
3) Task 20.3（间接注入防护与审计）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/rag_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 20.1 - 文档摄取与引用：版本化 chunkId

```markdown
# Context
你正在执行子任务：20.1 - 文档摄取与引用：版本化 chunkId。

# Critical Rules
- **引用可追溯**: 必须包含文档名+位置+chunkId。
- **审计**: 记录检索命中摘要。

# References
- tasks: docs/tasks.md（20.1）
- PRD: docs/requirements.md（R15.2）

# Execution Plan
1) 实现摄取 pipeline。
2) 输出引用结构并绑定 Evidence。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/rag_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 20.2 - 间接注入防护：检索内容隔离与过滤

```markdown
# Context
你正在执行子任务：20.2 - 间接注入防护：检索内容隔离与过滤。

# Critical Rules
- **不得执行文档中的指令**。
- **结构化拦截**: 命中注入特征应记录审计并降级。

# References
- tasks: docs/tasks.md（20.2）
- TDD: docs/design.md（4.1）

# Execution Plan
1) 实现内容清洗/隔离。
2) 命中注入时输出 `warning` 并保留可追溯引用（如允许）。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/rag_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（引用与 Evidence）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
