# 语义层 API（Semantic API）

本文档描述 `backend/gangqing/api/v1/semantic.py` 提供的语义层 REST API：实体（Equipment/Material/Batch）、事件（Events）、指标口径（KPI）以及 KPI 血缘查询。

## 通用约定

### 认证与鉴权
- 使用 `Authorization: Bearer <JWT>`
- 租户/项目隔离：必须传递请求头
  - `X-Tenant-Id: <tenant_id>`
  - `X-Project-Id: <project_id>`

### 分页
- 列表接口使用：
  - `limit`（默认 200）
  - `offset`（默认 0）
- 返回结构：
  - `{"total": <int>, "items": <list>}`

### 错误模型
对外错误使用结构化 `AppError`：
- `code`：稳定错误码
- `message`：英文错误消息（便于日志检索）
- `details`：结构化上下文
- `retryable`：是否可重试
- `requestId`：链路追踪 ID

常见错误码：
- `VALIDATION_ERROR`：参数/格式不合法
- `AUTH_ERROR`：跨租户/跨项目访问或 scope 冲突
- `FORBIDDEN`：RBAC 不允许
- `NOT_FOUND`：资源不存在

## 幂等性与重试策略

### 幂等性
- 语义层的 `upsert` 类写入（equipment/material/batch/kpi）在**同一 tenant/project scope 内**，以业务主键（如 `unified_id`/`unified_batch_id`/`kpi_id`）为幂等键。
- 若同一业务主键在不同 scope 下出现冲突，服务端返回 `AUTH_ERROR`（禁止跨隔离覆盖）。

### 批量写入语义
- `continue_on_error=false`（默认）：单事务批量写入
  - 任一条失败 => 整批失败并回滚
  - 适合客户端希望“全量一致性”的场景
- `continue_on_error=true`：逐条写入
  - 每条独立事务
  - 返回 `results` 数组，客户端应检查失败项并按需重试

### 重试建议
- 当 `retryable=true` 时允许客户端重试（建议指数退避）
  - 建议：初始 200ms，最大 3-5 次，带随机抖动
- 当前语义层常见错误码的推荐策略：
  - `VALIDATION_ERROR`：不可重试（修正请求）
  - `AUTH_ERROR`/`FORBIDDEN`：不可重试（修正权限/租户项目）
  - `NOT_FOUND`：通常不可重试（除非依赖上游异步写入）
  - `INTERNAL_ERROR`：视为可重试候选（需结合 `retryable` 字段判断）

## 端点

### Equipment

#### `POST /api/v1/semantic/equipment`

- 权限（RBAC capability）：`semantic:equipment:write`
- 请求头（必须）：

  - `Authorization: Bearer <JWT>`
  - `X-Request-Id: <request_id>`（建议；未传入服务端会生成）
  - `X-Tenant-Id: <tenant_id>`
  - `X-Project-Id: <project_id>`

- Errors：

  - `AUTH_ERROR`：缺少 `X-Tenant-Id/X-Project-Id` 或 cross-scope 覆盖
  - `FORBIDDEN`：无写权限（缺少 `semantic:equipment:write`）
  - `VALIDATION_ERROR`：请求体 schema 校验失败（HTTP 422）
  - `INTERNAL_ERROR`：未捕获异常

- 示例（成功）：

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-001" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Project-Id: project-a" \
  "http://localhost:8000/api/v1/semantic/equipment" \
  -H "Content-Type: application/json" \
  -d '{"unified_id":"EQ-1","equipment_name":"Caster-1"}'
