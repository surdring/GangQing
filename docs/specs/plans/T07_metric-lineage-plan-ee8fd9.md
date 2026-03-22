# Task 7（指标口径仓库）执行蓝图

本蓝图定义指标口径（Metric Lineage）的实体/版本化策略与“计算必须绑定 lineageVersion”的强制校验链路，并与 Evidence、错误模型、RBAC 与审计契约一致对齐。

## 0. 范围与不变式（必须遵守）

- **Evidence-First**：任何“计算/聚合型指标结论”必须绑定明确 `lineageVersion` 并写入 Evidence；无法确定版本时必须拒答或降级。
- **拒答/降级（强制）**：
  - **口径缺失**：不得输出确定性结论；必须拒答或降级为“仅展示数据与来源/不确定项”。
  - **口径冲突**：不得自动选择一个版本；必须拒答并要求指定版本。
- **Schema First（后端 Pydantic 单一事实源）**：后端对外 I/O、工具参数、Evidence、审计事件都必须由 Pydantic 模型定义，并在输出前做序列化校验。
- **Structured Errors（强制）**：对外错误固定为 `code` + `message(英文)` + `requestId` + `retryable` + `details?`。
- **RBAC & Audit（强制）**：读取口径、执行绑定、工具调用、计算请求都必须权限检查并记录审计（至少 `requestId`；可用时补齐 `sessionId/taskId/stepId/toolName`）。
- **Read-Only Default（强制）**：本任务只涉及口径元数据与只读查询；任何写操作能力仅 L4 草案/审批治理，不在本任务引入。
- **Real Integration（No Skip）**：冒烟/集成必须连真实 Postgres；配置缺失或依赖不可用必须失败。

## 1. 现状盘点（已存在的权威实现/契约）

### 1.1 契约层（docs）

- Evidence 对外契约：`docs/contracts/api-and-events-draft.md#3 Evidence`
  - Evidence 字段包含：`lineage_version?`（文档中字段名为 snake_case，但同时声明 Evidence 对外字段 `lineageVersion`）。
- 错误模型：`docs/contracts/api-and-events-draft.md#2 ErrorResponse`
  - 限制：ErrorResponse 对外仅允许 `code/message/details?/retryable/requestId`。

### 1.2 前端 schema（Zod）

- 错误：`web/schemas/errorResponse.ts` 已与 contracts 对齐。
- SSE envelope：`web/schemas/sseEnvelope.ts` 当前是“顶层 envelope 字段 + payload”的形态（与 contracts 文档中 `type + envelope + payload` 的版本存在差异）。
  - Task 7 不直接改 SSE 协议，但后续任何新增事件/字段必须谨慎避免契约漂移。

### 1.3 后端口径仓库（已存在、可作为本任务权威落地点）

- 指标口径仓库核心模块：`backend/gangqing_db/metric_lineage.py`
  - 版本策略已固定为 **SemVer (X.Y.Z)**，并在 Pydantic validator + DB check constraint 强制。
  - `MetricLineageRecord.lineage_version` 在对外模型层别名为 `lineageVersion`。
  - 关键规则已经实现：
    - `get_metric_lineage`：
      - 指定 `lineageVersion` 时必须命中且唯一，否则 `EVIDENCE_MISSING` / `EVIDENCE_MISMATCH`。
      - 未指定版本时，仅当“恰好一个 active”才允许，否则 `EVIDENCE_MISSING` / `EVIDENCE_MISMATCH`。
    - `bind_metric_lineage_for_computation`：
      - 默认 **不允许** 缺失 `lineageVersion`（除非 `scenarioKey` 或显式允许 `allow_default_active=True`）。
      - 会生成 Evidence（`Evidence.lineageVersion`）并可写审计事件。
  - RBAC：统一 capability `metric_lineage:read`。
- Evidence Pydantic：`backend/gangqing_db/evidence.py`
  - `Evidence.lineage_version` 对外 alias 为 `lineageVersion`。
- DB 约束：`backend/migrations/versions/0002_metric_lineage_semver_and_active_unique.py`
  - SemVer check constraint
  - “同 scope 同 metric 仅允许一个 active”部分唯一索引（`is_active=true`）。

