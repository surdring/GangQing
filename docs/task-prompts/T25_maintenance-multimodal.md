### Task 25 - 设备多模态诊断（图像/音频）+ 维修方案推荐 + 设备历史聚合（Umbrella）

```markdown
# Context
你正在执行第 25 号任务：设备多模态诊断（图像/音频）+ 维修方案推荐 + 设备历史聚合。
角色：**技术负责人/架构师**。
目标是规划多模态输入边界（隔离/脱敏/大小限制）、诊断输出约束（置信度/备选诊断）、维修方案证据要求（工单/手册/故障库引用），以及统一实体 ID 映射前置条件。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 诊断结论/维修建议必须绑定来源证据；无证据必须明确不确定。
- **安全隔离（强制）**: 图片/音频等外部内容不得影响系统指令；必须执行注入防护与脱敏。
- **RBAC + 脱敏（强制）**。
- **结构化错误**: 英文 message。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R3.1/R3.2/R3.3）
- TDD: docs/design.md（3.7/4.1）
- tasks: docs/tasks.md（任务 25）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 25.1（多模态输入处理：隔离/限制/审计）
2) Task 25.2（诊断输出：置信度 + 备选诊断 + Evidence）
3) Task 25.3（历史聚合：统一实体 ID 映射后聚合）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/maintenance_multimodal_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 25.1 - 多模态输入：安全隔离、大小限制、脱敏与审计

```markdown
# Context
你正在执行子任务：25.1 - 多模态输入：安全隔离、大小限制、脱敏与审计。

# Critical Rules
- **配置外部化**: 最大文件大小、允许格式。
- **审计**: 记录上传元数据摘要（不记录原始内容）。

# References
- tasks: docs/tasks.md（25.1）
- TDD: docs/design.md（3.7）

# Execution Plan
1) 定义上传/处理接口的 Pydantic 模型。
2) 实现隔离存储与权限校验。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/maintenance_multimodal_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
