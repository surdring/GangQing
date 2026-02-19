### Task 6 - 实现可复现造数脚本（Umbrella）

```markdown
# Context
你正在执行第 6 号任务：实现可复现造数脚本（覆盖异常/边界，用于降级与 guardrail 验证）。
角色：**技术负责人/架构师**。
目标是规划造数数据集的覆盖范围、可复现性策略、异常/边界样本、与冒烟/回归使用方式，并明确测试口径。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First**: 造数必须支持证据链演示（可定位到表/主键/时间范围）。
- **真实集成测试（No Skip）**: 冒烟测试必须连接真实 Postgres。
- **配置外部化**: 种子/规模/时间范围通过配置或参数化，禁止硬编码。

# References
- PRD: docs/requirements.md（R7.2/R14.4）
- TDD: docs/design.md（2.6.2）
- tasks: docs/tasks.md（任务 6）

# Execution Plan
1) Task 6.1（造数脚本框架与种子策略）
- 同种子同数据；版本变更可追溯。

2) Task 6.2（异常/边界覆盖）
- 缺失值、延迟到达、重复记录、极端波动。

3) Task 6.3（数据集用于测试）
- 冒烟/回归统一使用该数据集；依赖缺失必须失败。

# Verification
- Unit: `pytest -q`
- Smoke: `backend/scripts/seed_data_smoke_test.py`

# Output Requirement
输出执行蓝图（Markdown），禁止写代码。
```

---

### Task 6.1 - 造数脚本：可复现与异常/边界覆盖

```markdown
# Context
你正在执行子任务：6.1 - 造数脚本：可复现与异常/边界覆盖。
目标是实现造数脚本，把最小数据模型填充为可开发、可冒烟、可回归的数据集。

# Critical Rules
- **可复现性**: 同 seed 输出一致。
- **真实集成测试（No Skip）**: 造数必须写入真实 Postgres，配置缺失必须失败。

# References
- PRD: docs/requirements.md（R7.2）
- tasks: docs/tasks.md（6.1）

# Execution Plan
1) 实现造数入口：支持 seed 与规模参数。
2) 覆盖异常样本：缺失/重复/延迟/极端波动。

# Verification
- **Unit**: `pytest -q` 覆盖：同 seed 一致性（允许通过“可注入 RNG/seed”实现）。
- **Smoke**: `backend/scripts/seed_data_smoke_test.py`

# Output Requirement
输出修改文件完整内容 + 测试命令与关键输出。
```

---

### Checklist（自检）
- [x] 是否所有错误 `message` 都是英文？
- [x] 是否包含结构化错误模型字段？（全局规则已包含）
- [x] 是否包含证据链要求与字段？（强调可定位与 time_range）
- [x] 是否包含只读默认与审批链要求？
- [x] 是否包含 RBAC 与审计、`requestId` 贯穿要求？（与审计关联在全局规则中保留）
- [x] 是否包含 Schema（Zod/Pydantic）与契约对齐要求？
- [x] 是否包含真实集成测试且不可 skip 的要求？