### 1.4 测试资产（已存在）

- 单元测试：`backend/tests/test_metric_lineage.py`（覆盖缺失/冲突/拒答/审计写入/证据字段完整性）。
- 冒烟测试：`backend/scripts/metric_lineage_smoke_test.py`（真实 Postgres + migration + seed + 查询/绑定行为）。

## 2. Task 7 的目标收敛（你要验收的“必须成立”）

- **G1：口径实体可权威查询**
  - 对任意 metric：
    - 指定 `lineageVersion` => 必须唯一命中；否则结构化错误。
    - 不指定 `lineageVersion` => 默认拒绝；若允许 default active，则只能在“唯一 active”时成功。
- **G2：指标计算入口必须绑定 `lineageVersion`**
  - 任意计算/聚合型指标输出（包括服务端聚合、工具聚合、Agent 生成的数值结论）必须在 Evidence 内带 `lineageVersion`。
  - 缺失时：
    - 要么 **拒答**（推荐，返回 `EVIDENCE_MISMATCH` + reason `lineage_version_required`）。
    - 要么 **降级**（仅展示原始数据与来源 + warning），但不得输出确定性计算结果。
- **G3：口径冲突不自动择优**
  - 多 active / 多记录冲突：必须拒答（`EVIDENCE_MISMATCH`）。
- **G4：对外字段命名一致**
  - 后端 Pydantic 对外统一使用 `lineageVersion`（camelCase）。
  - DB/内部字段为 `lineage_version`（snake_case）。
  - Evidence 对外字段为 `lineageVersion`（与前端/契约一致）。

## 3. 指标口径实体（Metric Lineage）规划与约束

### 3.1 实体字段（权威：Pydantic + DB）

- **MetricLineageRecord（对外）**
  - `metric_name`
  - `lineageVersion`（SemVer）
  - `status`：`draft|active|deprecated|retired`
  - `formula?`：口径公式（文本）
  - `source_systems?`：引用的数据源系统列表（仅用于追溯摘要，不展开外部系统字段映射细节）
  - `owner?`：责任人
  - `is_active`：是否作为默认 active
  - `created_at?`
  - `tenantId/projectId`：隔离字段（对外可出现在口径记录中；但注意 ErrorResponse 不允许输出这些上下文）

### 3.2 唯一性与一致性（DB 强制）

- **同 scope（tenant_id, project_id）同 metric_name**：最多一个 `is_active=true`。
- `lineage_version` 必须 SemVer。
- 如果出现 duplicate records（同 metric_name + lineage_version 多条）：视为数据一致性问题，必须 `EVIDENCE_MISMATCH` 拒答并提示修复。

### 3.3 版本化策略（关键决策已在代码中固化）

- 主版本策略：**SemVer (X.Y.Z)**。
- 语义建议（用于流程与治理，但不引入写能力）：
  - `major`：口径定义发生破坏性变化（跨报表/跨系统对齐变化）
  - `minor`：非破坏性扩展（新增来源字段/新增过滤项）
  - `patch`：修订（bugfix/描述修正）

## 4. 口径绑定规则（计算前置门禁）

### 4.1 输入（建议抽象为“绑定请求”契约）

- **MetricLineageBindingRequest（对外/工具参数/服务内部统一）**
  - `metric_name`
  - `lineageVersion?`
  - `scenarioKey?`（可选：把“业务场景”映射到固定版本；用于财务月结等固定口径场景）
  - `tenantId/projectId?`（通常由 RequestContext 解析，不鼓励调用方手动传；但如果传了必须与 ctx 一致）

### 4.2 选择策略（强制顺序，不得自动选择非确定项）

1. **用户显式指定 `lineageVersion`**：必须命中唯一记录。
2. **提供 `scenarioKey`**：必须能解析到唯一版本，再去命中对应记录。
3. **都不提供**：
   - 默认：拒答（`EVIDENCE_MISMATCH`，reason=`lineage_version_required`）。
   - 若产品明确允许“默认 active”：只能在“唯一 active”时返回；否则拒答（reason=`multiple_active_lineage_versions` 或缺失）。

