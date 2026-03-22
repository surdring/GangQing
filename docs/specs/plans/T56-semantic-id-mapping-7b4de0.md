# Task 56: 统一语义层（实体与 ID 映射）执行计划

本计划为 GangQing 项目建立跨系统统一 ID 映射体系，涵盖映射表 Schema 与版本化管理、冲突检测与降级机制、跨系统聚合门禁、证据链集成与审计四大子任务，确保跨 ERP/MES/DCS/EAM 的数据聚合具备可追溯性与一致性保障。

## 一、执行蓝图

### 1) Task 56.1 - 映射表 Schema 与版本化管理（基础数据层）

**目标**: 设计并实现统一 ID 映射表的数据库 Schema、Pydantic 模型、以及版本化机制

**关键决策**:
- 映射表结构：支持 Equipment/Material/Batch/Order 四类实体的统一 ID 映射
- 版本化策略：使用 `version` + `valid_from/valid_to` 时间戳实现历史追溯
- 隔离字段：必须包含 `tenant_id` + `project_id` 实现多租户隔离

**具体步骤**:

1. **定义 Pydantic Schema**（`backend/gangqing/semantic/models/entity_mapping.py`）
   - 定义 `EntityType` Enum: `equipment`, `material`, `batch`, `order`
   - 定义 `EntityMappingBase` 模型字段：
     - `unified_id: str` - 统一实体 ID
     - `entity_type: EntityType` - 实体类型
     - `source_system: str` - 来源系统（ERP/MES/DCS）
     - `source_id: str` - 源系统原始 ID
     - `tenant_id: str` / `project_id: str` - 隔离字段
     - `version: int` - 版本号（从 1 递增）
     - `valid_from: datetime` / `valid_to: Optional[datetime]` - 时间戳
     - `created_by: Optional[str]` / `metadata: Optional[Dict[str, Any]]`
   - 定义 `EntityMappingCreate` / `EntityMappingUpdate` / `EntityMappingResponse` / `MappingVersionHistory`

2. **实现数据库迁移**（`backend/migrations/versions/xxx_add_entity_mapping_tables.py`）
   - 创建 `entity_mappings` 表
   - 复合唯一索引: `(unified_id, entity_type, version, tenant_id, project_id)`
   - 查询优化索引:
     - `(tenant_id, project_id, entity_type, unified_id)` - 按实体查询
     - `(source_system, source_id)` - 反向查询
     - `(valid_from, valid_to)` + `valid_to IS NULL` 部分索引

3. **实现版本化管理模块**（`backend/gangqing/semantic/mapping_versioning.py`）
   - `MappingVersionManager` 类:
     - `create_mapping(mapping) -> EntityMappingResponse`: 创建新映射（version=1）
     - `update_mapping(unified_id, entity_type, update) -> EntityMappingResponse`: 更新映射（旧版本标记失效，创建新版本）
     - `get_current_mapping(unified_id, entity_type) -> Optional[EntityMappingResponse]`: 获取当前有效版本
     - `get_mapping_history(unified_id, entity_type) -> List[MappingVersionHistory]`: 获取版本历史
     - `soft_delete_mapping(unified_id, entity_type) -> bool`: 软删除
   - 版本冲突检测: `check_version_conflict(tenant_id, project_id, unified_id, entity_type, expected_version)`

4. **集成 RBAC 与审计**
   - 权限检查: 读操作需 `semantic:mapping:read`，写操作需 `semantic:mapping:write`
   - 审计事件: `mapping.query`, `mapping.create`, `mapping.update`, `mapping.delete`
   - 审计字段: `requestId`, `tenant_id`, `project_id`, `user_id`, `version`

---

### 2) Task 56.2 - 冲突检测与拒答/降级机制（核心逻辑层）

**目标**: 实现映射冲突检测逻辑，定义 `EVIDENCE_MISMATCH` 错误语义与降级策略

**依赖**: 依赖 Task 56.1 的 Schema 定义

**关键决策**:
- 冲突类型：统一 ID 多对一冲突、跨系统 ID 冲突、映射缺失、版本不匹配
- 错误映射：所有冲突统一映射到 `EVIDENCE_MISMATCH` 错误码
- 降级策略：冲突时降级为"仅展示可用数据与来源"，不可编造聚合结果

**具体步骤**:

1. **定义冲突检测 Schema**（`backend/gangqing/semantic/models/conflict_detection.py`）
   - `ConflictType` Enum:
     - `MULTI_TO_ONE`: 同一 unified_id 映射到多个 source_id
     - `CROSS_SYSTEM`: 跨系统 ID 冲突
     - `MAPPING_MISSING`: 映射缺失
     - `VERSION_MISMATCH`: 版本不匹配
   - `ConflictDetectionResult` 模型:
     - `unified_id`, `entity_type`, `conflict_type`, `conflict_details: Dict[str, Any]`
     - `severity: Literal["critical", "warning", "info"]`, `detected_at: datetime`
   - `ConflictResolutionStrategy` Enum: `REJECT`, `DEGRADE`, `OVERRIDE`

