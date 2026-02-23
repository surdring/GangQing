# T04 数据域隔离与字段级脱敏落地蓝图

本蓝图定义 GangQing L1 阶段“默认隔离过滤 + 字段级脱敏 + 可审计”的权威落地方案：明确隔离维度模型、策略注入点、脱敏策略与配置 Schema、审计事件口径与测试验收口径。

## 0. 范围与强制约束（对齐权威文档）

- 隔离（Isolation）强制：所有数据读写**默认**按 `tenantId/projectId` 过滤；缺少隔离上下文必须快速失败；跨域访问必须拒绝并写审计。
- 脱敏（Masking）强制：财务/工艺参数/敏感配方等按角色字段级脱敏；Evidence/审计/日志默认脱敏（仅摘要 + 命中策略信息）。
- RBAC + 审计 + requestId 贯穿强制：HTTP 入站 → 工具调用 → Evidence → SSE/REST 输出 → 审计落库。
- 结构化错误强制：对外错误 `ErrorResponse(code/message/details?/retryable/requestId)`，且 `message` 必须英文。
- Schema 单一事实源强制：后端 Pydantic；前端如做事件/展示校验用 Zod。
- 配置外部化强制：隔离/脱敏策略、开关、默认行为必须配置化；禁止硬编码租户/产线/字段白名单到业务逻辑。
- 真实集成测试强制：冒烟/集成必须连真实 FastAPI + 真实 Postgres；缺配置/依赖不可用必须失败，不得 skip。

权威参考：
- PRD：`docs/requirements.md`（R1.3、R10.2）
- TDD：`docs/design.md`（4.4、6）
- Contracts：`docs/contracts/api-and-events-draft.md`（ErrorResponse/Evidence/Audit/SSE）
- OpenAPI：`docs/api/openapi.yaml`

## 1. 现状盘点（用于定位改造点）

### 1.1 已具备的基础能力（可复用）

- **RequestContext**：后端已通过 `X-Tenant-Id/X-Project-Id/X-Request-Id/...` 构建 `RequestContext`，且在缺少 tenant/project 时抛 `AUTH_ERROR`（英文 message）。
- **错误模型**：`AppError` + `ErrorResponse` 已存在，响应由 FastAPI exception handler 统一输出，并写审计。
- **审计落库**：`audit_log` 表插入使用 append-only，且 `action_summary` 会进行 `redact_sensitive()`（按 key 片段）脱敏。
- **RBAC 拒绝审计**：RBAC `FORBIDDEN` 会写 `rbac.denied` 审计事件。
- **隔离校验工具钩子**：存在 `require_same_scope(ctx, tenant_id, project_id)`（当前主要校验“参数中的 scope 与 ctx 一致”）。

### 1.2 当前缺口（本任务必须补齐）

- **字段级脱敏体系缺失**：当前仅有基于 key 片段的 redaction（password/token 等），未覆盖“财务/工艺/配方”等业务敏感字段，也缺少“按角色/按字段”的策略与证据链 redactions 结构。
- **默认过滤注入点需要系统化**：工具查询/语义 API/审计查询等必须统一执行 scope 过滤与跨域拒绝，不能依赖调用方“记得加 where”。
- **审计事件类型不完整**：contracts 期望 query/tool_call/response/error 等链路可追溯；现状审计类型枚举较少（虽可扩展为字符串）。
- **SSE error payload 同构**：SSE 中 error payload 需要严格同构 `ErrorResponse`（含 `requestId` 字段）；现状部分流式 error 事件 payload 可能缺少 `requestId` 字段（需按 contracts 口径统一）。

## 2. 隔离模型（Isolation Model）

### 2.1 隔离维度（最小集合 + 可扩展）

- **强制维度（L1）**：
  - `tenantId`：租户隔离
  - `projectId`：项目隔离
- **可扩展维度（L1 建模，L2+ 可启用）**：
  - `lineId` / `plantAreaId` / `workshopId`（产线/区域隔离）
  - `dataDomain`（数据域：finance/process/maintenance/...）

约束：
- 对外 `ErrorResponse` **不得**额外输出 tenant/project 等上下文（contracts 2.1）。
- SSE envelope **必须**包含 `tenantId/projectId`（contracts 6.1.2）。

### 2.2 “默认过滤”语义（必须明确）

