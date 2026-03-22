### Task 56 - （L1+）统一语义层（实体与 ID 映射）：设备/物料/批次/订单统一 ID 映射与冲突治理（Umbrella）

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行第 56 号任务：统一语义层（实体与 ID 映射）。
角色：**技术负责人/架构师**。
目标是制定统一 ID 映射表、冲突检测与版本化、跨系统聚合前置条件、以及映射缺失/冲突的错误码与证据链语义的详细执行计划。

# Critical Rules (核心约束)
- **NO CODE IMPLEMENTATION**: 在此阶段**禁止**输出任何具体的函数实现或业务代码。
- **PLANNING ONLY**: 你的输出应该聚焦于"怎么做"、"分几步"、"文件结构如何"、"接口长什么样"。
- **Isolation（强制）**: 映射必须按 tenant/project 隔离；跨隔离访问返回 `AUTH_ERROR`。
- **Evidence-First（强制）**: 映射结果与版本信息必须可追溯并进入 Evidence（摘要）。
- **结构化错误（强制）**: 映射缺失/冲突返回 `EVIDENCE_MISMATCH`（或按 contracts），英文 message。
- **真实集成测试（No Skip）**。
- **Schema First**:
  - 后端：对外 I/O、工具参数、Evidence、审计事件使用 Pydantic 校验。
- **Read-Only Default**: 默认只读；写操作仅生成草案与审批材料。

# References
- PRD: docs/requirements.md（R16.1 实体与 ID 映射）
- TDD: docs/design.md（5.3 实体与 ID 映射）
- tasks: docs/tasks.md（任务 56）
- contracts: docs/contracts/api-and-events-draft.md（2.3 Semantic API）
- api docs: docs/api/semantic-api.md

# Execution Plan (执行蓝图)

## 1) Task 56.1 - 映射表 Schema 与版本化管理（基础数据层）
- **Goal**: 设计并实现统一 ID 映射表的数据库 Schema、Pydantic 模型、以及版本化机制
- **Key Decisions**:
  - 映射表结构：支持 Equipment/Material/Batch/Order 四类实体的统一 ID 映射
  - 版本化策略：使用 `version` + `valid_from/valid_to` 时间戳实现历史追溯
  - 隔离字段：必须包含 `tenant_id` + `project_id` 实现多租户隔离
- **Deliverables**:
  - 数据库迁移脚本（Alembic）：`migrations/versions/xxx_add_entity_mapping_tables.py`
  - Pydantic Schema 模型：`backend/gangqing/semantic/models/entity_mapping.py`
  - 版本化管理模块：`backend/gangqing/semantic/mapping_versioning.py`

## 2) Task 56.2 - 冲突检测与拒答/降级机制（核心逻辑层）
- **Goal**: 实现映射冲突检测逻辑，定义 `EVIDENCE_MISMATCH` 错误语义与降级策略
- **Dependencies**: 依赖 Task 56.1 的 Schema 定义
- **Key Decisions**:
  - 冲突类型：统一 ID 多对一冲突、跨系统 ID 冲突、映射缺失
  - 错误映射：所有冲突统一映射到 `EVIDENCE_MISMATCH` 错误码
  - 降级策略：冲突时降级为"仅展示可用数据与来源"，不可编造聚合结果
- **Deliverables**:
  - 冲突检测模块：`backend/gangqing/semantic/conflict_detector.py`
  - 错误映射工具：`backend/gangqing/semantic/mapping_errors.py`
  - 降级策略实现：`backend/gangqing/semantic/mapping_fallback.py`

## 3) Task 56.3 - 跨系统聚合门禁（API 集成层）
- **Goal**: 在跨系统聚合查询入口处实现基于统一 ID 的强制门禁检查
- **Dependencies**: 依赖 Task 56.1 的映射表和 Task 56.2 的冲突检测
- **Key Decisions**:
  - 门禁位置：Semantic API 层、工具调用层、编排引擎数据获取层
  - 检查逻辑：聚合前必须验证所有源数据的统一 ID 映射一致性
  - 失败处理：映射缺失/冲突时立即返回错误，不进入下游计算
