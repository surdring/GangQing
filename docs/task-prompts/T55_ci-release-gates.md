### Task 55 - （跨阶段）生产级发布与回归门禁：CI 触发（契约/单元/冒烟/Golden Dataset）+ 版本化发布 + 回滚策略（Umbrella）

```markdown
# Context
你正在执行第 55 号任务：生产级发布与回归门禁。
角色：**技术负责人/架构师**。
目标是规划 CI 门禁（契约/单元/冒烟/Golden Dataset）、版本一致性校验、发布与回滚策略，以及产物（报告/证据链）。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **门禁强制**: 合并前强制跑单元 + 冒烟 + 契约校验 + Golden Dataset 回归。
- **真实集成测试（No Skip）**: 冒烟/回归必须连真实服务，缺配置必须失败。
- **结构化错误**: 英文 message。
- **Evidence-First**: 回归报告必须包含版本证据与差异样本。
- **配置外部化**: CI 参数与阈值不得硬编码。

# References
- PRD: docs/requirements.md（R17.1）
- TDD: docs/design.md（7/8）
- tasks: docs/tasks.md（任务 55）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 55.1（CI 工作流：测试矩阵与门禁）
2) Task 55.2（版本一致性：文档/契约/口径/数据集版本）
3) Task 55.3（发布与回滚：可审计证据）

# Verification
- Unit: `pytest -q && npm -C web test`
- Smoke: `backend/scripts/full_pipeline_smoke_test.py && npm -C web run build`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 55.1 - CI 门禁：契约/单元/冒烟/Golden Dataset 全量回归

```markdown
# Context
你正在执行子任务：55.1 - CI 门禁：契约/单元/冒烟/Golden Dataset 全量回归。

# Critical Rules
- **失败即阻断合并**。
- **不得 skip**。

# References
- tasks: docs/tasks.md（55.1）

# Execution Plan
1) 配置 CI workflow。
2) 产出报告并存档。

# Verification
- **Smoke**: `backend/scripts/full_pipeline_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（回归证据/版本）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