- **默认过滤（Default Filter）**：凡是访问数据层（Postgres/外部系统）或返回可枚举数据集的接口，必须自动叠加：
  - `tenant_id = ctx.tenant_id`
  - `project_id = ctx.project_id`
  - 若启用扩展维度（如 `line_id`）：同样自动叠加
- **快速失败（Fail Fast）**：
  - 缺少 `tenantId/projectId`：`AUTH_ERROR`，英文 message 指明缺失 header（或缺失上下文）。
  - 任何“无法确定 scope”的情况都不允许降级为全量查询。

### 2.3 跨域检测与拒绝策略

跨域触发条件（至少包含）：
- **请求上下文与参数不一致**：
  - JWT token scope 与 header scope 不一致（现状已覆盖：`Invalid token scope`）
  - 工具/接口参数显式携带 scope，且与 ctx 不一致（现状 `require_same_scope` 可复用）
- **数据命中跨域**：在数据返回前发现记录 scope 不属于 ctx（例如 join 结果带出其他 tenant/project）。

拒绝策略：
- 默认返回 `AUTH_ERROR`（401）或 `FORBIDDEN`（403）需按端点契约：
  - **认证/上下文缺失/跨 scope**：倾向 `AUTH_ERROR`
  - **RBAC 能力不足**：`FORBIDDEN`
- **必须写审计**：事件类型建议为 `auth.denied`（跨域/缺 scope）或 `rbac.denied`（权限不足）。

## 3. 默认过滤注入点（后端）

> 目标：把“scope 强制叠加”从业务代码中抽离为可审计、可测试的统一机制。

### 3.1 API 层（FastAPI）

- **统一依赖**：所有需要数据访问的路由必须依赖 `require_authed_request_context`（确保 `userId/role` 可用）。
- **作用**：
  - 强制 requestId/tenantId/projectId 存在
  - 强制鉴权（JWT）与 scope 一致

### 3.2 工具层（Tool Layer）

- **工具入参 schema 必带 scope（建议）**：
  - 对“可被模型调用”的工具参数模型，建议包含 `tenant_id/project_id` 字段（与 ctx 对齐），并在工具入口调用 `require_params_scope()`。
  - 对“不暴露给模型、仅由服务端调用”的工具：可只从 ctx 注入 scope，不让外部传入，避免“越权指定 scope”的风险。

- **默认过滤实现策略（规划，不写代码）**：
  - 若工具基于 SQLAlchemy/text SQL：在 query 组装阶段统一追加 where 条件；并禁止调用方绕过。
  - 若工具基于表/视图模板：模板层强制包含 scope 条件（例如所有 fact/dim 表必须具备 tenant_id/project_id 列）。

### 3.3 数据层（Postgres）

- **Schema 约束（建议强制）**：所有业务表至少包含 `tenant_id/project_id` 列，并建立索引（tenant_id, project_id, 时间列）。
- **可选增强（后续）**：使用 RLS（Row Level Security）作为“第二道防线”，与应用层过滤互为冗余。

## 4. 字段级脱敏策略（Masking Policy）

### 4.1 敏感字段分类（建议最小分类）

- **Finance（财务）**：unit_cost、total_cost、profit、price、supplier_price、salary 等
- **Process（工艺）**：关键工艺参数、配方、控制目标、阈值、关键质量指标等
- **Recipe（敏感配方）**：配方明细、添加剂比例、专有工艺路线
- **PII（人员信息）**：手机号/身份证/邮箱等（如未来接入）

说明：分类仅作为策略配置的“领域标签”，字段集合必须配置化（见 5）。

### 4.2 角色 → 脱敏规则（策略表达）

- 输入：`role`（来自 JWT）、`dataDomain`（如可推导）、`resourceType`（表/实体/接口）、`fieldName`
- 输出：
  - `decision`: allow|mask|deny
  - `maskingMethod`: redacted|hash|range|round|bucket|partial（按场景）
  - `policyId`: 版本化策略 ID（用于审计/Evidence redactions）

建议规则（示例口径，最终以配置为准）：
- `finance` 角色：Finance 字段 allow，Process/Recipe 默认 mask 或 deny（看需求）
- `dispatcher/maintainer`：Finance 字段 mask（仅范围/等级），Process 可按白名单 allow
- `plant_manager`：可见范围更大，但 Recipe 仍可默认 mask（需显式 capability 才可展开）