- **Deliverables**:
  - API 层门禁中间件：`backend/gangqing/api/middleware/mapping_gate.py`
  - 工具调用门禁装饰器：`backend/gangqing/tools/decorators/mapping_guard.py`
  - 聚合查询门禁实现：`backend/gangqing/semantic/aggregation_gate.py`

## 4) Task 56.4 - 证据链集成与审计（可观测层）
- **Goal**: 将映射版本信息、冲突检测结果写入 Evidence 与审计日志
- **Dependencies**: 依赖 Task 56.1-56.3 的实现
- **Key Decisions**:
  - Evidence 字段：`mapping_version`、`source_systems`、`conflict_status`
  - 审计内容：映射查询、冲突检测、门禁拦截事件
  - 贯穿字段：`requestId` 在映射全链路贯穿
- **Deliverables**:
  - Evidence 扩展：`backend/gangqing/semantic/mapping_evidence.py`
  - 审计事件定义：`backend/gangqing_db/audit_mapping.py`

# Deliverables Definition (交付物定义)
- [ ] **Directory Structure**: 明确新增/修改的目录树
  ```
  backend/
  ├── gangqing/
  │   └── semantic/
  │       ├── __init__.py
  │       ├── models/
  │       │   ├── __init__.py
  │       │   └── entity_mapping.py      # Pydantic Schema
  │       ├── mapping_versioning.py       # 版本化管理
  │       ├── conflict_detector.py        # 冲突检测
  │       ├── mapping_errors.py           # 错误映射
  │       ├── mapping_fallback.py         # 降级策略
  │       ├── aggregation_gate.py         # 聚合门禁
  │       └── mapping_evidence.py         # 证据链集成
  │   ├── api/
  │   │   └── middleware/
  │   │       └── mapping_gate.py         # API 层门禁
  │   └── tools/
  │       └── decorators/
  │           └── mapping_guard.py        # 工具门禁
  │   └── gangqing_db/
  │       └── audit_mapping.py            # 审计事件
  └── migrations/versions/
      └── xxx_add_entity_mapping_tables.py
  ```
- [ ] **Environment Variables**: 通过统一配置加载（参考 `backend/gangqing/config.py`）
  - `ENTITY_MAPPING_VERSION_RETENTION_DAYS`: 映射版本保留天数（默认 365）
  - `MAPPING_CONFLICT_AUTO_RESOLVE`: 是否启用自动冲突解决（默认 false）
- [ ] **API Contracts**: 与 `docs/api/semantic-api.md` 对齐
  - 新增端点：`GET /api/v1/semantic/mappings/{entity_type}/conflicts` - 查询映射冲突
  - 新增端点：`GET /api/v1/semantic/mappings/{entity_type}/{unified_id}/history` - 查询映射历史
- [ ] **Evidence Contract**: 证据链数据结构扩展
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
  ```
- [ ] **Auth & RBAC**: 
  - 读权限：`semantic:mapping:read`
  - 写权限：`semantic:mapping:write`
  - 冲突查看权限：`semantic:mapping:conflict:read`
- [ ] **Error Model**: 错误码补充
  - `EVIDENCE_MISMATCH`: 映射冲突或不匹配（已存在）
  - `MAPPING_VERSION_CONFLICT`: 版本冲突（新增）
  - `AGGREGATION_BLOCKED`: 聚合被门禁拦截（新增）
- [ ] **Observability**: 
  - `requestId` 贯穿映射查询全链路
  - 审计事件类型：`mapping.query`, `mapping.conflict_detected`, `mapping.aggregation_blocked`

# Verification Plan (整体验收)

## 自动化断言（冒烟测试）
- 启动真实 FastAPI 服务 + 真实 Postgres 实例
- **场景 1**: 正常映射查询链路
  - 创建设备映射 → 查询映射 → 验证返回包含 `mapping_version`
  - 断言：Evidence 包含映射版本字段
- **场景 2**: 冲突检测链路
  - 创建冲突映射（同一 unified_id 映射到多个源 ID）
  - 查询触发 `EVIDENCE_MISMATCH` 错误
  - 断言：错误包含 `code`, 英文 `message`, `requestId`, `retryable=false`
- **场景 3**: 跨系统聚合门禁
  - 尝试聚合存在映射冲突的数据
  - 断言：门禁拦截，返回 `AGGREGATION_BLOCKED` 错误
- **场景 4**: 版本化历史追溯
  - 更新映射 → 查询历史版本 → 验证版本链完整
  - 断言：历史记录包含 `valid_from/valid_to` 时间戳
- **场景 5**: 多租户隔离
  - 跨 tenant/project 访问映射数据
  - 断言：返回 `AUTH_ERROR`，记录审计日志

## 测试命令
- **Unit**: `cd backend && python -m pytest gangqing/semantic/tests/ -q`
- **Smoke**: `python backend/scripts/semantic_id_mapping_smoke_test.py`
- **Verification**: 
  - 运行冒烟测试并检查所有断言通过
  - 检查审计日志包含 `mapping.query` 事件
  - 检查 Evidence 输出包含 `mapping_version` 字段

# Output Requirement
请输出一份详细的 **Markdown 执行计划**，包含上述所有章节。
**不要写代码**，请确认你理解了全局设计后再输出计划。
```

