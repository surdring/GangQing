### Task 26 - OpenTelemetry traces/metrics：端到端链路追踪与关键指标采集（Umbrella）

```markdown
# Context
你正在执行第 26 号任务：OpenTelemetry traces/metrics：端到端链路追踪与关键指标采集。
角色：**技术负责人/架构师**。
目标是规划 trace/span 命名规范、最小链路覆盖（http.request/intent.classify/tool.query/llm.generate/evidence.build）、metrics 指标与标签字段（至少 requestId 关联策略），以及测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **可观测性（强制）**: 结构化日志与 trace/span 字段对齐，至少含 `requestId`。
- **脱敏（强制）**: span attributes 不得包含敏感数据或密钥。
- **配置外部化（强制）**: OTel endpoint、采样率不得硬编码。
- **真实集成测试（No Skip）**: 冒烟需连真实 OTel collector（如任务环境要求），缺配置必须失败并给英文错误。

# References
- PRD: docs/requirements.md（R12.1/R12.2）
- TDD: docs/design.md（2.8.2）
- tasks: docs/tasks.md（任务 26）

# Execution Plan
1) Task 26.1（Trace：span 列表与属性）
2) Task 26.2（Metrics：请求量/错误率/延迟/队列长度）
3) Task 26.3（冒烟验证：导出与采集）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/otel_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 26.1 - Trace/span：最小覆盖与属性脱敏

```markdown
# Context
你正在执行子任务：26.1 - Trace/span：最小覆盖与属性脱敏。

# Critical Rules
- **span 不得包含敏感信息**。

# References
- tasks: docs/tasks.md（26.1）
- PRD: docs/requirements.md（R12.1）

# Execution Plan
1) 在 HTTP 入站创建 root span。
2) 在意图识别/工具/推理/证据链建立 child spans。

# Verification
- **Smoke**: `backend/scripts/otel_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（观测不直接产出，但链路含 evidence.build span）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
