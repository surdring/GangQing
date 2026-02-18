# Requirements Traceability Matrix (RTM)
本 RTM 用于建立 GangQing（钢擎）需求（PRD/TDD/Tasks）到交付物与验收证据的可追溯闭环，确保 L1-L4 全量交付满足“只读默认/证据链/审计/RBAC/脱敏/熔断/requestId 贯穿”等强制约束。

## 1. 使用说明

### 1.1 字段定义（表头）
- `requirement_id`
  - 示例：`PRD-Phase1`、`PRD-F1.3`、`PRD-NFR-Security`、`TDD-7.2`、`TASK-1`。
- `requirement_text`
  - 需求摘要（中文描述，便于评审）。
- `phase`
  - `L1`/`L2`/`L3`/`L4`。
- `deliverable`
  - 文档/契约草案/配置规范/测试用例等（指向 `docs/` 的具体文件）。
- `verification_method`
  - `automated`/`manual`/`mixed`。
- `acceptance_evidence`
  - 验收取证材料清单（审计检索导出、日志片段、截图、测试报告等）。
- `owner`
  - 负责角色（技术负责人/安全负责人/后端/前端/数据/运维）。
- `status`
  - `draft`/`in_review`/`accepted`。

### 1.2 口径原则（强制）
- **单一事实源**：对外契约只允许 Zod（前端）/Pydantic（后端）作为事实源。
- **只读默认**：未显式授权与审批通过前，系统不得执行任何写操作。
- **Evidence Required**：任何数值结论必须可追溯到数据源与时间范围；禁止伪造 citation/evidence id。
- **RBAC & Masking**：所有接口/工具必须权限检查；敏感数据必须按角色脱敏。
- **Kill Switch**：写操作必须可熔断；熔断状态可审计、可观测。
- **Error Handling**：对外错误 `message` 必须英文；错误模型包含 `code/message/details?/retryable/requestId`。
- **Observability**：`requestId` 贯穿 HTTP→编排→工具→审计→响应。
- **多租户隔离**：`tenantId/projectId` 从 L1 起强制启用，默认过滤与审计。
- **对话流式**：SSE + WebSocket 同时支持（验收至少覆盖一种端到端链路）。
- **L4 写入范围**：包含 IT 写入与 OT 写入（OT 写入必须“专用通道 + OT 二次确认”，禁止直连反控）。
- **审计落地**：先 PostgreSQL 后 Elasticsearch（ES）。

## 2. MUST 主题追溯（最小集合）