### 4.3 “可展开（unmask）”的授权条件（强制设计）

- 默认：Evidence/UI/API 输出均为脱敏态。
- 展开查看原文需要：
  - **显式 capability**（例如 `finance:field:unmask` / `process:field:unmask` / `recipe:field:unmask`）
  - **二次审计事件**：`data.unmask`（建议新增）记录谁在何时对哪个 requestId 的哪条 evidence/字段做了展开（只记录定位信息 + 策略命中，不记录原文）。

## 5. 配置与 Schema（Config Externalization + Single Source of Truth）

### 5.1 后端配置项（ENV）规划（示例命名，最终应落到 Pydantic Settings）

- 隔离开关：
  - `GANGQING_ISOLATION_ENABLED=true|false`（默认 true）
  - `GANGQING_ISOLATION_EXTRA_DIMENSIONS=lineId,...`（可选）
- 脱敏策略：
  - `GANGQING_MASKING_POLICY_PATH=<path>`（指向策略文件；或使用 JSON 字符串配置）
  - `GANGQING_MASKING_DEFAULT_ACTION=mask|deny`（默认 mask）
  - `GANGQING_MASKING_AUDIT_INCLUDE_POLICY_HITS=true|false`（默认 true）
- 审计脱敏：
  - `GANGQING_REDACTION_SENSITIVE_KEY_FRAGMENTS=...`（现有）

强制要求：
- 配置缺失（例如策略路径不存在/无效）必须快速失败，错误 message 英文。

### 5.2 配置 Schema（Pydantic）

- **MaskingPolicy**（建议新增 Pydantic 模型）作为单一事实源：
  - `version`、`policyId`
  - `roles` 映射
  - `fieldRules`（fieldName/pattern → action/method/domain）
  - `domains`（Finance/Process/Recipe/PII）与字段集合
  - `capabilitiesForUnmask`
- **IsolationPolicy**（建议新增）:
  - `requiredDimensions`（tenantId/projectId/...）
  - `extraDimensions`（lineId 等）
  - `crossScopeErrorCode`（AUTH_ERROR/FORBIDDEN）可按端点或资源配置

前端（如需要）：
- Zod schema 仅用于校验 SSE 事件/Evidence/redactions 的展示输入，不作为后端权威。

## 6. 审计事件（Audit Events）与可审计口径

### 6.1 事件类型规划（对齐 contracts 4.1 + 现状扩展）

必须覆盖的事件（最小闭环）：
- `query`：用户发起查询（包含 query 摘要、domain 推断、是否触发脱敏）
- `tool_call`：工具调用（现状已具备）
- `api.response`：HTTP 响应结果（现状已具备）
- `auth.denied` / `rbac.denied`：拒绝类事件（现状已具备）

建议新增（用于脱敏可追溯）：
- `data.masked`：输出阶段发生字段脱敏（记录 policyId、fields、methods，不含原文）
- `data.unmask`：授权展开（记录谁对哪些 evidence/字段展开）

### 6.2 审计字段要求（必须）

- 必须字段：`requestId/tenantId/projectId/timestamp/eventType/result/errorCode?`
- actionSummary 必须：
  - **只记录摘要**（例如字段名列表、数量、范围）
  - **记录策略命中信息**（policyId、hitRules、maskedFields count）
  - 严禁写入敏感原值

## 7. Error Model（错误码与映射）

### 7.1 统一错误码使用规则

- `AUTH_ERROR`：
  - 缺少 `X-Tenant-Id/X-Project-Id`
  - JWT 无效/过期/签名不匹配
  - token scope 与 header scope 不一致
  - 参数 scope 与 ctx scope 不一致（跨域）
- `FORBIDDEN`：
  - RBAC capability 不满足（例如无权读取财务报表/无权展开原文）
- 其他错误保持既有映射：`VALIDATION_ERROR/NOT_FOUND/UPSTREAM_* / INTERNAL_ERROR` 等。

### 7.2 SSE 与 REST 同构（必须对齐 contracts）

- REST 非 2xx：响应体必须为 `ErrorResponse`。
- SSE：`type=error` 的 `payload` 必须为 `ErrorResponse`，且包含 `requestId` 字段（注意这是 payload 内字段，不是 envelope 的 requestId）。