---

### Task 56.1 - 统一 ID 映射：映射表 Schema 与版本化管理

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行统一语义层（实体与 ID 映射）下的子任务：56.1 - 映射表 Schema 与版本化管理。
角色：**高级开发工程师**。
目标是设计并实现统一 ID 映射表的数据库 Schema、Pydantic 模型、以及版本化机制。

# Critical Rules (核心约束)
- **Python/FastAPI**: 使用 Pydantic 作为对外 I/O 与工具参数的单一事实源。
- **Schema First**: 所有映射表结构必须先定义 Pydantic Schema，再实现数据库模型。
- **Evidence-First**: 映射结果必须包含版本信息，可追溯至 Evidence。
- **真实集成 (No Skip)**: 测试必须连接真实 Postgres；配置缺失或服务不可用**测试必须失败**。
- **结构化错误**: 对外错误必须包含 `code`, 英文 `message`, `requestId`, `retryable`。
- **RBAC & Audit**: 映射表读写必须做权限检查并记录审计事件，贯穿 `requestId`。
- **Read-Only Default**: 映射表写入需遵循只读默认原则（L4 治理流程）。
- **Tenant/Project 隔离**: 所有映射数据必须按 `tenant_id` + `project_id` 隔离。

# References
- PRD: docs/requirements.md（R16.1 实体与 ID 映射）
- TDD: docs/design.md（5.3 实体与 ID 映射、2.6 数据层设计）
- tasks: docs/tasks.md（56.1）
- contracts: docs/contracts/api-and-events-draft.md
- api docs: docs/api/semantic-api.md

# Execution Plan (具体步骤)

## 1) 定义 Pydantic Schema（单一事实源）
- **Files**: 
  - `backend/gangqing/semantic/models/__init__.py`（新建目录和文件）
  - `backend/gangqing/semantic/models/entity_mapping.py`（核心 Schema）
- **Action**:
  - 定义 `EntityType` Enum: `equipment`, `material`, `batch`, `order`
  - 定义 `EntityMappingBase` Pydantic 模型，字段包括：
    - `unified_id: str` - 统一实体 ID
    - `entity_type: EntityType` - 实体类型
    - `source_system: str` - 来源系统（如 ERP/MES/DCS）
    - `source_id: str` - 源系统原始 ID
    - `tenant_id: str` - 租户 ID（强制隔离）
    - `project_id: str` - 项目 ID（强制隔离）
    - `version: int` - 版本号（从 1 开始递增）
    - `valid_from: datetime` - 版本生效时间
    - `valid_to: Optional[datetime]` - 版本失效时间（当前版本为 null）
    - `created_by: Optional[str]` - 创建者
    - `metadata: Optional[Dict[str, Any]]` - 扩展元数据
  - 定义 `EntityMappingCreate` / `EntityMappingUpdate` / `EntityMappingResponse` 模型
  - 定义 `MappingVersionHistory` 历史查询响应模型

