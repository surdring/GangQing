### Task 11 - 接入 llama.cpp 推理服务（超时/错误码映射/健康检查联动）（Umbrella）

```markdown
# Context
你正在执行第 11 号任务：接入 llama.cpp 推理服务（超时/错误码映射/健康检查联动）。
角色：**技术负责人/架构师**。
目标是规划 llama.cpp 适配层接口、超时/不可用错误映射、健康检查联动（unhealthy/degraded），以及真实集成测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **配置外部化（强制）**: llama.cpp base URL、超时、并发上限不得硬编码；必须加载并校验。
- **结构化错误（强制）**: 不可用/超时映射 `UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT`，英文 `message`。
- **可观测与审计（强制）**: 推理调用写审计（tool_call 或等价事件），包含 `requestId`。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实 llama.cpp；缺配置必须失败。

# References
- PRD: docs/requirements.md（R9.1/R12.3）
- TDD: docs/design.md（2.7.1/2.7.2/2.9）
- tasks: docs/tasks.md（任务 11）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) Task 11.1（llama.cpp 适配层接口与配置）
2) Task 11.2（错误映射与重试/降级策略对齐）
3) Task 11.3（健康检查联动）

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/llamacpp_smoke_test.py`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 11.1 - llama.cpp 适配层：配置化接入与错误映射

```markdown
# Context
你正在执行子任务：11.1 - llama.cpp 适配层：配置化接入与错误映射。
目标是实现对 llama.cpp 的最小调用封装，并确保结构化错误与审计对齐。

# Critical Rules
- **配置外部化**: base URL/timeout。
- **结构化错误**: 连接失败/超时映射稳定错误码。
- **审计**: 记录调用耗时与结果摘要（去敏）。

# References
- tasks: docs/tasks.md（11.1）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan
1) 实现 HTTP 客户端封装与超时。
2) 统一错误映射。

# Verification
- **Unit**: `pytest -q`
- **Smoke**: `backend/scripts/llamacpp_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Task 11.2 - 健康检查联动：unhealthy/degraded 判定

```markdown
# Context
你正在执行子任务：11.2 - 健康检查联动：unhealthy/degraded 判定。
目标是把 llama.cpp 状态纳入健康检查，并区分依赖不可用与系统降级态。

# Critical Rules
- **结构化错误**: 健康检查失败也要提供可读英文信息（不泄露密钥）。
- **配置校验**: 关键配置缺失必须快速失败。

# References
- PRD: docs/requirements.md（R12.3）
- tasks: docs/tasks.md（11.2）
- TDD: docs/design.md（2.9）

# Execution Plan
1) 在健康检查中探测 llama.cpp。
2) 将结果映射为 unhealthy/degraded。

# Verification
- **Smoke**: 通过 `backend/scripts/llamacpp_smoke_test.py` 与健康检查脚本验证。

# Output Requirement
输出修改文件完整内容 + 测试命令。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（作为全局约束保留）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