## 8. 需要修改/新增的目录与文件清单（Deliverables: Directory Structure）

> 仅列出规划目标，不写具体实现代码。

### 8.1 后端（backend/）

- `backend/gangqing/common/settings.py`
  - 扩展 settings：新增 isolation/masking 相关 ENV + 校验（缺失快速失败）。
- `backend/gangqing/common/redaction.py`
  - 保留 key-fragment redaction（用于密钥/凭证），并补充“策略命中摘要”的通用脱敏工具（用于审计 actionSummary）。
- `backend/gangqing/tools/isolation.py`
  - 扩展支持“额外维度”（如 lineId）的一致性校验与错误 details 口径（不含敏感）。
- `backend/gangqing/common/audit_event_types.py`
  - 扩展事件类型（data.masked / data.unmask / query 等）或明确以字符串为准。
- `backend/gangqing/common/audit.py` & `backend/gangqing_db/audit_log.py`
  - 强化 actionSummary 的脱敏与“策略命中信息”落库口径。
- `backend/gangqing_db/*`（如 evidence/audit_query）
  - 确保 audit 查询同样按 tenant/project 默认过滤（现状已过滤，需纳入测试口径）。
- `backend/gangqing/api/*`（chat/semantic/data/audit/evidence）
  - 统一依赖：authed ctx + capability + masking 输出策略。

### 8.2 前端（web/）

- 若前端需要展示“已脱敏/可展开”：
  - `web/components/ContextPanel.tsx`（展示 redactions 摘要、展开按钮 gated by capability）
  - Zod schema（如已引入）用于 SSE event/Evidence 的校验（可选，视当前前端架构）。

### 8.3 脚本与测试

- `backend/tests/`：新增 isolation/masking 单元测试（不允许 skip）。
- `backend/scripts/rbac_and_masking_smoke_test.py`：按任务要求新增/补齐真实冒烟测试脚本。

## 9. 测试计划（Test Plan）

### 9.1 单元测试（pytest -q）覆盖点

必须覆盖（最小集合）：
- 缺少隔离上下文：请求/依赖构建 `RequestContext` 失败，返回结构化 `AUTH_ERROR`，英文 message。
- 跨域访问拒绝：
  - header scope 与 token scope 不一致 → `AUTH_ERROR`
  - tool params scope 与 ctx 不一致 → `AUTH_ERROR`
- 字段级脱敏结果随角色变化：
  - 同一资源在不同 role 下返回字段差异（allow/mask/deny）。
- 审计事件不出现敏感原文：
  - actionSummary 中仅摘要
  - 记录 policyId/fields 命中，不记录原值
- SSE error 同构：`type=error payload` 可被解析为 `ErrorResponse` 且含 `requestId`。

### 9.2 冒烟测试（真实 FastAPI + 真实 Postgres）

脚本：`backend/scripts/rbac_and_masking_smoke_test.py`（需落地）

覆盖链路：
- 成功路径（至少 1 条）：
  - 发起一次真实查询（REST 或 SSE）
  - 确认默认过滤生效（仅返回本 tenant/project 数据）
  - 确认响应字段已脱敏（并可看到 redactions 摘要/策略命中）
  - 确认审计表中存在对应 requestId 的链路事件
- 失败路径（至少 1 条）：
  - 构造跨域/越权（例如 scope 不一致或无 capability）
  - 返回结构化错误（`AUTH_ERROR` 或 `FORBIDDEN`，message 英文）
  - 审计表写入拒绝事件

注意：真实依赖缺失必须失败（不得 skip）。

## 10. 待确认问题（需要你确认后再进入实现）

1) 隔离扩展维度：L1 是否要求立刻纳入 `lineId/plantAreaId`？还是只建模预留、默认不开启？
2) “跨产线访问”在 PRD 中允许“空结果或 FORBIDDEN 错误”：你希望 L1 默认采用哪种？（建议：默认拒绝并审计，避免静默空结果导致误判）
3) 字段级脱敏的最小敏感字段集合：L1 是否先聚焦 Finance（成本/利润）+ Recipe（配方），还是 Process 关键参数也要同一批纳入？
4) 展开（unmask）能力：L1 是否需要真正提供“可展开查看原文”的 API/能力？还是只落“默认脱敏 + 不提供展开”？（若提供展开，需要新增 capability + 审计事件）

