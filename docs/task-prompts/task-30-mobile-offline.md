# Task 30 - 移动端能力补齐：弱网/离线缓存（Umbrella + Sub-tasks）

## Umbrella Prompt

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 30 组任务：移动端能力补齐：弱网/离线缓存（手册/SOP/常见故障流程）与网络恢复自动同步。
你的角色是 **技术负责人/架构师**。
你的目标是定义离线包模型、缓存策略、同步状态机、权限与审计要求。

# Critical Rules
- **NO CODE IMPLEMENTATION**: 禁止输出实现代码。
- **Schema 单一事实源**: 前端离线包/同步状态 I/O 用 Zod；后端离线包分发/权限/审计用 Pydantic。
- **RBAC + 审计 + requestId**: 离线包分发与同步必须鉴权并审计。
- **结构化错误**: message 英文。
- **配置外部化**: 离线包存储地址、缓存 TTL、同步重试配置化并校验。
- **真实集成测试（No Skip）**: 冒烟必须连接真实后端并验证离线包下载与同步；缺配置必须失败。

# References
- Prompt Standard: `docs/promts/提示词标准2.0.md`
- PRD: `docs/产品需求.md`（#111-112、#250-261）
- tasks: `docs/tasks.md`（Task 30）

# Execution Plan
1) Task 30.1 - 前端：离线包管理、缓存策略与同步状态机
2) Task 30.2 - 后端：离线包分发与版本控制、权限校验
3) Task 30.3 - 冒烟：offline_mode_smoke_test（前端）+ offline_package_smoke_test（后端）

# Verification
- Unit: `npm test && pytest -q`
- Smoke: `node web/scripts/offline_mode_smoke_test.mjs && backend/scripts/offline_package_smoke_test.py`

# Output Requirement
输出 Markdown 规划，不要写实现代码。
```

## Sub-task Prompts

### Task 30.1 - 前端：离线包管理与同步状态机（Zod）

```markdown
# Context
你正在执行子任务：30.1 - 前端离线模式。
你的目标是实现离线包下载/缓存/校验/更新与同步状态机。

# Critical Rules
- **TypeScript Strict**: 禁止 any。
- **Schema 单一事实源**: Zod 校验离线包 manifest。

# References
- tasks: `docs/tasks.md`（Task 30）

# Execution Plan
1) 定义 manifest schema。
2) 实现缓存与同步。

# Verification
- `npm test` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 30.2 - 后端：离线包分发 + 版本控制 + RBAC

```markdown
# Context
你正在执行子任务：30.2 - 后端离线包分发。
你的目标是实现离线包分发接口与版本管理，并做 RBAC 与审计。

# Critical Rules
- **RBAC + 审计**: 下载必须鉴权并审计。
- **结构化错误**: message 英文。

# References
- tasks: `docs/tasks.md`（Task 30）

# Execution Plan
1) 定义 Pydantic 响应。
2) 实现下载与签名/校验（如适用）。

# Verification
- `pytest -q` 通过。

# Output Requirement
- 输出代码与测试。
```

### Task 30.3 - 冒烟：offline_mode_smoke_test.mjs + offline_package_smoke_test.py

```markdown
# Context
你正在执行子任务：30.3 - 离线模式冒烟。
你的目标是验证真实链路：后端分发离线包 -> 前端缓存 -> 模拟弱网 -> 恢复后同步。

# Critical Rules
- **真实集成测试（No Skip）**: 缺配置必须失败并英文报错。

# References
- tasks: `docs/tasks.md`（Task 30）

# Execution Plan
1) 后端冒烟：可下载离线包。
2) 前端冒烟：构建后跑离线流程。

# Verification
- 两个冒烟通过。

# Output Requirement
- 输出脚本。
```

## Checklist（生成后自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？
- [x] 是否包含证据链要求与字段？（离线包也需来源与版本，按适用性）
- [x] 是否包含只读默认与审批链要求（如涉及写操作）？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