```

响应（200）：
```json
{"status":"ok"}
```

- 示例（失败：缺少 scope headers）：

响应（403）：
```json
{
  "code": "AUTH_ERROR",
  "message": "Missing tenantId or projectId",
  "details": {"tenantId": null, "projectId": null},
  "retryable": false,
  "requestId": "req-001",
  "tenantId": null,
  "projectId": null
}
```

#### `POST /api/v1/semantic/equipment/batch`

- 权限（RBAC capability）：`semantic:equipment:write`
- 查询参数：

  - `continue_on_error`：`true|false`（默认 `false`）

    - `false`：单事务批量写入（任一条失败 => 整批失败回滚）
    - `true`：逐条写入（每条独立事务），返回逐条 `results`（不会因为单条失败导致整批回滚）

- Errors：

  - `AUTH_ERROR`：缺少 scope headers 或某条记录触发 cross-scope
  - `FORBIDDEN`：无写权限
  - `VALIDATION_ERROR`：请求体 schema 校验失败
  - `INTERNAL_ERROR`：

    - `continue_on_error=false`：通常表现为请求失败（整体失败）
    - `continue_on_error=true`：单条失败时会落在 `results[].error` 中

- 示例（成功：continue_on_error=false，单事务）：

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-002" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Project-Id: project-a" \
  "http://localhost:8000/api/v1/semantic/equipment/batch" \
  -H "Content-Type: application/json" \
  -d '[{"unified_id":"EQ-1","equipment_name":"Caster-1"},{"unified_id":"EQ-2","equipment_name":"Caster-2"}]'
```

响应（200）：
```json
{"status":"ok"}
```

- 示例（部分失败：continue_on_error=true，逐条写入）：

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-003" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Project-Id: project-a" \
  "http://localhost:8000/api/v1/semantic/equipment/batch?continue_on_error=true" \
  -H "Content-Type: application/json" \
  -d '[{"unified_id":"EQ-1","equipment_name":"Caster-1"},{"unified_id":"EQ-cross","equipment_name":"Other"}]'
```

响应（200）：
```json
{
  "status": "ok",
  "results": [
    {"index": 0, "ok": true, "unified_id": "EQ-1"},
    {
      "index": 1,
      "ok": false,
      "unified_id": "EQ-cross",
      "error": {
        "code": "AUTH_ERROR",
        "message": "Cross-scope access denied: ...",
        "details": {"resource": "semantic:equipment", "unified_id": "EQ-cross"},
        "retryable": false,
        "requestId": "req-003",
        "tenantId": "tenant-a",
        "projectId": "project-a"
      }
    }
  ]
}
```

#### `GET /api/v1/semantic/equipment/{unified_id}`

- 权限（RBAC capability）：`semantic:equipment:read`
- 请求头（必须）：同上
- Errors：

  - `AUTH_ERROR`：缺少 scope headers
  - `FORBIDDEN`：无读权限
  - `NOT_FOUND`：当前 tenant/project 下不存在该 `unified_id`

- 示例（成功）：

```bash
curl -X GET \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-004" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Project-Id: project-a" \
  "http://localhost:8000/api/v1/semantic/equipment/EQ-1"
```

- 示例（失败：不存在）：

响应（404）：
```json
{
  "code": "NOT_FOUND",
  "message": "Equipment not found for unified_id",
  "details": {"unified_id": "EQ-404"},
  "retryable": false,
  "requestId": "req-004",
  "tenantId": "tenant-a",
  "projectId": "project-a"
}
```

### Material

#### `POST /api/v1/semantic/materials`

- 权限（RBAC capability）：`semantic:material:write`
- 请求头（必须）：同上
- Errors：

  - `AUTH_ERROR`：缺少 scope headers 或 cross-scope 覆盖
  - `FORBIDDEN`：无写权限
  - `VALIDATION_ERROR`：请求体 schema 校验失败

- 示例（成功）：

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-010" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Project-Id: project-a" \
  "http://localhost:8000/api/v1/semantic/materials" \
  -H "Content-Type: application/json" \
  -d '{"unified_id":"MAT-1","material_name":"Scrap"}'
```

响应（200）：
```json
{"status":"ok"}
```

#### `POST /api/v1/semantic/materials/batch`

