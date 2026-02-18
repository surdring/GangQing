# Task 3 验收交付物：数据接入与数据质量治理（IT/OT 全域数据）

## 1. 范围边界

### 1.1 本任务做什么

- ERP/MES/EAM/LIMS 以“只读查询接口清单 + 字段字典/口径对齐”为交付目标（不实现真实对接）。
- OT 时序数据：提供采集链路设计与 PoC 说明（OPC UA/Modbus），并在后端提供“时序对齐 + 质量评估”的可运行最小闭环。
- 数据质量评估：对缺失、异常、漂移给出结构化报表与 `data_quality_score`（0-1）。
- 数据对齐策略：以“时间窗口对齐（bucket 聚合）”为 PoC 落地点，兼容未来的“事件锚点对齐”。

### 1.2 本任务不做什么

- 不连接真实 ERP/MES/EAM/LIMS/OPC UA/Modbus 服务（真实工具对接属于后续工具链任务）。
- 不落地 TDengine/Flink 等生产级数据管道，仅提供接口与计算口径的可运行 PoC。

## 2. 后端可运行能力（PoC）

### 2.1 API 端点

- `GET /api/v1/data/connectors`
  - 返回：接入系统清单（ERP/MES/EAM/LIMS/OT）及只读能力边界。
- `POST /api/v1/data/timeseries/align`
  - 入参：`points[]`（`ts/value/quality_code?`）+ `alignment.window_seconds`。
  - 返回：`aligned[]`（`bucket_start/value_avg/count/data_quality_score`）。
- `POST /api/v1/data/quality/report`
  - 入参：`timeRange(start/end)` + `points[]` + `expected_interval_seconds`。
  - 返回：缺失/异常/漂移指标与 `data_quality_score`。

### 2.2 质量评分口径（当前 PoC 实现）

- **缺失（missing）**：按 `expected_interval_seconds` 估算应有点数，缺失比例记为 `missing_ratio`。
- **异常（anomaly）**：对点值做 z-score（默认阈值 3.0），统计异常点数量。
- **漂移（drift）**：将序列一分为二，比较两段均值相对变化量，截断到 `[0, 1]`。
- **综合评分（data_quality_score）**：
  - 初始 1.0
  - 缺失惩罚权重 0.6
  - 异常惩罚权重 0.3
  - 漂移惩罚权重 0.1
  - 最终 clamp 到 `[0, 1]`

## 3. 数据接入清单（只读）与字段字典（最小集合）

> 说明：以下为“统一语义层/工具链”对接所需的字段约定（以契约为准），真实数据源字段映射在后续任务逐步补齐。

### 3.1 ERP（SAP/ERP 类）

- **查询域**：物料、订单、库存、成本
- **最小字段建议**
  - 物料：`material_code/material_name/unit/specifications`
  - 订单：`order_no/customer/product/material_code/plan_qty/due_date`
  - 库存：`material_code/location/qty/snapshot_time`
  - 成本：`cost_type/cost_value/currency/time_range/lineage_version`

### 3.2 MES

- **查询域**：炉次/批次、排产、产量、工序状态
- **最小字段建议**
  - 批次：`unified_batch_id/mes_batch_no/batch_type/start_time/end_time/equipment_id`
  - 排产：`schedule_id/equipment_id/window_start/window_end/status`
  - 产量：`batch_id/output_weight_tons/grade/quality_code`

### 3.3 EAM

- **查询域**：设备档案、维修历史、备件库存
- **最小字段建议**
  - 设备：`unified_id/eam_asset_id/equipment_name/equipment_type/location`
  - 维修历史：`work_order_id/equipment_id/start_time/end_time/failure_mode/actions`
  - 备件：`part_no/part_name/warehouse/qty`

### 3.4 LIMS

- **查询域**：样品、化验结果
- **最小字段建议**
  - 样品：`sample_id/sample_type/batch_id/collected_time`
  - 化验：`sample_id/analyte/value/unit/method/qa_flag`

### 3.5 OT（OPC UA/Modbus）

- **查询域**：点位时序（温度/压力/流量等）
- **最小字段建议**
  - 点位：`equipment_id/tag_name/tag_type/unit`
  - 采样点：`ts/value/quality_code`

## 4. OT 时序采集链路设计与 PoC 说明

### 4.1 参考链路（只读）

- **现场侧**：OPC UA Server / Modbus TCP 设备
- **采集侧**：采集网关（边缘计算）
  - 做协议适配（OPC UA/Modbus）
  - 做基础缓存与断点续传
- **安全隔离**：网闸/数据二极管（OT→IT 单向）
- **IT 侧**：入湖/入库（TDengine/数据湖）
- **查询侧**：后端工具层只读查询 + 质量码处理 + Evidence 输出

