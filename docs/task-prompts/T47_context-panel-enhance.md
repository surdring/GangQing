### Task 47 - （L1）前端 Context Panel 强化：“证据缺失/不可验证/降级态”表达与可追溯展开（Umbrella）

```markdown
# Context
你正在执行第 47 号任务：前端 Context Panel 强化。
角色：**技术负责人/架构师**。
目标是规划 Context Panel 的状态模型（完整/缺失/冲突/降级）、可追溯展开交互、与后端 warning/evidence 事件对齐。

# Critical Rules
- **NO CODE IMPLEMENTATION**。
- **Evidence-First（强制）**: 只展示可追溯证据；不可验证必须显式 UI 表达。
- **Schema 单一事实源**: 前端对外数据结构用 Zod。
- **TypeScript Strict**。
- **真实集成测试（No Skip）**。

# References
- PRD: docs/requirements.md（R6.2/R14.4/R13.3）
- TDD: docs/design.md（5.1）
- tasks: docs/tasks.md（任务 47）

# Execution Plan
1) Task 47.1（Evidence UI 状态：缺失/冲突/降级）
2) Task 47.2（可追溯展开：sourceLocator/timeRange/lineageVersion）

# Verification
- Unit: `npm -C web test`
- Smoke: `npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`

# 联调检查清单（Context Panel）
- [ ] Context Panel 的输入模型是否来源于“已校验”的数据（Zod 校验通过的 SSE 事件 payload 或 REST 响应），禁止直接渲染未校验的 `unknown`？
- [ ] 是否与后端事件对齐并能正确处理：
  - [ ] `evidence.update`（证据增量更新，可能多次出现）
  - [ ] `warning`（证据不足/不可验证/降级原因）
  - [ ] `final`（结束后证据面板状态稳定，不再闪烁/回退）
- [ ] evidence 增量合并策略是否明确（不会因为后续 update 缺字段导致“覆盖丢失”）？
- [ ] 是否只展示“可追溯证据”：
  - [ ] citations 至少包含数据源标识（source_system 或等价字段）
  - [ ] citations 必须包含 `time_range`
  - [ ] citations 必须包含 `extracted_at`
  - [ ] 涉及计算的结论是否展示 `lineage_version`（或按契约字段名）
- [ ] 当 evidence 不完整/缺失时，是否明确显示降级态（例如：缺证据、不可验证、仅展示数据与来源），并避免渲染出“看似可信”的引用？
- [ ] 当后端返回结构化错误（`error` 事件或 REST 错误）时，Context Panel 是否：
  - [ ] 不展示半成品伪证据
  - [ ] 保留 `requestId`（便于审计/排障）
- [ ] `backend/scripts/web_sse_e2e_smoke_test.py` 是否至少覆盖：
  - [ ] 正常链路含 `evidence.update`（如当前阶段支持）
  - [ ] 缺证据链路输出 `warning` 并在 UI 可见
  - [ ] 错误链路结构化 `error` 可解析且包含 `requestId`

# Output Requirement
输出执行蓝图，禁止写代码。
```

---

### Task 47.1 - Context Panel：证据缺失/不可验证/降级态 UI

```markdown
# Context
你正在执行子任务：47.1 - Context Panel：证据缺失/不可验证/降级态 UI。

# Critical Rules
- **不得展示伪造引用**。

# References
- tasks: docs/tasks.md（47.1）

# Execution Plan
1) 定义 EvidenceViewModel schema（Zod）。
2) 根据 `validation`/`warning` 渲染 UI。

# Verification
- **Unit**: `npm -C web test`
- **Smoke**: `backend/scripts/web_sse_e2e_smoke_test.py`

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。
- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。
- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- 输出验证命令与关键输出摘要（文本）。
```

---

### Checklist（自检）
- [x] 错误 message 英文？
- [x] 结构化错误字段？
- [x] 证据链要求与字段？（本任务核心）
- [x] 只读默认与审批链？
- [x] RBAC/审计/requestId？
- [x] Schema（Zod/Pydantic）？
- [x] 真实集成测试 No Skip？
