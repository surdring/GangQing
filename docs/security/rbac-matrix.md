# RBAC 权限矩阵（含 tenantId/projectId 隔离与脱敏）
本文件定义 GangQing（钢擎）在 L1-L4 的权限模型最小集合，用于验收“RBAC & Masking”“只读默认”“多租户隔离”“审计可复核”等强制约束。本文仅定义能力点与矩阵，不包含任何实现。

## 0. 强制原则
- **最小权限原则**：写权限独立于读权限。
- **多租户隔离**：`tenantId/projectId` 从 L1 起强制启用，所有资源访问默认过滤。
- **审计强制**：所有授权失败、脱敏动作、以及高风险能力使用必须写审计。
- **脱敏优先**：当业务允许时优先脱敏展示；当不允许时必须拒绝并审计。

## 1. 角色（Roles）
- `manager`：厂长/高管
- `scheduler`：生产调度
- `maintenance`：设备维修
- `finance`：财务
- `admin`：系统管理员（安全/运维）
- `ot_operator`：OT 侧确认/执行人员（L4 OT 二次确认角色）

> 注：实际组织结构可在试点中裁剪/合并，但能力点与审计口径需保持稳定。

## 2. 能力点（Permissions）命名规范
- 资源域:动作:范围
  - 示例：`audit:read:any`、`kpi:read:cost`、`execution:execute:ot`

### 2.1 通用能力
- `session:read:self`
- `session:write:self`（仅会话元数据，不涉及业务写入）
- `evidence:read:self`
- `audit:read:self`

### 2.2 经营/财务域
- `kpi:read:cost`
- `kpi:read:profit`
- `finance:read:raw_records`（高敏，原则上仅 finance/admin）

### 2.3 生产/工艺域
- `process:read:params`（高敏，需脱敏策略）
- `dcs:read:realtime`
- `dcs:read:history`

### 2.4 维修域
- `eam:read:asset`
- `eam:read:maintenance_history`
- `sparepart:read:inventory`

### 2.5 审计与安全域
- `audit:read:any`
- `audit:export:any`
- `kill_switch:toggle`
- `policy:read`
- `policy:write`（策略变更也属于写操作，必须审批/审计）

### 2.6 写操作闭环（L4）
- `draft:create:it`
- `draft:create:ot`
- `approval:submit:it`
- `approval:approve:it`
- `approval:submit:ot`
- `approval:approve:ot`
- `execution:execute:it`
- `execution:execute:ot`
- `execution:rollback:it`
- `execution:rollback:ot`

## 3. 脱敏等级（Masking Levels）
- `none`：不脱敏
- `partial`：部分脱敏（区间化、取整、阈值化、打码等）
- `strict`：严格脱敏（仅展示趋势/相对变化，不展示绝对值）
- `deny`：拒绝访问

## 4. 权限矩阵（示例基线）

### 4.1 读取类（L1 起必须可验收）

| capability | manager | scheduler | maintenance | finance | admin | ot_operator | masking_rule | audit_required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| evidence:read:self | allow | allow | allow | allow | allow | allow | none | yes |
| audit:read:self | allow | allow | allow | allow | allow | allow | none | yes |
| audit:read:any | deny | deny | deny | deny | allow | deny | deny | yes |
| kpi:read:cost | allow(partial) | allow(partial) | deny | allow(none) | allow(none) | deny | role_based | yes |
| kpi:read:profit | allow(partial) | deny | deny | allow(none) | allow(none) | deny | role_based | yes |
| finance:read:raw_records | deny | deny | deny | allow(none) | allow(none) | deny | deny_if_not_finance | yes |
| dcs:read:realtime | allow(strict) | allow(partial) | allow(partial) | deny | allow(none) | allow(partial) | role_based | yes |
| process:read:params | deny | allow(partial) | allow(partial) | deny | allow(none) | allow(partial) | high_sensitivity | yes |
| eam:read:maintenance_history | allow(partial) | allow(partial) | allow(none) | deny | allow(none) | allow(partial) | role_based | yes |

说明：
- `allow(partial/strict)` 表示“允许访问但必须脱敏”。
- 对高敏字段（成本明细/工艺参数/配方等）优先通过脱敏满足业务需要；无法脱敏则拒绝。

### 4.2 写操作类（仅 L4，必须经过审批/多签/熔断/白名单）

| capability | manager | scheduler | maintenance | finance | admin | ot_operator | additional_gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| draft:create:it | deny | allow | allow | allow | allow | deny | approval_required |
| approval:approve:it | deny | allow | allow | allow | allow | deny | multisig_optional |
| execution:execute:it | deny | deny | deny | deny | allow | deny | kill_switch + whitelist |
| draft:create:ot | deny | allow | deny | deny | allow | deny | approval_required |
| approval:approve:ot | deny | allow | deny | deny | allow | allow | multisig_required |
| execution:execute:ot | deny | deny | deny | deny | allow | allow | kill_switch + whitelist + ot_confirm |
| execution:rollback:ot | deny | deny | deny | deny | allow | allow | kill_switch + ot_confirm |

## 5. tenantId/projectId 隔离规则（验收口径）
- 所有资源访问必须携带或可推导 `tenantId/projectId`。
- 默认按 `tenantId/projectId` 过滤。
- 发现跨隔离访问：
  - 返回结构化错误（英文 message，建议 `AUTH_ERROR`）
  - 记录审计事件（包含 requestId、tenantId/projectId、目标资源摘要）

## 6. 验收用例最小集合（建议）
- 同一查询在 3 个角色下分别验证：放行/脱敏/拒绝，并检查审计记录。
- 跨 tenant/project 访问尝试：必须拒绝并审计。
- L4 写能力在熔断开启时：全部降级并审计。