### 4.2 质量码（quality_code）处理建议

- 原始质量码应保留进入证据链与质量评分。
- 质量码与评分的映射（示例）：
  - `bad/invalid/0/unknown` → 0.0
  - 其他值 → 1.0

## 5. 数据对齐策略

### 5.1 时间窗口对齐（当前 PoC 已实现）

- 以 `window_seconds` 为桶，对同桶内点做 `avg`。
- 桶级 `data_quality_score` 使用桶内点的质量码评分平均值。

### 5.2 事件锚点对齐（后续扩展）

- 以 `production_events`（例如出铁/浇次/停机等）作为锚点。
- 对齐窗口：`[event_time - pre, event_time + post]`，并在 Evidence 中记录规则。

## 6. 证据链（Evidence）与数据质量字段

- Evidence 至少包含：`sourceLocator/timeRange/lineageVersion/dataQualityScore/validation`（按 `docs/contracts/api-and-events-draft.md`）。
- 本任务确保后端 schema 已支持 `dataQualityScore` 等字段（对话接口的 Evidence 模型已扩展）。

## 7. 自动化验证与取证材料

- 自动化验证（必须执行）
  - `python -m compileall backend`
  - `pytest -q`

- 取证材料（验收日志中必须记录）
  - 以上命令输出与结论
  - `/api/v1/data/*` 冒烟测试覆盖：成功路径 + 失败路径（缺少 scope）

## 8. 配置项（外部化与文档化，验收必需）

> 配置来源：环境变量（`.env.local`）+ `backend/gangqing/config/settings.py` 校验。

### 8.1 数据质量评分（Data Quality）

- `GANGQING_DATA_QUALITY_EXPECTED_INTERVAL_SECONDS`
  - 用途：估算应有点数，用于缺失比例 `missing_ratio`
  - 默认值：`60`
- `GANGQING_DATA_QUALITY_ANOMALY_METHOD`
  - 用途：异常检测方法（`zscore`/`iqr`）
  - 默认值：`zscore`
- `GANGQING_DATA_QUALITY_ANOMALY_Z_THRESHOLD`
  - 用途：异常检测 z-score 阈值
  - 默认值：`3.0`
- `GANGQING_DATA_QUALITY_ANOMALY_IQR_MULTIPLIER`
  - 用途：异常检测 IQR 倍数（当 `ANOMALY_METHOD=iqr` 时生效）
  - 默认值：`1.5`
- `GANGQING_DATA_QUALITY_DRIFT_MIN_POINTS`
  - 用途：启动漂移检测所需的最小点数
  - 默认值：`10`
- `GANGQING_DATA_QUALITY_MISSING_WEIGHT / GANGQING_DATA_QUALITY_ANOMALY_WEIGHT / GANGQING_DATA_QUALITY_DRIFT_WEIGHT`
  - 用途：缺失/异常/漂移惩罚权重（范围 `[0,1]`）
  - 默认值：`0.6/0.3/0.1`
- `GANGQING_DATA_QUALITY_QUALITY_CODE_BAD_VALUES`
  - 用途：质量码坏值集合（逗号分隔、小写比较）
  - 默认值：`0,bad,invalid,unknown`
- `GANGQING_DATA_QUALITY_QUALITY_CODE_WEIGHT`
  - 用途：质量码惩罚权重（范围 `[0,1]`）
  - 默认值：`0.2`

- `GANGQING_DATA_QUALITY_REPORT_CACHE_ENABLED`
  - 用途：是否启用质量报表缓存（PoC 内存缓存）
  - 默认值：`true`
- `GANGQING_DATA_QUALITY_REPORT_CACHE_TTL_SECONDS`
  - 用途：质量报表缓存 TTL（秒）；设置为 `0` 表示不缓存
  - 默认值：`300`

### 8.2 时序对齐（Alignment）

- `GANGQING_DATA_TIMESERIES_DEFAULT_WINDOW_SECONDS`
  - 用途：对齐窗口默认值（当前 PoC 主要用于文档与前端默认值建议）
  - 默认值：`60`

### 8.3 连接器配置（PoC 预留）

- `GANGQING_CONNECTORS_CHECK_TIMEOUT_SECONDS`
  - 用途：连接器健康检查超时（PoC 预留）
  - 默认值：`0.5`
- `GANGQING_CONNECTOR_{ERP|MES|EAM|LIMS|OT}_HOST / GANGQING_CONNECTOR_{...}_PORT`
  - 用途：外部系统连接信息（PoC 仅回显，不发起真实连接）
  - 默认值：空

### 8.4 时区处理策略

- API 入参时间若包含时区：服务端统一转换为 UTC 参与计算。
- 若为 naive datetime（无时区）：服务端按 UTC 解释。