- 权限（RBAC capability）：`semantic:material:write`
- 查询参数：`continue_on_error=true|false`（默认 `false`）
- Errors：

  - `AUTH_ERROR` / `FORBIDDEN` / `VALIDATION_ERROR`
  - `INTERNAL_ERROR`：逐条模式下落在 `results[].error`

- 示例（部分失败：continue_on_error=true）：

响应（200）：
```json
{
  "status": "ok",
  "results": [
    {"index": 0, "ok": true, "unified_id": "MAT-1"},
    {
      "index": 1,
      "ok": false,
      "unified_id": "MAT-cross",
      "error": {"code": "AUTH_ERROR", "message": "Cross-scope access denied: ..."}
    }
  ]
}
```

#### `GET /api/v1/semantic/materials/{unified_id}`

- 权限（RBAC capability）：`semantic:material:read`
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `NOT_FOUND`

### Batch

#### `POST /api/v1/semantic/batches`

- 权限（RBAC capability）：`semantic:batch:write`
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `VALIDATION_ERROR`

#### `POST /api/v1/semantic/batches/batch`

- 权限（RBAC capability）：`semantic:batch:write`
- 查询参数：`continue_on_error=true|false`（默认 `false`）
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `VALIDATION_ERROR` / `INTERNAL_ERROR`

#### `GET /api/v1/semantic/batches/{unified_batch_id}`

- 权限（RBAC capability）：`semantic:batch:read`
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `NOT_FOUND`

### Events

#### `POST /api/v1/semantic/events`

- 权限（RBAC capability）：`semantic:event:write`
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `VALIDATION_ERROR`

#### `POST /api/v1/semantic/events/batch`

- 权限（RBAC capability）：`semantic:event:write`
- 查询参数：`continue_on_error=true|false`（默认 `false`）
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `VALIDATION_ERROR` / `INTERNAL_ERROR`

#### `GET /api/v1/semantic/events`

- 权限（RBAC capability）：`semantic:event:read`
- 查询参数：

  - `equipment_id`（可选）
  - `batch_id`（可选）
  - `start_time` / `end_time`（可选，ISO 8601 datetime）
  - `limit` / `offset`

- Errors：

  - `AUTH_ERROR`：缺少 scope headers
  - `FORBIDDEN`：无读权限
  - `VALIDATION_ERROR`：时间范围非法（例如 `end_time <= start_time`）

- 示例（成功）：

```bash
curl -X GET \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-020" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Project-Id: project-a" \
  "http://localhost:8000/api/v1/semantic/events?limit=10&offset=0"
```

响应（200）：
```json
{"total": 0, "items": []}
```

### KPI Definitions

#### `POST /api/v1/semantic/kpis`

- 权限（RBAC capability）：`semantic:kpi:write`
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `VALIDATION_ERROR`

#### `POST /api/v1/semantic/kpis/batch`

- 权限（RBAC capability）：`semantic:kpi:write`
- 查询参数：`continue_on_error=true|false`（默认 `false`）
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `VALIDATION_ERROR` / `INTERNAL_ERROR`

#### `GET /api/v1/semantic/kpis`

- 权限（RBAC capability）：`semantic:kpi:read`
- 查询参数：`limit` / `offset`
- 响应：`{"total": <int>, "items": <list>}`
- Errors：`AUTH_ERROR` / `FORBIDDEN`

#### `GET /api/v1/semantic/kpis/{kpi_id}`

- 权限（RBAC capability）：`semantic:kpi:read`
- Errors：`AUTH_ERROR` / `FORBIDDEN` / `NOT_FOUND`

#### `GET /api/v1/semantic/kpis/{kpi_id}/lineage`

- 权限（RBAC capability）：`semantic:kpi:read`
- 查询参数：`max_depth`（默认 5）
- Errors：

  - `AUTH_ERROR` / `FORBIDDEN`
  - `NOT_FOUND`：KPI 不存在
  - `VALIDATION_ERROR`：`max_depth` 不合法（例如 `< 1`）