### 4.3 结果产物（必须写入证据链）

- 绑定结果必须产出：
  - `MetricLineageRecord`
  - `MetricLineageBindingDecision`（method=`user_specified|default_active`；若走 scenarioKey，建议 method 仍视为 `user_specified`，但在审计中记录 `resolved_by=scenario_mapping`）
  - **Evidence**：`Evidence.lineageVersion=<bound version>`

### 4.4 绑定失败的拒答/降级

- **缺失口径记录**：`EVIDENCE_MISSING`（英文 message），不得输出计算结果。
- **冲突/不允许策略**：`EVIDENCE_MISMATCH`，不得输出计算结果。
- **可选降级路径（仅当产品要求）**：
  - 输出 warning（code 建议复用 `EVIDENCE_MISSING` / `EVIDENCE_MISMATCH`）
  - 仅展示原始数据与来源 Evidence（不包含计算口径结论）

## 5. Evidence 字段对齐（lineage_version / lineageVersion）

### 5.1 对外字段名

- 对外统一：`Evidence.lineageVersion`（camelCase）。
- 内部/DB：`lineage_version`。

### 5.2 必填策略

- **计算/聚合型指标结论**：Evidence 中 `lineageVersion` 必填。
- **非计算型“原始数据展示”**：允许缺省，但建议在 evidence 中标注 `validation` 与 `confidence`，并以 warning 提示“未发生口径绑定”。

### 5.3 填充时机（门禁点）

- 任何“计算开始前”必须先完成 `bind_metric_lineage_for_computation`（或等价逻辑），并把 Evidence 写入证据链（SSE `evidence.update` 或非流式响应体 evidenceChain）。

## 6. 对外契约（Pydantic Schema First）

> 本任务蓝图不输出实现代码，但要求在实现阶段严格遵循以下契约形态。

### 6.1 REST（若提供口径查询接口）

- `GET /api/v1/semantic/kpis/{kpi_id}/lineage` 已在 docs 存在，但目前文档未展开字段；Task 7 应补齐“返回口径版本集合/默认 active/冲突提示”的契约说明（以 Pydantic 为权威）。

### 6.2 工具参数契约（若计算由工具触发）

- 任意 `compute_metric_*` 工具参数必须包含：
  - `metric_name`
  - `lineageVersion`（或 `scenarioKey`，但最终必须解析到 `lineageVersion`）
  - `timeRange`（用于 Evidence.timeRange 与审计追溯）

### 6.3 SSE / Evidence update（仅对齐，不改变协议版本）

- 若计算链路是流式：在 `tool.result` 或 `evidence.update` 中输出 Evidence（含 `lineageVersion`）。
- 若发生拒答：必须输出结构化 `error`（payload=ErrorResponse）并 `final(status=error)`。

## 7. RBAC 策略（权限点与拒绝行为）

- 最小 capability：`metric_lineage:read`
  - 适用范围：
    - 口径查询
    - 口径绑定（计算前置）
- 拒绝行为：
  - 缺 capability => `FORBIDDEN`（英文 message），并写审计事件（result=failure, errorCode=FORBIDDEN）。

## 8. 审计与可观测（必须有证据链一致性）

### 8.1 审计事件类型

- 本任务至少覆盖：`query`（口径绑定/口径查询）
  - resource 建议：`metric_lineage_binding`

### 8.2 必填字段

- `requestId/tenantId/projectId/userId/role/timestamp`
- actionSummary（脱敏摘要，不含敏感信息）：
  - `metric_name`
  - `requested_lineage_version`
  - `scenario_key`
  - `bound_lineage_version`
  - `method`
  - `resolved_by`（user_specified/scenario_mapping/default_active）
  - `allow_default_active/allow_inactive/allow_deprecated`
  - scopeFilter：`tenantId/projectId/mode/policyVersion`
- result：`success|failure` + `errorCode?`
- `evidence_refs`：必须能引用到 Evidence（成功路径）。

## 9. 错误码映射（口径相关场景）

