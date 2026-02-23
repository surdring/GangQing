# Windsurf：Plan/Code 模式衔接与「Plans 交接包」使用指南

本文档描述如何在 Windsurf IDE 中使用 `plan` 与 `code` 两种模式完成任务，并将 `~/.windsurf/plans/*.md`（plan 模式生成物）作为 **权威交接包（handoff）** 驱动后续实现，避免范围漂移与约束丢失。

适用场景：
- 你的任务提示词文件位于 `docs/task-prompts/*.md`。
- `plan` 阶段需要做“决策/范围/验收标准”，`code` 阶段需要“落盘改代码/跑验证”。

---

## 1. 核心原则

- **Plan 产出必须可复制**：`plan` 模式最后必须输出一个可直接粘贴到 `code` 模式的“交接包”。
- **Code 不重新讨论需求**：`code` 模式严格按交接包实现；除非你显式批准，不得更改关键决策与范围。
- **一次只做一个可验证闭环**：子任务实现应以“能跑通验证命令”为退出标准，避免并行推进导致漂移。

---

## 2. Plan 模式应该产出什么（交接包规范）

在 `plan` 模式最后一轮，要求模型在输出末尾追加一个 **`CODE_HANDOFF`** 区块，建议固定结构如下：

```text
[CODE_HANDOFF]

1) Blockers（阻塞项）
- 当前仓库缺少哪些承载/配置/入口会导致无法跑验证？
- 需要你确认的前置决策（例如是否允许新增 backend/ 骨架）。

2) Non-negotiables（不可违背约束）
- 安全/隔离/审计/证据链/错误结构化/真实集成测试（No Skip）/配置外部化等。

3) Final Decisions（最终决策）
- 关键选型与不可变口径（例如主键类型、表关联方式、审计 append-only 策略、是否启用 RLS/分区）。

4) Scope & Out-of-scope（范围与禁止扩展）
- 本任务/子任务明确包含什么，不包含什么。

5) Acceptance Criteria（验收标准）
- 每个子任务必须可自动化验证（给出命令/脚本入口与关键断言）。

6) File Targets（落盘位置）
- 预计会改动/新增的目录与文件类型（例如 migrations、scripts、tests、config）。
```

---

## 3. Code 模式如何使用交接包（粘贴顺序）

进入 `code` 模式的新对话后，第一条消息必须包含：

1) **粘贴 `CODE_HANDOFF` 原文**（不要改写，避免信息损失）
2) **声明执行范围**：例如“现在只实现 Task 5.1”
3) **强制先列文件清单**：要求模型先输出“将修改/新增的文件路径列表”，再开始写代码

推荐模板：

```text
（粘贴 plan 输出的 [CODE_HANDOFF] 原文）

你现在处于 code 模式。
- 只实现：<子任务编号/名称>
- 除非我明确允许，否则不得更改 [CODE_HANDOFF] 的 Non-negotiables 与 Final Decisions。
- 开始前先列出你将新增/修改的文件路径清单（只列路径，不写代码）。
```

---

## 4. 以 T05（Postgres Schema）为例：如何利用 `~/.windsurf/plans/*.md`

### 4.1 识别 `~/.windsurf/plans/*.md` 的可复用区块

以 `~/.windsurf/plans/T05_postgres-schema-plan-*.md` 为例，通常包含：

- **阻塞项（Blockers）**：例如仓库是否缺少 `backend/`、迁移框架、pytest 入口等。
- **硬约束（Non-negotiables）**：Isolation、Evidence-first、append-only audit、结构化错误、真实集成测试、配置外部化。
- **最终决策（Final Decisions）**：例如主键类型、事实表设备关联方式、审计不可篡改落地方式、是否启用 RLS/分区。
- **可实现蓝图**：表清单、字段/约束/索引命名、迁移回滚策略、测试断言清单。

你在 `code` 模式实现 5.1/5.2/5.3 时，应按子任务只抽取对应章节：

- **Task 5.1（表/索引/约束）**：表清单 + 字段规范 + 具体表设计 + 索引策略
- **Task 5.2（迁移/回滚）**：迁移工具/目录/回滚边界 + upgrade->downgrade->upgrade 验证
- **Task 5.3（Unit+Smoke）**：断言清单 + 真实 Postgres 强制 + “配置缺失必须失败”

### 4.2 T05 的 code 模式开场模板（推荐）

```text
以下为 plan 模式产出的权威蓝图（摘自 ~/.windsurf/plans/T05_postgres-schema-plan-<id>.md），作为本次实现的不可变输入：

[Blockers]
- <粘贴阻塞项>

[Non-negotiables]
- <粘贴硬约束>

[Final Decisions]
- <粘贴最终决策>

现在进入 code 模式：先处理阻塞项（如需新增承载骨架），再进入 Task 5.1。
开始前先列出你将新增/修改的文件路径清单（只列路径，不写代码）。
```

---

## 5. 常见失败模式与修复办法

- **问题：code 模式开始“重新设计方案”，与 plan 冲突**
  - 修复：在 `code` 开场明确“不得改变 Final Decisions”，并要求先列文件清单再实现。

- **问题：plan 说 No Code，但输出了伪代码/SQL**
  - 修复：在 plan 阶段明确“只允许蓝图 Markdown，不允许 SQL/Alembic/代码片段”。

- **问题：真实集成测试被 skip 或用 mock 替代**
  - 修复：把“配置缺失必须失败（No Skip）”写入 Non-negotiables，并在 smoke 脚本中加入显式失败检查。

- **问题：隔离字段或索引漏掉**
  - 修复：把“每张核心表必须有 tenant_id/project_id + 对应索引”写入 Non-negotiables，并在单测/冒烟断言中硬性验证。

---

## 6. 最小检查清单（你在切换模式时要自检）

- [ ] plan 输出末尾是否包含可复制的 `[CODE_HANDOFF]`？
- [ ] code 开场是否粘贴了 handoff 原文并声明“不可改约束”？
- [ ] 是否一次只推进一个子任务闭环，并能跑通其验证命令？
- [ ] 是否所有错误 `message` 都为英文（便于日志检索）？
- [ ] 是否所有冒烟测试都连接真实服务（真实 Postgres），且配置缺失会失败？
