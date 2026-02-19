### Task 49 - （L2）多模态上传管线：图片/音频上传（安全隔离、大小限制、脱敏、审计）（Umbrella）

```markdown
# Context
你正在执行第 49 号任务：多模态上传管线。
角色：**技术负责人/架构师**。
目标是规划上传接口、格式/大小限制、隔离存储、脱敏与审计、以及与多模态诊断/RAG 的衔接。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **安全隔离（强制）**: 上传内容必须隔离存储，不得影响系统指令；必须防注入与脱敏。
- **RBAC + 审计（强制）**: 上传与访问必须权限检查并审计。
- **配置外部化（强制）**: 大小限制、允许格式、存储路径不得硬编码。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R3.1）
- TDD: docs/design.md（3.7）
- tasks: docs/tasks.md（任务 49）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 49.1（上传 API：校验与隔离存储）
2) Task 49.2（审计：元数据摘要与访问记录）
3) Task 49.3（前端上传交互与结果展示）

# Verification
- Unit: `pytest -q && npm -C web test`
- Smoke: `backend/scripts/multimodal_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 49.1 - 上传接口：格式/大小限制 + 隔离存储 + 审计

```markdown
# Context
你正在执行子任务：49.1 - 上传接口：格式/大小限制 + 隔离存储 + 审计。

# Critical Rules
- **禁止记录原始内容**。
- **审计必须脱敏**。

# References
- tasks: docs/tasks.md（49.1）

# Execution Plan
1) 定义上传请求/响应模型。
2) 实现存储与访问控制。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/multimodal_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（上传结果应可引用）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