## 2) 实现数据库迁移（Alembic）
- **Files**: 
  - `backend/migrations/versions/xxx_add_entity_mapping_tables.py`（新建迁移）
- **Action**:
  - 创建 `entity_mappings` 表，包含上述所有字段
  - 添加复合唯一索引: `(unified_id, entity_type, version, tenant_id, project_id)`
  - 添加索引优化查询:
    - `(tenant_id, project_id, entity_type, unified_id)` - 按实体查询
    - `(source_system, source_id)` - 按源系统 ID 反向查询
    - `(valid_from, valid_to)` - 时间范围查询
  - 添加 `valid_to IS NULL` 部分索引用于快速定位当前有效版本

## 3) 实现版本化管理模块
- **Files**: 
  - `backend/gangqing/semantic/mapping_versioning.py`（核心模块）
  - `backend/gangqing/semantic/__init__.py`（模块导出）
- **Action**:
  - 实现 `MappingVersionManager` 类:
    - `create_mapping(mapping: EntityMappingCreate) -> EntityMappingResponse`: 创建新映射（版本从 1 开始）
    - `update_mapping(unified_id, entity_type, update: EntityMappingUpdate) -> EntityMappingResponse`: 更新映射（旧版本标记失效，创建新版本）
    - `get_current_mapping(unified_id, entity_type) -> Optional[EntityMappingResponse]`: 获取当前有效版本
    - `get_mapping_history(unified_id, entity_type) -> List[MappingVersionHistory]`: 获取版本历史
    - `soft_delete_mapping(unified_id, entity_type) -> bool`: 软删除（标记 valid_to）
  - 实现版本冲突检测：`check_version_conflict(tenant_id, project_id, unified_id, entity_type, expected_version)`

## 4) 集成 RBAC 与审计
- **Files**:
  - `backend/gangqing/semantic/mapping_versioning.py`（权限检查点）
  - `backend/gangqing_db/audit_mapping.py`（审计事件定义）
- **Action**:
  - 在 `MappingVersionManager` 方法中添加 RBAC 检查:
    - 读取操作: 需要 `semantic:mapping:read`
    - 写入操作: 需要 `semantic:mapping:write`
  - 记录审计事件:
    - `mapping.query`: 映射查询（包含 unified_id, entity_type, version）
    - `mapping.create`: 创建映射
    - `mapping.update`: 更新映射（记录旧版本 -> 新版本）
    - `mapping.delete`: 删除映射
  - 审计日志包含 `requestId`, `tenant_id`, `project_id`, `user_id`

## 5) 编写单元测试
- **Files**: 
  - `backend/gangqing/semantic/tests/test_mapping_versioning.py`（测试目录需创建）
- **Action**:
  - 测试场景：
    1. 正常创建映射 → 验证版本 = 1, valid_to = None
    2. 更新映射 → 验证旧版本 valid_to 被填充，新版本 = 2
    3. 查询历史 → 验证返回 2 个版本，时间戳正确
    4. 跨租户访问 → 验证返回 `AUTH_ERROR`
    5. 无权限写入 → 验证返回 `FORBIDDEN`
    6. 并发更新 → 验证版本冲突检测

# Verification (验收标准)

## 自动化测试
- **Unit**: `cd backend && python -m pytest gangqing/semantic/tests/test_mapping_versioning.py -v`
  - 覆盖率要求: 核心方法 100%，至少覆盖正常路径 + 4 个错误路径
- **Migration Test**: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
  - 验证迁移可回滚

## 手动验证（Curl 命令示例）
```bash
# 假设服务运行在 localhost:8000，已获取 JWT token
TOKEN=$(python backend/scripts/get_test_token.py)

# 1. 创建设备映射
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-56-1-001" \
  -H "X-Tenant-Id: test-tenant" \
  -H "X-Project-Id: test-project" \
  -H "Content-Type: application/json" \
  "http://localhost:8000/api/v1/semantic/equipment" \
  -d '{"unified_id":"EQ-001","equipment_name":"Test Caster","source_system":"MES","source_id":"MES-EQ-001"}'

# 2. 查询映射历史
curl -X GET \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-56-1-002" \
  -H "X-Tenant-Id: test-tenant" \
  -H "X-Project-Id: test-project" \
  "http://localhost:8000/api/v1/semantic/mappings/equipment/EQ-001/history"
```