- **缺口径记录**：`EVIDENCE_MISSING`，`retryable=false`
- **版本缺失但要求必填**：`EVIDENCE_MISMATCH` + details.reason=`lineage_version_required`
- **多 active 冲突**：`EVIDENCE_MISMATCH` + details.reason=`multiple_active_lineage_versions`
- **数据一致性问题（duplicate records）**：`EVIDENCE_MISMATCH` + details.reason=`duplicate_metric_lineage`
- **权限不足**：`FORBIDDEN`
- **缺 tenant/project scope**：`AUTH_ERROR`

> 约束：对外 ErrorResponse 仅包含 5 字段；其余上下文通过日志与审计承载。

## 10. 目录结构（建议的权威落点）

> 结合现状，Task 7 的“权威口径仓库”落点已经存在于 `backend/gangqing_db/metric_lineage.py`。

- `backend/gangqing_db/metric_lineage.py`：口径实体/查询/绑定规则（Pydantic + 强制策略）
- `backend/gangqing_db/evidence.py`：Evidence Pydantic（含 `lineageVersion`）
- `backend/gangqing_db/errors.py`：结构化错误（口径缺失/冲突映射）
- `backend/migrations/versions/0002_*.py`：SemVer 与唯一 active 约束
- `backend/scripts/metric_lineage_smoke_test.py`：真实 Postgres 冒烟
- `backend/tests/test_metric_lineage.py`：单测（真实 Postgres，不 skip）

## 11. 环境变量与失败策略

- 必需：`GANGQING_DATABASE_URL`
  - 缺失：测试/脚本必须失败，错误 message 必须英文，可用 `CONFIG_MISSING` 或按项目统一映射。

## 12. 验收与验证计划（本任务必须提供的证据）

### 12.1 单元测试（pytest）必须覆盖

- 版本格式校验（SemVer）
- 缺失版本拒答（默认）
- scenarioKey 绑定成功
- 多 active 冲突拒答
- 权限不足拒答
- Evidence 字段完整性（含 `lineageVersion` + `timeRange` 合法）
- 审计成功/失败均写入（含 requestId 与 errorCode）

### 12.2 冒烟测试（真实 Postgres）必须覆盖

- migrations upgrade 到 head
- seed 口径记录 + scenario mapping
- 显式版本查询成功
- 缺失 `lineageVersion` 且不允许 default active => 必须失败并返回结构化错误

## 13. 需要你确认的关键决策点（避免后续契约漂移）

1. **是否允许“默认 active”作为计算入口的 fallback？（以实现为准）**
  - 现状：`bind_metric_lineage_for_computation(..., allow_default_active: bool = False)` 默认 **不允许** 缺失 `lineageVersion`。
  - 现状行为：当未提供 `lineageVersion` 且未提供 `scenarioKey`，会返回 `EVIDENCE_MISMATCH`，`details.reason=lineage_version_required`。
2. **scenarioKey 的定位（以实现为准）**
  - 现状：`scenarioKey` 已作为“版本绑定的第二选择路径”落地（`bind_metric_lineage_for_computation`），并有单元测试与冒烟测试覆盖；因此按当前实现视为 **可用且稳定的绑定入口**（至少在后端内部/工具层使用）。
3. **对外 API 形态（以实现为准）**
  - 现状：当前 FastAPI 路由层未暴露 `metric_lineage` 或 `kpi lineage` 的对外查询端点（`backend/gangqing/api/router.py` 未 include semantic 路由；仓库中也不存在 `backend/gangqing/api/v1/semantic.py`）。
  - 结论：Task 7 在当前实现边界内，以“口径仓库 + 绑定门禁 + Evidence/审计对齐 + 测试验收”为主；是否新增对外 API 属于后续任务/扩展范围（不在现状实现中）。
4. **`lineage_version` vs `lineageVersion` 字段命名（以实现为准）**
  - 现状：对外（Pydantic Evidence/口径记录）统一使用 `lineageVersion`；DB 内部字段为 `lineage_version`。
  - 结论：对外契约以 `lineageVersion` 为准；文档中出现 `lineage_version` 的地方需要明确其为内部/DB 表述，避免前后端契约漂移。
