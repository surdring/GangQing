# 数据接入与数据质量治理 API（Data API）

本文档描述 `backend/gangqing/api/v1/data_quality.py` 提供的数据接入与数据质量治理 REST API（Task 3 PoC）：连接器清单、时序对齐、数据质量报表。

## 通用约定

### 认证与鉴权

- 使用 `Authorization: Bearer <JWT>`
- 租户/项目隔离：必须传递请求头
  - `X-Tenant-Id: <tenant_id>`
  - `X-Project-Id: <project_id>`
- `X-Request-Id`：建议传递，用于审计与排障关联

### 只读默认

- 本组 API 均为只读性质（PoC：不对外部系统执行写操作）。

### 错误模型

对外错误使用结构化 `AppError`（与 `docs/contracts/api-and-events-draft.md` 对齐）：

- `code`：稳定错误码
- `message`：英文错误消息（便于日志检索）
- `details`：结构化上下文（禁止敏感信息）
- `retryable`：是否可重试
- `requestId`：链路追踪 ID

常见错误码：

- `VALIDATION_ERROR`：参数/格式不合法（含请求体 schema 校验失败）
- `AUTH_ERROR`：鉴权失败或缺少 `tenant/project` scope
- `FORBIDDEN`：RBAC 不允许
- `INTERNAL_ERROR`：系统错误

## 时区处理策略

- API 入参时间若包含时区：服务端统一转换为 UTC 参与计算。
- 若为 naive datetime（无时区）：服务端按 UTC 解释。

## `quality_code` 语义与映射（PoC）

- `quality_code`：来源系统对采样点质量的标记。
- PoC 最小映射：
  - `0`/`bad`/`invalid`/`unknown`（忽略大小写与空白）视为坏值
  - 其他值视为好值
- 映射关系：
  - 点级得分：坏值 → `0.0`；好值/缺失（`null`）→ `1.0`
  - 对齐桶级得分：桶内点级得分平均值
  - 报表级得分：坏值比例作为 `data_quality_score` 的惩罚项（由 `quality_code_weight` 控制）

相关配置：

- `GANGQING_DATA_QUALITY_QUALITY_CODE_BAD_VALUES`
- `GANGQING_DATA_QUALITY_QUALITY_CODE_WEIGHT`
- `GANGQING_DATA_QUALITY_REPORT_CACHE_ENABLED`
- `GANGQING_DATA_QUALITY_REPORT_CACHE_TTL_SECONDS`

## 端点

### 1) `GET /api/v1/data/connectors`

用途：返回接入系统清单（PoC：仅配置回显 + 只读边界声明，不发起真实连接）。

请求头（必须）：

- `Authorization`
- `X-Request-Id`
- `X-Tenant-Id`
- `X-Project-Id`

响应 200（示例）：

```json
{
  "connectors": [
    {
      "system": "ERP",
      "mode": "read_only",
      "entities": ["material", "order", "inventory", "cost"],
      "endpoint": {"host": "erp.example", "port": 443}
    }
  ]
}
```

可能错误码：

- `AUTH_ERROR`：缺少 scope 或鉴权失败
- `FORBIDDEN`：无 `data:connectors:read`

### 2) `POST /api/v1/data/timeseries/align`

用途：将点位时序对齐到统一时间窗口（bucket 聚合）。

请求体（示例）：

```json
{
  "points": [
    {"ts": "2026-02-17T00:00:01+00:00", "value": 10.0, "quality_code": "192"}
  ],
  "alignment": {"method": "bucket_avg", "window_seconds": 60}
}
```

参数约束：

- `alignment.window_seconds >= 1`

响应 200（示例）：

```json
{
  "aligned": [
    {
      "bucket_start": "2026-02-17T00:00:00+00:00",
      "value_avg": 10.0,
      "count": 1,
      "data_quality_score": 1.0
    }
  ]
}
```

可能错误码：

- `VALIDATION_ERROR`
  - 请求体 schema 校验失败（HTTP 422）
  - 或对齐参数不合法（HTTP 400）
- `AUTH_ERROR` / `FORBIDDEN`

### 3) `POST /api/v1/data/quality/report`

用途：生成数据质量报表（缺失/异常/漂移/质量码）与综合评分 `data_quality_score`。

请求体（示例）：

```json
{
  "start": "2026-02-17T00:00:00+00:00",
  "end": "2026-02-17T00:04:00+00:00",
  "points": [
    {"ts": "2026-02-17T00:00:00+00:00", "value": 10.0, "quality_code": "192"}
  ],
  "expected_interval_seconds": 60
}
```

参数约束：

- `end > start`
- `expected_interval_seconds >= 1`

评分与算法（PoC）：

- 异常检测方法由 `GANGQING_DATA_QUALITY_ANOMALY_METHOD=zscore|iqr` 控制
  - `zscore` 使用 `GANGQING_DATA_QUALITY_ANOMALY_Z_THRESHOLD`
  - `iqr` 使用 `GANGQING_DATA_QUALITY_ANOMALY_IQR_MULTIPLIER`
- 缓存：服务端可启用 PoC 内存缓存
  - 响应头 `X-Cache: MISS|HIT`
  - 配置：`GANGQING_DATA_QUALITY_REPORT_CACHE_ENABLED`、`GANGQING_DATA_QUALITY_REPORT_CACHE_TTL_SECONDS`

响应 200（示例）：

```json
{
  "time_range": {"start": "2026-02-17T00:00:00+00:00", "end": "2026-02-17T00:04:00+00:00"},
  "total_points": 1,
  "missing_points": 4,
  "missing_ratio": 0.8,
  "anomaly_points": 0,
  "drift_score": 0.0,
  "data_quality_score": 0.52,
  "issues": [
    {"issue_type": "missing", "message": "Missing data points detected", "details": {"expected": 5, "observed": 1}}
  ]
}
```

可能错误码：

- `VALIDATION_ERROR`
- `AUTH_ERROR` / `FORBIDDEN`

## 配置项摘要（T3）

> 详见 `.env.example` 与 `docs/acceptance/T3_data-ingestion-and-quality.md`。

- `GANGQING_DATA_QUALITY_EXPECTED_INTERVAL_SECONDS`
- `GANGQING_DATA_QUALITY_ANOMALY_METHOD`
- `GANGQING_DATA_QUALITY_ANOMALY_Z_THRESHOLD`
- `GANGQING_DATA_QUALITY_ANOMALY_IQR_MULTIPLIER`
- `GANGQING_DATA_QUALITY_DRIFT_MIN_POINTS`
- `GANGQING_DATA_QUALITY_MISSING_WEIGHT`
- `GANGQING_DATA_QUALITY_ANOMALY_WEIGHT`
- `GANGQING_DATA_QUALITY_DRIFT_WEIGHT`
- `GANGQING_DATA_QUALITY_QUALITY_CODE_BAD_VALUES`
- `GANGQING_DATA_QUALITY_QUALITY_CODE_WEIGHT`
- `GANGQING_DATA_TIMESERIES_DEFAULT_WINDOW_SECONDS`
- `GANGQING_CONNECTORS_CHECK_TIMEOUT_SECONDS`
- `GANGQING_CONNECTOR_{ERP|MES|EAM|LIMS|OT}_HOST`
- `GANGQING_CONNECTOR_{ERP|MES|EAM|LIMS|OT}_PORT`
