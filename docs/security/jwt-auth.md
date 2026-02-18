# JWT 认证规范（AuthN）

本文件固化 GangQing（钢擎）对外 API 的 JWT 认证最小闭环规范与验收口径，作为后端实现与接口契约的权威依据之一。

## 0. 强制原则
- 令牌仅用于身份认证（AuthN），授权（AuthZ）必须由 RBAC/策略层完成。
- 默认只读：认证通过不代表允许写操作；写操作仍需审批、白名单与 Kill Switch 关闭。
- 错误消息（message）必须为英文，便于日志检索。

## 1. Token 类型
- **Access Token**：短期有效（默认 8 小时，可配置），用于访问 API。
- （可选）**Refresh Token**：本阶段不强制实现；如引入需有独立撤销与审计策略。

## 2. Header 与格式
- Header：`Authorization: Bearer <token>`
- 额外链路字段：建议客户端携带 `X-Request-Id`，服务端在缺失时生成并回写。

## 3. Claims 约定（最小集合）
- `sub`：用户唯一标识（userId）
- `role`：角色（如 `admin/manager/scheduler/maintenance/finance/ot_operator`）
- `iat`：签发时间（Unix timestamp）
- `exp`：过期时间（Unix timestamp）

（可选但推荐）
- `tenantId` / `projectId`：多租户/项目隔离上下文字段（若启用隔离，建议写入并在网关/服务端校验一致性）

## 4. 签名算法
- 推荐：`HS256`（对称密钥）作为 PoC/试点基线。
- 生产建议：逐步迁移到 `RS256/ES256` 并使用 KMS/HSM 托管私钥。

## 5. 认证失败响应（对外）
认证失败必须返回结构化错误模型（示例字段）：
- `code`: `AUTH_ERROR`
- `message`: 英文，如 `Missing Authorization header` / `Invalid token`
- `retryable`: `false`
- `requestId`: 链路追踪 ID

HTTP 状态码建议：
- 缺少/格式错误：`401`
- token 无效/过期：`401`

## 6. 审计要求
- 认证失败（401）必须记录审计事件（建议 actionType: `query`，并标记为 `auth_failed` 结果）。
- 认证成功不强制逐次审计，但对高风险能力（审批/写/策略变更）必须审计。

## 7. 最小验收用例
- 无 `Authorization`：返回 401 + 结构化错误 + `requestId`。
- 非 `Bearer` 格式：返回 401。
- 过期 token：返回 401。
- 合法 token：可访问 `/api/v1/health` 与其他只读接口。