## 10.1 决策记录（按推荐固定，当前仅落盘不实现）

以下决策用于锁定 L1 交付范围，避免实现阶段契约漂移；如后续需要变更，应以“变更单/PR 评审”方式更新本节。

- **D1（隔离维度：L1 最小强制集）**
  - **Decision**：L1 仅强制 `tenantId/projectId`；`lineId/plantAreaId/workshopId` 等作为扩展维度**只建模预留**，默认不开启。
  - **Rationale**：先把 scope 贯穿与默认过滤打通，降低 schema/数据造数/索引改造面；扩展维度在 L2+ 通过配置开关启用。

- **D2（跨域/跨产线访问策略）**
  - **Decision**：默认 **拒绝 + 写审计**，不采用“静默空结果”。
  - **Error Code**：
    - 缺少隔离上下文：`AUTH_ERROR`
    - scope 不一致（header vs token / params vs ctx）：`AUTH_ERROR`
    - RBAC 能力不足：`FORBIDDEN`
  - **Rationale**：空结果容易造成业务误判并掩盖越权尝试；拒绝更符合“Fail Fast + 可审计”的安全要求。

- **D3（字段级脱敏：L1 最小覆盖面）**
  - **Decision**：L1 优先落 **Finance（成本/利润/价格等）+ Recipe（配方/添加剂比例等）** 两类；Process 关键参数在 L1 不作为强制范围（仅保留扩展机制）。
  - **Rationale**：先覆盖最敏感与最容易引发合规风险的数据域，避免一次性扩大策略配置与验收矩阵。

- **D4（是否提供 unmask 展开能力）**
  - **Decision**：L1 **不提供**“展开查看原文（unmask）”能力；统一以“默认脱敏输出 + 策略命中可审计”作为交付。
  - **Rationale**：unmask 会引入额外 capability、二次审计事件、前端交互与安全评审成本；先确保默认脱敏链路完整。

- **D5（数据库 RLS：是否在 L1 启用）**
  - **Decision**：L1 **不启用** PostgreSQL RLS 作为硬依赖；但将其明确为 L2+ 可选的第二道防线（Defense-in-Depth）。
  - **Rationale**：当前阶段以应用层默认过滤为主线，减少迁移复杂度；同时本仓库已具备 `set_config('app.current_tenant/project', ...)` 的前置条件，后续启用 RLS 具备可行性。

## 11. 全网最佳实践推荐（可落地到本仓库）

本节提炼业界关于“多租户/多项目隔离、字段级脱敏、审计可追溯”的最佳实践，并映射到本项目的落地点。

### 11.1 权威来源（建议在评审中作为引用依据）

- OWASP Multi-Tenant Security Cheat Sheet
  - https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html
- OWASP Authorization Cheat Sheet
  - https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- PostgreSQL 官方文档：Row Level Security
  - https://www.postgresql.org/docs/current/ddl-rowsecurity.html

### 11.2 租户/项目上下文：尽早建立、强校验、禁止“盲信客户端”

OWASP 强调：必须在请求生命周期尽早阶段建立 tenant context，并且**不要盲信客户端传入的 tenant id**。

对本项目的推荐（保持与 contracts 一致）：
- **权威 scope 来源**：以 JWT claims（或服务端 session）作为权威来源；`X-Tenant-Id/X-Project-Id` 作为“显式上下文”可用于路由/多实例，但必须与 token scope 一致。
- **Fail Fast**：缺 `tenantId/projectId` 直接 `AUTH_ERROR`（英文 message），不要退化为全量查询。
- **贯穿传播**：将 scope 作为 `RequestContext` 的必填字段贯穿到工具层、审计层、SSE envelope。

### 11.3 数据库隔离：Defense-in-Depth，优先考虑 RLS 作为第二道防线

PostgreSQL RLS 官方与 OWASP 都强调“默认拒绝（default deny）”与“纵深防御”。RLS 在未命中策略时会默认不返回任何行；并且需要注意 table owner / BYPASSRLS 等角色可能绕过。