| requirement_id | requirement_text | phase | deliverable | verification_method | acceptance_evidence | owner | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PRD-NFR-Safety | Read-Only Default：默认只读，写操作必须草案→审批/多签→受控执行→回滚→审计 | L1-L4 | docs/security/guardrails-and-kill-switch.md ; docs/acceptance/milestone-acceptance-checklist.md | mixed | 写操作拦截演示记录；审批链路审计导出；回滚点记录样例；熔断演练记录 | 安全负责人/后端 | draft |
| PRD-F1.3 | 结果可追溯：展示证据链（数据源、时间范围、公式版本、中间结果） | L1-L4 | docs/contracts/api-and-events-draft.md ; docs/acceptance/acceptance-evidence-pack.md | mixed | 证据链样例包（可验证/不可验证降级/越界）；按 requestId 关联证据链与审计 | 技术负责人/前端/后端 | draft |
| PRD-NFR-Security | RBAC 权限隔离：不同角色不可越权访问敏感域 | L1-L4 | docs/security/rbac-matrix.md ; docs/security/guardrails-and-kill-switch.md | mixed | 越权用例表；拒绝响应与英文错误模型；审计事件导出（AUTH_ERROR） | 安全负责人/后端 | draft |
| PRD-NFR-Masking | 数据脱敏：财务/工艺/配方等敏感数据按角色脱敏且可审计 | L1-L4 | docs/security/rbac-matrix.md ; docs/acceptance/acceptance-evidence-pack.md | manual | 脱敏前后对照（按角色）；脱敏行为审计事件导出 | 安全负责人/后端/前端 | draft |
| TDD-7.5 | Kill Switch：全局熔断写操作、强制降级仅查询，熔断可审计可告警 | L4 | docs/security/guardrails-and-kill-switch.md ; docs/acceptance/milestone-acceptance-checklist.md | mixed | 开启/关闭熔断的审计导出；拦截 Action 意图记录；告警触达证明 | 安全负责人/运维/后端 | draft |
| CODING-ERR | 结构化错误模型：`code/message/details?/retryable/requestId`，且 `message` 英文 | L1-L4 | docs/contracts/api-and-events-draft.md ; docs/acceptance/milestone-acceptance-checklist.md | automated | 契约测试报告（错误响应 schema）；接口示例与日志检索（英文 message） | 后端 | draft |
| CODING-REQID | requestId 贯穿：HTTP→编排→工具→审计→响应 | L1-L4 | docs/contracts/api-and-events-draft.md ; docs/acceptance/acceptance-evidence-pack.md | mixed | 从一次对话 requestId 追溯到 tool_call/audit/evidence 的闭环导出 | 后端/运维 | draft |
| TENANT-ISO | tenantId/projectId 从 L1 强制启用，多租户隔离与审计 | L1-L4 | docs/security/rbac-matrix.md ; docs/contracts/api-and-events-draft.md | mixed | 至少 2 条跨 tenant/project 访问拦截样例（含审计导出）；默认过滤证明（查询对账） | 安全负责人/后端 | draft |
| STREAM-2 | 对话流式协议：SSE + WebSocket 同时支持 | L1-L4 | docs/contracts/api-and-events-draft.md ; docs/acceptance/milestone-acceptance-checklist.md | manual | SSE 端到端录屏/抓包与事件样例；WS 端到端录屏/抓包与事件样例；事件可解析证明（含 error）；取消传播最小验证 | 前端/后端 | draft |
| OT-SEC | OT 写入：禁止直连反控，必须专用通道 + OT 二次确认 + 审计 | L4 | docs/security/guardrails-and-kill-switch.md ; docs/acceptance/milestone-acceptance-checklist.md | manual | OT 写入演练记录（含二次确认截图/记录）；专用通道说明；审计事件导出 | 安全负责人/运维 | draft |
| AUDIT-PG-ES | 审计落地：先 PostgreSQL 后 ES（检索增强），并可复核 | L1-L4 | docs/contracts/api-and-events-draft.md ; docs/acceptance/acceptance-evidence-pack.md | mixed | PG 审计表对账导出；ES 索引延迟与一致性抽样复核报告 | 运维/后端 | draft |

## 3. Roadmap/Phase 交付边界追溯

| requirement_id | requirement_text | phase | deliverable | verification_method | acceptance_evidence | owner | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PRD-Roadmap | Phase1-4（L1-L4）交付边界与试点范围清晰，验收指标模板固化 | L1-L4 | docs/roadmap/phase-l1-l4-scope.md ; docs/roadmap/phase-delivery-matrix.md | manual | 里程碑评审纪要；试点范围白名单；验收指标模板签署 | 技术负责人/产品 | draft |

## 4. 与 docs/tasks.md 的一致性追溯（Task 1）

| requirement_id | requirement_text | phase | deliverable | verification_method | acceptance_evidence | owner | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TASK-1 | 明确项目范围与里程碑（L1-L4）：边界、清单、验收、追溯闭环 | L1-L4 | docs/roadmap/* ; docs/acceptance/* ; docs/rtm/* ; docs/security/* ; docs/contracts/* | manual | 交付物清单与版本记录；评审通过记录 | 技术负责人 | draft |

## 5. 维护流程（变更控制）
- 任何新增 MUST/接口/事件字段：必须先更新 RTM → 更新对应 deliverable → 补齐验收证据采集方式。
- 任何涉及写操作/OT 写入/权限/脱敏/熔断的变更：必须触发安全评审与回归验收条目更新。