2. **实现冲突检测模块**（`backend/gangqing/semantic/conflict_detector.py`）
   - `ConflictDetector` 类:
     - `detect_by_unified_id(unified_id, entity_type) -> List[ConflictDetectionResult]`: 按统一 ID 检测
     - `detect_by_source_id(source_system, source_id) -> List[ConflictDetectionResult]`: 反向检测
     - `detect_multi_to_one(tenant_id, project_id) -> List[ConflictDetectionResult]`: 扫描多对一冲突
     - `validate_mapping_consistency(mappings) -> Optional[ConflictDetectionResult]`: 验证一致性
   - 检测逻辑：
     - 查询同一 unified_id 下的所有 source_id
     - 如果数量 > 1 且 source_system 不同 → 标记 `MULTI_TO_ONE`
     - 如果映射不存在 → 标记 `MAPPING_MISSING`

3. **实现错误映射与降级策略**
   - `mapping_errors.py`: `map_conflict_to_error(conflict) -> ErrorResponse`
     - 映射为 `EVIDENCE_MISMATCH`
     - 英文 message: "Mapping conflict detected: {conflict_type} for {entity_type} {unified_id}"
   - `mapping_fallback.py`: `create_degraded_response(conflict) -> DegradedResult`
     - 降级结果包含：可用数据源列表、冲突说明、人工审核建议
     - 不返回聚合数值，仅返回原始数据与来源

4. **集成到 API 层**
   - 在查询端点添加冲突检测调用
   - `critical` 级别冲突 → 返回 `EVIDENCE_MISMATCH`
   - `warning` 级别冲突 → 返回降级结果 + warning 事件

---

### 3) Task 56.3 - 跨系统聚合门禁（API 集成层）

**目标**: 在跨系统聚合查询入口处实现基于统一 ID 的强制门禁检查

**依赖**: 依赖 Task 56.1 的映射表和 Task 56.2 的冲突检测

**关键决策**:
- 门禁位置：Semantic API 层、工具调用层、编排引擎数据获取层
- 检查逻辑：聚合前必须验证所有源数据的统一 ID 映射一致性
- 失败处理：映射缺失/冲突时立即返回错误，不进入下游计算

**具体步骤**:

1. **实现聚合门禁核心逻辑**（`backend/gangqing/semantic/aggregation_gate.py`）
   - `AggregationGate` 类:
     - `check_aggregation_prerequisites(entity_refs: List[EntityRef]) -> AggregationGateResult`
     - `EntityRef` 包含: `unified_id`, `entity_type`, `required_source_systems`
   - 检查逻辑:
     1. 遍历所有 entity_refs
     2. 查询每个 unified_id 的当前映射
     3. 映射缺失 → 返回 `AGGREGATION_BLOCKED`
     4. 映射冲突 → 返回 `AGGREGATION_BLOCKED`
     5. 检查通过 → 返回 `ALLOWED`

2. **实现 API 层门禁中间件**（`backend/gangqing/api/middleware/mapping_gate.py`）
   - 创建 FastAPI 依赖函数 `require_valid_mapping(entity_type, unified_id)`
   - 在 Semantic API 聚合查询端点应用
   - 拦截时返回结构化错误:
     ```json
     {
       "code": "AGGREGATION_BLOCKED",
       "message": "Aggregation blocked due to mapping inconsistency",
       "details": {"entity_refs": [...], "conflicts": [...]},
       "retryable": false,
       "requestId": "..."
     }
     ```

3. **实现工具调用门禁装饰器**（`backend/gangqing/tools/decorators/mapping_guard.py`）
   - 装饰器 `@require_mapping_consistency(entity_refs_extractor)`
   - 装饰器自动：
     1. 从工具参数中提取 entity_refs
     2. 调用 `AggregationGate.check_aggregation_prerequisites`
     3. 失败时抛出 `AggregationBlockedError`
   - 应用到 Postgres 查询工具等需要聚合的工具

---

### 4) Task 56.4 - 证据链集成与审计（可观测层）

**目标**: 将映射版本信息、冲突检测结果写入 Evidence 与审计日志

**依赖**: 依赖 Task 56.1-56.3 的实现

**关键决策**:
- Evidence 字段：`mapping_version`, `source_systems`, `conflict_status`
- 审计内容：映射查询、冲突检测、门禁拦截事件
- 贯穿字段：`requestId` 在映射全链路贯穿

**具体步骤**:

1. **扩展 Evidence 数据结构**（`backend/gangqing/semantic/mapping_evidence.py`）
   - `MappingEvidence` Pydantic 模型:
     ```python
     class MappingEvidence(BaseModel):
         evidence_id: str
         unified_id: str
         entity_type: Literal["equipment", "material", "batch", "order"]
         mapping_version: int
         source_systems: List[str]
         conflict_status: Literal["clean", "conflict", "missing"]
         valid_from: datetime
         valid_to: Optional[datetime]
         gate_passed: bool
         gate_block_reason: Optional[str]
     ```
   - `MappingEvidenceBuilder` 类用于构建 Evidence

2. **集成到 Evidence 引擎**
   - 在映射查询、冲突检测、门禁检查处调用 `MappingEvidenceBuilder`
   - 将 `MappingEvidence` 传递到 Evidence 引擎
   - 确保输出到 SSE `evidence.update` 事件

3. **定义审计事件**（`backend/gangqing_db/audit_mapping.py`）
   - 审计事件模型 `AuditMappingEvent`
   - 事件类型：
     - `mapping.query`: 映射查询（unified_id, entity_type, version, result_count）
     - `mapping.conflict_detected`: 冲突检测（conflict_type, unified_id, details）
     - `mapping.aggregation_blocked`: 门禁拦截（reason, entity_refs）
     - `mapping.version_created/updated/deleted`: 版本变更
   - 所有事件包含: `requestId`, `tenant_id`, `project_id`, `user_id`, `timestamp`

4. **集成到审计日志系统**
   - 在 `audit_log.py` 中添加映射事件类型
   - 实现 `AuditMappingLogger` 类
   - 在映射模块中注入审计日志记录

---

## 二、交付物定义

### 目录结构

```
backend/
├── gangqing/
│   └── semantic/
│       ├── __init__.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── entity_mapping.py          # Pydantic Schema (56.1)
│       │   └── conflict_detection.py      # 冲突检测 Schema (56.2)
│       ├── mapping_versioning.py          # 版本化管理 (56.1)
│       ├── conflict_detector.py           # 冲突检测 (56.2)
│       ├── mapping_errors.py              # 错误映射 (56.2)
│       ├── mapping_fallback.py            # 降级策略 (56.2)
│       ├── aggregation_gate.py            # 聚合门禁 (56.3)
│       └── mapping_evidence.py            # 证据链集成 (56.4)
│   ├── api/
│   │   └── middleware/
│   │       └── mapping_gate.py            # API 层门禁 (56.3)
│   └── tools/
│       └── decorators/
│           └── mapping_guard.py           # 工具门禁 (56.3)
└── gangqing_db/
    └── audit_mapping.py                   # 审计事件 (56.4)
└── migrations/versions/
    └── xxx_add_entity_mapping_tables.py   # 数据库迁移 (56.1)
```

### 环境变量

通过统一配置加载（参考 `backend/gangqing/config.py`）:

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENTITY_MAPPING_VERSION_RETENTION_DAYS` | 365 | 映射版本保留天数 |
| `MAPPING_CONFLICT_AUTO_RESOLVE` | false | 是否启用自动冲突解决 |
| `ENTITY_MAPPING_CACHE_TTL_SECONDS` | 300 | 映射查询缓存 TTL |

### API 契约

与 `docs/api/semantic-api.md` 对齐，新增端点：

| 方法 | 端点 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/v1/semantic/mappings/{entity_type}/conflicts` | `semantic:mapping:conflict:read` | 查询映射冲突 |
| GET | `/api/v1/semantic/mappings/{entity_type}/{unified_id}/history` | `semantic:mapping:read` | 查询映射历史 |

### Evidence 契约

证据链数据结构扩展（MappingEvidence）：

```python
class MappingEvidence(BaseModel):
    evidence_id: str
    unified_id: str
    entity_type: Literal["equipment", "material", "batch", "order"]
    mapping_version: int
    source_systems: List[str]
    conflict_status: Literal["clean", "conflict", "missing"]
    valid_from: datetime
    valid_to: Optional[datetime]
    gate_passed: bool
    gate_block_reason: Optional[str]
```

### Auth & RBAC

| 权限 | 能力 | 适用操作 |
|------|------|----------|
| `semantic:mapping:read` | 读取映射 | 查询映射、查询历史 |
| `semantic:mapping:write` | 写入映射 | 创建、更新、删除映射 |
| `semantic:mapping:conflict:read` | 查看冲突 | 查询冲突列表 |

### Error Model

错误码补充：

| 错误码 | 场景 | HTTP Status |
|--------|------|-------------|
| `EVIDENCE_MISMATCH` | 映射冲突或不匹配 | 409 |
| `MAPPING_VERSION_CONFLICT` | 版本冲突 | 409 |
| `AGGREGATION_BLOCKED` | 聚合被门禁拦截 | 403 |