对本项目的推荐分层策略（不改变你当前“应用层默认过滤”的主策略）：
- **第一道防线（应用层）**：所有查询/写入路径都必须显式叠加 `tenant_id/project_id` 条件（你当前蓝图的主线）。
- **第二道防线（数据库 RLS，可选启用）**：
  - 对核心业务表启用 RLS，并用会话变量（例如 `set_config('app.current_tenant', ...)`）驱动策略。
  - **强制**使用 `FORCE ROW LEVEL SECURITY`（避免 table owner 绕过）——这是 OWASP 示例中特别强调的点。
  - 明确禁止使用具备 `BYPASSRLS` 能力的数据库角色来跑应用业务查询。

落地点建议：
- 本仓库审计写入/查询已经在连接级别 `set_config('app.current_tenant/project', ...)`，这是未来引入 RLS 的“良好前置条件”。
- 即便 L1 不启用 RLS，也建议把“RLS 可启用”的表结构约束与迁移策略提前纳入设计评审（属于安全架构决策）。

### 11.4 防止跨租户/跨项目访问（IDOR）：任何资源查找都必须带 scope

OWASP Multi-Tenant 强调：仅凭 `resource_id` 的查找很容易造成 IDOR（越权读取其他租户资源）。

对本项目的推荐：
- **Repository/DAO 层统一加 scope**：任何 `get_by_id/list` 都必须包含 `tenant_id/project_id` 条件。
- **复合键思维**：对外暴露的资源定位尽量以 `(tenantId, projectId, id)` 作为事实上的复合约束（即使 URL path 中不显式带 tenant/project，也必须在数据层强制过滤）。
- **错误语义**：当资源存在但不属于当前 scope 时，建议返回 `NOT_FOUND` 或 `AUTH_ERROR/FORBIDDEN` 需要你统一口径；但无论返回哪种，都必须写审计并记录“cross-scope attempt”。

### 11.5 授权（Authorization）：最小权限 + 默认拒绝 + 每次请求都检查

OWASP Authorization Cheat Sheet 的关键点：
- **Deny by Default**：未匹配到规则也必须拒绝。
- **Validate on Every Request**：每一次请求都要校验权限，不允许“漏一个”。
- **Centralize**：把权限失败的处理逻辑集中化，避免分散在业务代码里。

对本项目的推荐：
- 保持你现有的 capability 模型（`require_capability`）并把“敏感字段展开（unmask）”纳入 capability 体系。
- 将“默认脱敏输出”视为一种授权结果（role/capability 决策），并在审计中记录 policyId/命中字段集合（仅字段名与策略，不含原值）。

### 11.6 日志与审计：记录上下文 + 监控隔离违规，但避免敏感信息落地

OWASP Multi-Tenant 与 Authorization 都强调：日志/审计要包含 tenant context，并监控跨租户访问尝试；同时避免在错误消息与日志中泄露敏感信息。

对本项目的可落地建议：
- **审计事件标准化**：
  - 每次拒绝（跨域/越权/缺 scope）必须写审计，事件类型可统一为 `auth.denied`/`rbac.denied` 并带 `details.reason`（英文 code + 结构化字段）。
- **策略命中可审计**：
  - 字段脱敏应写入“策略命中摘要”（policyId、fields、methods），但不写原值。
- **可观测告警**：
  - 对同一用户在短窗口内重复触发 cross-scope 的行为计数并告警（可以先在日志层实现，后续再引入指标/告警系统）。

## 12. 测试口径最终版（可验收清单）

本节将 T04 的测试要求固化为“可验收断言”，用于实现阶段对照；测试必须连接真实 FastAPI + 真实 Postgres，缺配置/依赖不可用必须失败，不得以任何形式 skip。

### 12.1 总体要求（强制）

- **必须执行的命令**：
  - Unit：`pytest -q`
  - Smoke：`backend/scripts/rbac_and_masking_smoke_test.py`
- **禁止 skip**：不得使用 `skip/xfail/条件跳过` 等任何形式绕过。
- **依赖缺失即失败**：
  - 缺少数据库连接配置/服务不可达：测试必须失败，并输出英文错误（便于 CI/日志检索）。
- **对外错误 message 英文**：所有失败路径必须验证返回的 `ErrorResponse.message` 为英文。
- **结构化错误同构**：REST 与 SSE 的错误体/错误事件必须可解析为 `ErrorResponse(code/message/details?/retryable/requestId)`。

### 12.2 单元测试（pytest -q）必测断言

#### 12.2.1 隔离上下文缺失（Fail Fast）