## 验收检查清单
- [ ] 数据库表创建成功，索引生效
- [ ] Pydantic Schema 校验通过（边界值测试）
- [ ] 版本化管理：创建 → 更新 → 查询历史流程完整
- [ ] RBAC：无权限用户被拒绝并记录审计
- [ ] 隔离：跨租户数据不可见
- [ ] 审计日志包含完整字段（requestId, tenant_id, user_id, 操作类型）
- [ ] 单元测试通过率 100%，覆盖率 >= 80%

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
- **摘要**: 说明本次修改了哪些文件、哪些章节/段落发生变更。
- **关键片段**: 仅粘贴与本子任务契约/实现要求直接相关的最小必要片段（如 Pydantic Schema 定义、核心类方法）。
- **文件路径**: 给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。
- **输出验证命令与关键输出摘要**（文本）。
```

---

### Task 56.2 - 冲突检测与拒答/降级机制

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行统一语义层（实体与 ID 映射）下的子任务：56.2 - 冲突检测与拒答/降级机制。
角色：**高级开发工程师**。
目标是实现映射冲突检测逻辑，定义 `EVIDENCE_MISMATCH` 错误语义与降级策略。

# Critical Rules (核心约束)
- **Schema First**: 冲突检测结果必须使用 Pydantic 模型定义。
- **Evidence-First**: 冲突状态必须进入 Evidence，不可遗漏。
- **冲突必须拒绝聚合**: 检测到冲突时，下游聚合操作必须被阻断。
- **降级策略**: 冲突时降级为"仅展示可用数据与来源"，禁止编造聚合结果。
- **真实集成 (No Skip)**: 测试必须连接真实 Postgres；配置缺失或服务不可用**测试必须失败**。
- **结构化错误**: 冲突错误使用 `EVIDENCE_MISMATCH` 错误码，英文 message。
- **RBAC & Audit**: 冲突检测过程必须记录审计事件。

# References
- PRD: docs/requirements.md（R16.1、R14.4 幻觉检测与降级）
- TDD: docs/design.md（5.3 实体与 ID 映射、6.2 错误模型）
- tasks: docs/tasks.md（56.2）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan (具体步骤)

## 1) 定义冲突检测 Schema
- **Files**: 
  - `backend/gangqing/semantic/models/conflict_detection.py`（新建）
- **Action**:
  - 定义 `ConflictType` Enum:
    - `MULTI_TO_ONE`: 同一 unified_id 映射到多个 source_id
    - `CROSS_SYSTEM`: 跨系统 ID 冲突
    - `MAPPING_MISSING`: 映射缺失
    - `VERSION_MISMATCH`: 版本不匹配
  - 定义 `ConflictDetectionResult` Pydantic 模型:
    - `unified_id: str`
    - `entity_type: EntityType`
    - `conflict_type: ConflictType`
    - `conflict_details: Dict[str, Any]` - 冲突详情（如冲突的源系统列表）
    - `severity: Literal["critical", "warning", "info"]`
    - `detected_at: datetime`
  - 定义 `ConflictResolutionStrategy` Enum: `REJECT`, `DEGRADE`, `OVERRIDE`

## 2) 实现冲突检测模块
- **Files**: 
  - `backend/gangqing/semantic/conflict_detector.py`（核心模块）
- **Action**:
  - 实现 `ConflictDetector` 类:
    - `detect_by_unified_id(unified_id, entity_type) -> List[ConflictDetectionResult]`: 按统一 ID 检测
    - `detect_by_source_id(source_system, source_id) -> List[ConflictDetectionResult]`: 按源系统 ID 反向检测
    - `detect_multi_to_one(tenant_id, project_id) -> List[ConflictDetectionResult]`: 扫描所有多对一冲突
    - `validate_mapping_consistency(mappings) -> Optional[ConflictDetectionResult]`: 验证映射一致性
  - 检测逻辑：
    - 查询同一 unified_id 下的所有 source_id
    - 如果数量 > 1 且 source_system 不同 → 标记 `MULTI_TO_ONE` 冲突
    - 如果映射不存在 → 标记 `MAPPING_MISSING`

## 3) 实现错误映射与降级策略
- **Files**: 
  - `backend/gangqing/semantic/mapping_errors.py`（错误映射）
  - `backend/gangqing/semantic/mapping_fallback.py`（降级策略）
- **Action**:
  - `mapping_errors.py`:
    - `map_conflict_to_error(conflict: ConflictDetectionResult) -> ErrorResponse`
    - 将冲突映射为 `EVIDENCE_MISMATCH` 错误
    - 英文 message 模板："Mapping conflict detected: {conflict_type} for {entity_type} {unified_id}. Details: {details}"
  - `mapping_fallback.py`:
    - `create_degraded_response(conflict: ConflictDetectionResult) -> DegradedResult`
    - 降级结果包含：可用数据源列表、冲突说明、人工审核建议
    - 不返回聚合数值，仅返回原始数据与来源

## 4) 集成到 API 层
- **Files**: 
  - `backend/gangqing/api/v1/semantic.py`（API 路由）
- **Action**:
  - 在查询端点添加冲突检测调用
  - 如果检测到 `critical` 级别冲突 → 返回 `EVIDENCE_MISMATCH` 错误
  - 如果检测到 `warning` 级别冲突 → 返回降级结果 + warning 事件

## 5) 编写测试
- **Files**: 
  - `backend/gangqing/semantic/tests/test_conflict_detector.py`
- **Action**:
  - 测试场景：
    1. 创建多对一冲突 → 验证检测到 `MULTI_TO_ONE`
    2. 查询不存在的映射 → 验证检测到 `MAPPING_MISSING`
    3. 验证降级结果不包含聚合数值
    4. 验证错误包含英文 message 和 requestId

# Verification (验收标准)

## 自动化测试
- **Unit**: `cd backend && python -m pytest gangqing/semantic/tests/test_conflict_detector.py -v`

## 验收检查清单
- [x] 冲突检测覆盖所有定义的类型
- [x] `EVIDENCE_MISMATCH` 错误包含英文 message、requestId、retryable=false
- [x] 降级结果不包含编造数据，仅展示来源
- [x] 审计日志记录冲突检测事件
- [x] 单元测试覆盖率 >= 80%

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Task 56.3 - 跨系统聚合门禁

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行统一语义层（实体与 ID 映射）下的子任务：56.3 - 跨系统聚合门禁。
角色：**高级开发工程师**。
目标是在跨系统聚合查询入口处实现基于统一 ID 的强制门禁检查。

# Critical Rules (核心约束)
- **聚合前必须验证**: 任何跨系统聚合操作前必须验证所有源数据的统一 ID 映射一致性。
- **失败立即阻断**: 映射缺失/冲突时立即返回错误，不进入下游计算。
- **门禁多层覆盖**: API 层、工具调用层、编排引擎数据获取层均需覆盖。
- **Evidence-First**: 门禁拦截事件必须写入 Evidence。
- **结构化错误**: 门禁拦截返回 `AGGREGATION_BLOCKED` 错误码。
- **RBAC & Audit**: 门禁检查过程必须记录审计。

# References
- PRD: docs/requirements.md（R16.1）
- TDD: docs/design.md（2.5 工具与适配层、2.10 工具装饰器）
- tasks: docs/tasks.md（56.3）

# Execution Plan (具体步骤)

## 1) 实现聚合门禁核心逻辑
- **Files**: 
  - `backend/gangqing/semantic/aggregation_gate.py`（核心模块）
- **Action**:
  - 实现 `AggregationGate` 类:
    - `check_aggregation_prerequisites(entity_refs: List[EntityRef]) -> AggregationGateResult`
    - `EntityRef` 包含：unified_id, entity_type, required_source_systems
  - 检查逻辑：
    1. 遍历所有 entity_refs
    2. 查询每个 unified_id 的当前映射
    3. 如果有任何映射缺失 → 返回 `AGGREGATION_BLOCKED`
    4. 如果有任何映射冲突 → 返回 `AGGREGATION_BLOCKED`
    5. 所有检查通过 → 返回 `ALLOWED`

## 2) 实现 API 层门禁中间件
- **Files**: 
  - `backend/gangqing/api/middleware/mapping_gate.py`（新建）
- **Action**:
  - 创建 FastAPI 中间件/依赖函数 `require_valid_mapping(entity_type, unified_id)`
  - 在 Semantic API 聚合查询端点应用
  - 拦截时返回 403 + 结构化错误:
    ```json
    {
      "code": "AGGREGATION_BLOCKED",
      "message": "Aggregation blocked due to mapping inconsistency: missing or conflicting unified_id mappings",
      "details": {"entity_refs": [...], "conflicts": [...]},
      "retryable": false,
      "requestId": "..."
    }
    ```

## 3) 实现工具调用门禁装饰器
- **Files**: 
  - `backend/gangqing/tools/decorators/mapping_guard.py`（新建）
- **Action**:
  - 实现装饰器 `@require_mapping_consistency(entity_refs_extractor)`
  - 装饰器自动：
    1. 从工具参数中提取 entity_refs
    2. 调用 `AggregationGate.check_aggregation_prerequisites`
    3. 检查失败时抛出 `AggregationBlockedError`
  - 应用到 Postgres 查询工具等需要聚合的工具

## 4) 编写测试
- **Files**: 
  - `backend/gangqing/semantic/tests/test_aggregation_gate.py`
  - `backend/gangqing/api/tests/test_mapping_middleware.py`
- **Action**:
  - 测试场景：
    1. 所有映射正常 → 允许聚合
    2. 任一映射缺失 → 阻断并返回 `AGGREGATION_BLOCKED`
    3. 任一映射冲突 → 阻断并返回 `AGGREGATION_BLOCKED`
    4. 跨租户映射 → 阻断并返回 `AUTH_ERROR`

# Verification (验收标准)

## 自动化测试
- **Unit**: `cd backend && python -m pytest gangqing/semantic/tests/test_aggregation_gate.py -v`

## 验收检查清单
- [ ] 门禁在 API 层、工具层、编排层均有实现
- [ ] 映射缺失/冲突时立即阻断，不进入下游
- [ ] `AGGREGATION_BLOCKED` 错误包含英文 message、requestId
- [ ] 门禁拦截事件记录审计日志
- [ ] 单元测试覆盖率 >= 80%

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Task 56.4 - 证据链集成与审计

```markdown
# Context
你是 GangQing（钢擎）项目的负责落地与验收的工程师。
你正在执行统一语义层（实体与 ID 映射）下的子任务：56.4 - 证据链集成与审计。
角色：**高级开发工程师**。
目标是将映射版本信息、冲突检测结果写入 Evidence 与审计日志。