### Observability

- `requestId` 贯穿映射查询全链路
- 审计事件类型：
  - `mapping.query`
  - `mapping.conflict_detected`
  - `mapping.aggregation_blocked`
  - `mapping.version_created/updated/deleted`

---

## 三、整体验收计划

### 自动化断言（冒烟测试）

启动真实 FastAPI 服务 + 真实 Postgres 实例：

**场景 1**: 正常映射查询链路
- 创建设备映射 → 查询映射 → 验证返回包含 `mapping_version`
- 断言：Evidence 包含映射版本字段

**场景 2**: 冲突检测链路
- 创建冲突映射（同一 unified_id 映射到多个源 ID）
- 查询触发 `EVIDENCE_MISMATCH` 错误
- 断言：错误包含 `code`, 英文 `message`, `requestId`, `retryable=false`

**场景 3**: 跨系统聚合门禁
- 尝试聚合存在映射冲突的数据
- 断言：门禁拦截，返回 `AGGREGATION_BLOCKED` 错误

**场景 4**: 版本化历史追溯
- 更新映射 → 查询历史版本 → 验证版本链完整
- 断言：历史记录包含 `valid_from/valid_to` 时间戳

**场景 5**: 多租户隔离
- 跨 tenant/project 访问映射数据
- 断言：返回 `AUTH_ERROR`，记录审计日志

### 测试命令

```bash
# 单元测试
cd backend && python -m pytest gangqing/semantic/tests/ -q

# 冒烟测试
python backend/scripts/semantic_id_mapping_smoke_test.py

# 迁移验证
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

### 验收检查清单

- [ ] 数据库表创建成功，索引生效
- [ ] Pydantic Schema 校验通过（边界值测试）
- [ ] 版本化管理：创建 → 更新 → 查询历史流程完整
- [ ] 冲突检测覆盖所有定义类型
- [ ] `EVIDENCE_MISMATCH` 错误包含英文 message、requestId、retryable=false
- [ ] 降级结果不包含编造数据，仅展示来源
- [ ] 门禁在 API 层、工具层、编排层均有实现
- [ ] `AGGREGATION_BLOCKED` 错误包含英文 message、requestId
- [ ] Evidence 输出包含 `mapping_version`, `source_systems`, `conflict_status`
- [ ] 审计日志覆盖所有映射相关事件
- [ ] `requestId` 在映射全链路贯穿
- [ ] SSE `evidence.update` 事件包含映射相关信息
- [ ] 单元测试覆盖率 >= 80%
- [ ] 冒烟测试所有断言通过

---

## 四、关键决策记录

### 决策 1：版本化策略选择
- **选项 A**: 单表 + version 字段 + valid_from/valid_to
- **选项 B**: 主表 + 历史表分离
- **决策**: 选择选项 A，理由：
  - 查询当前版本简单（valid_to IS NULL）
  - 历史查询无需 JOIN
  - 与现有审计日志模式一致

### 决策 2：冲突处理策略
- **选项 A**: 自动冲突解决（优先级规则）
- **选项 B**: 强制人工介入
- **决策**: 默认选项 B，配置化支持选项 A
  - 默认关闭自动解决（安全优先）
  - 关键业务冲突必须人工审核
  - 非关键冲突可配置自动降级

### 决策 3：门禁实现层级
- **选项 A**: 仅在 API 层实现
- **选项 B**: 多层覆盖（API + 工具 + 编排）
- **决策**: 选择选项 B
  - API 层：防御性校验
  - 工具层：最后防线
  - 编排层：策略控制点

---

## 五、依赖关系与执行顺序

```
56.1 映射表 Schema 与版本化管理
    │
    ▼
56.2 冲突检测与拒答/降级机制
    │
    ▼
56.3 跨系统聚合门禁
    │
    ▼
56.4 证据链集成与审计
```

**关键依赖**:
- 56.2 依赖 56.1 的 Schema 定义
- 56.3 依赖 56.1 的映射表和 56.2 的冲突检测
- 56.4 依赖 56.1-56.3 的实现

**并行可能性**:
- 56.1 的数据库迁移与 Pydantic Schema 可并行设计
- 56.4 的审计事件定义可与 56.1 并行启动

---

## 六、风险与缓解策略

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| 历史映射数据迁移复杂 | 高 | 提供批量导入脚本；版本号从 1 开始，历史记录标记为初始版本 |
| 冲突检测性能开销 | 中 | 增加缓存层；批量检测而非逐条检测；异步扫描 |
| 多租户隔离配置错误 | 高 | 强制校验 tenant_id/project_id；缺失时快速失败 |
| 下游系统依赖未就绪 | 中 | 提供 Mock 映射数据；允许手动维护映射表 |
