### Task 18 - 健康检查与运行态自检（依赖状态/降级态/版本信息）（Umbrella）

```markdown
# Context
你正在执行第 18 号任务：健康检查与运行态自检（依赖状态/降级态/版本信息）。
角色：**技术负责人/架构师**。
目标是规划健康检查端点契约、依赖探测（Postgres/llama.cpp/关键配置）、unhealthy/degraded 判定、以及冒烟测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **配置校验（强制）**: 关键配置缺失必须快速失败，英文错误消息。
- **结构化错误（强制）**: 健康检查失败响应也必须结构化（若对外暴露）。
- **真实集成测试（No Skip）**: 冒烟必须连接真实依赖；缺配置必须失败。

# References
- PRD: docs/requirements.md（R12.3）
- TDD: docs/design.md（2.9）
- tasks: docs/tasks.md（任务 18）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 18.1（健康检查端点与响应模型）
2) Task 18.2（依赖探测：Postgres/llama.cpp/配置完整性）
3) Task 18.3（冒烟脚本对齐）

# Verification
- Unit: `pytest -q`
- Smoke: `python backend/scripts/start_server_and_healthcheck.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 18.1 - 健康检查：依赖状态与 degraded/unhealthy 区分

```markdown
# Context
你正在执行子任务：18.1 - 健康检查：依赖状态与 degraded/unhealthy 区分。
目标是实现健康检查端点，返回系统与依赖的状态摘要，并可用于告警。

# Critical Rules
- **不泄露敏感信息**: 不返回密钥/连接串。
- **英文 message**。

# References
- tasks: docs/tasks.md（18.1）
- TDD: docs/design.md（2.9）

# Execution Plan
1) 定义 Pydantic HealthResponse 模型。
2) 探测 Postgres 与 llama.cpp。
3) 缺配置直接失败并给出英文错误。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `python backend/scripts/start_server_and_healthcheck.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（不适用；本任务为健康检查，但仍遵守全局规则）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（健康检查通常无需，但若有鉴权也需遵守）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