- **场景**：缺少 `X-Tenant-Id`。
  - **断言**：返回结构化错误 `code=AUTH_ERROR`。
  - **断言**：`message` 英文且明确缺少的 header 名称。
  - **断言**：包含 `requestId`。

- **场景**：缺少 `X-Project-Id`。
  - **断言**：返回结构化错误 `code=AUTH_ERROR`。
  - **断言**：`message` 英文且明确缺少的 header 名称。
  - **断言**：包含 `requestId`。

#### 12.2.2 跨域访问拒绝（header/token/params 与 ctx 不一致）

- **场景**：token scope 与 header scope 不一致。
  - **断言**：`code=AUTH_ERROR`（不是 200/空结果）。
  - **断言**：失败会写入审计（按 `requestId` 可检索到 `auth.denied` 或等价事件）。

- **场景**：工具/业务参数显式携带 `tenant_id/project_id` 且与 `RequestContext` 不一致。
  - **断言**：`code=AUTH_ERROR`。
  - **断言**：`details` 中不包含任何敏感原值（可包含 tenantId/projectId 这种隔离键）。

#### 12.2.3 RBAC 越权（能力不足）

- **场景**：无 capability 调用受保护资源（例如访问审计读取或财务域能力）。
  - **断言**：`code=FORBIDDEN`。
  - **断言**：写入 `rbac.denied` 审计事件，且 `actionSummary` 仅包含 capability/role 等摘要。

#### 12.2.4 字段级脱敏（按 D3：Finance + Recipe）

- **场景**：非 finance 角色访问 finance 域字段。
  - **断言**：响应中 finance 敏感字段被脱敏（不出现原值）。
  - **断言**：审计 `actionSummary` 不包含敏感原值。
  - **断言**：Evidence（如存在）包含 `redactions` 摘要（policyId/fields），且不含原值。

- **场景**：finance 角色访问 finance 域字段。
  - **断言**：允许返回（不脱敏或按策略返回），并仍保持审计不落敏感原值。

#### 12.2.5 SSE 错误事件同构（contracts 6.1）

- **场景**：触发任意错误（例如缺少 scope）。
  - **断言**：SSE `type=error` 事件的 `payload` 可解析为 `ErrorResponse`。
  - **断言**：`payload.requestId` 必须存在且与 envelope `requestId` 一致。
  - **断言**：`meta` 为首事件，`final` 为最后事件；错误路径必须 `error` 后紧随 `final(status=error)`。

### 12.3 冒烟测试（真实 FastAPI + 真实 Postgres）必测断言

脚本：`backend/scripts/rbac_and_masking_smoke_test.py`

#### 12.3.1 成功路径（至少 1 条）

- **前置**：真实 FastAPI 运行 + 真实 Postgres 可连接且已完成迁移/造数。
- **请求**：发起一次真实查询（REST 或 SSE 任一条关键链路）。
- **断言**：
  - 返回 2xx（或 SSE 以 `final(status=success)` 结束）。
  - 响应携带 `X-Request-Id`，且与响应体/事件中的 `requestId` 对齐。
  - 默认过滤生效：结果仅在当前 `tenantId/projectId` scope 内。
  - Finance/Recipe 字段按角色脱敏（不出现原始敏感值）。
- **审计断言**：通过 `requestId` 可在审计表检索到至少：
  - 1 条 `api.response`
  - 以及与该链路相关的 `tool_call`（如链路调用了工具）或 `query`（如有）。

#### 12.3.2 失败路径（至少 1 条）

- **请求**：构造跨域或越权（例如 token scope 与 header scope 不一致，或无 capability）。
- **断言**：
  - 返回结构化错误 `ErrorResponse`。
  - `message` 英文。
  - `requestId` 存在。
- **审计断言**：按 `requestId` 可检索到拒绝事件（`auth.denied` 或 `rbac.denied`）。

### 12.4 失败判定与取证要求（验收材料）

- **失败判定**：任何一条断言不满足即视为任务未达标；不得通过“跳过测试/忽略失败”方式收尾。
- **取证材料（建议）**：
  - SSE：保存 1 份成功链路与 1 份失败链路的事件样例（至少包含 `meta`、核心事件、`final`）。
  - 审计：保存按 `requestId` 检索到的事件记录摘要（字段脱敏后）。