# Critical Rules (核心约束)
- **Evidence-First**: 任何使用映射数据的操作必须在 Evidence 中记录映射版本。
- **审计全覆盖**: 映射查询、冲突检测、门禁拦截必须全部记录审计。
- **贯穿 requestId**: `requestId` 必须在映射全链路贯穿。
- **真实集成 (No Skip)**: 测试必须连接真实服务。

# References
- PRD: docs/requirements.md（R16.1、R11.1 审计日志）
- TDD: docs/design.md（2.10.5 Evidence 引擎、2.8 可观测与审计层）
- contracts: docs/contracts/api-and-events-draft.md

# Execution Plan (具体步骤)

## 1) 扩展 Evidence 数据结构
- **Files**: 
  - `backend/gangqing/semantic/mapping_evidence.py`（新建）
- **Action**:
  - 定义 `MappingEvidence` Pydantic 模型:
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
        gate_passed: bool  # 门禁是否通过
        gate_block_reason: Optional[str]  # 如果被阻断，记录原因
    ```
  - 实现 `MappingEvidenceBuilder` 类用于构建 Evidence

## 2) 集成到 Evidence 引擎
- **Files**: 
  - `backend/gangqing/semantic/mapping_versioning.py`（修改：添加 Evidence 输出）
  - `backend/gangqing/semantic/conflict_detector.py`（修改：添加 Evidence 输出）
  - `backend/gangqing/semantic/aggregation_gate.py`（修改：添加 Evidence 输出）
- **Action**:
  - 在映射查询、冲突检测、门禁检查处调用 `MappingEvidenceBuilder`
  - 将 `MappingEvidence` 对象传递到 Evidence 引擎
  - 确保 Evidence 输出到 SSE `evidence.update` 事件

## 3) 定义审计事件
- **Files**: 
  - `backend/gangqing_db/audit_mapping.py`（新建）
- **Action**:
  - 定义审计事件模型 `AuditMappingEvent`
  - 事件类型：
    - `mapping.query`: 映射查询（字段：unified_id, entity_type, version, result_count）
    - `mapping.conflict_detected`: 冲突检测（字段：conflict_type, unified_id, details）
    - `mapping.aggregation_blocked`: 门禁拦截（字段：reason, entity_refs）
    - `mapping.version_created/updated/deleted`: 版本变更
  - 所有事件包含：requestId, tenant_id, project_id, user_id, timestamp

## 4) 集成到审计日志系统
- **Files**: 
  - `backend/gangqing_db/audit_log.py`（修改：添加映射事件处理）
- **Action**:
  - 在审计日志表中添加映射事件类型
  - 实现 `AuditMappingLogger` 类
  - 在映射模块中注入审计日志记录

## 5) 编写测试
- **Files**: 
  - `backend/gangqing/semantic/tests/test_mapping_evidence.py`
  - `backend/gangqing_db/tests/test_audit_mapping.py`
- **Action**:
  - 测试场景：
    1. 映射查询 → 验证 Evidence 包含 mapping_version
    2. 冲突检测 → 验证 Evidence 包含 conflict_status
    3. 门禁拦截 → 验证审计日志包含 mapping.aggregation_blocked
    4. 验证 requestId 贯穿所有事件

# Verification (验收标准)

## 自动化测试
- **Unit**: 
  - `cd backend && python -m pytest gangqing/semantic/tests/test_mapping_evidence.py -v`
  - `cd backend && python -m pytest gangqing_db/tests/test_audit_mapping.py -v`
- **Smoke**: `python backend/scripts/semantic_id_mapping_smoke_test.py`

## 验收检查清单
- [ ] Evidence 输出包含 `mapping_version`, `source_systems`, `conflict_status`
- [ ] 审计日志覆盖所有映射相关事件
- [ ] `requestId` 在映射全链路贯穿
- [ ] SSE `evidence.update` 事件包含映射相关信息
- [ ] 单元测试覆盖率 >= 80%

# Output Requirement
交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。
```

---

### Checklist（自检清单）

#### Umbrella 检查点
- [x] 包含 `# Critical Rules` 并明确禁止写代码
- [x] `# Execution Plan` 覆盖所有子任务（56.1 到 56.4）
- [x] 定义全局技术标准（Schema 单一事实源、结构化错误、Evidence-First、只读默认、RBAC/审计）
- [x] 包含 `Deliverables Definition` 章节（目录结构、环境变量、API 契约、Evidence 契约）
- [x] 包含 `Verification Plan` 章节（自动化断言、测试命令）

#### Sub-task 检查点（56.1-56.4）
- [x] 明确列出 **Target Files**（要修改哪些文件）
- [x] 验收标准中包含具体的 **自动化测试断言**
- [x] 强调 **真实环境集成 (Real Integration)** 而非 Mock
- [x] 包含契约校验要求（Pydantic Schema）
- [x] 包含证据链生成/展示/可追溯字段要求
- [x] 包含鉴权/RBAC/审计字段与结构化错误要求

#### 编码规范检查点
- [x] 错误 message 必须为英文
- [x] 结构化错误字段完整（code/message/requestId/retryable/details）
- [x] Evidence 字段定义完整（mapping_version/source_systems/conflict_status）
- [x] RBAC/审计/requestId 贯穿要求明确
- [x] Tenant/Project 隔离要求明确
- [x] 真实集成测试（No Skip）要求明确
