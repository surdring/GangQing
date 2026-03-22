# Task 43: 配置外部化与配置校验 - 执行计划

**目标**：建立统一的配置加载机制、配置 schema 校验、缺配置快速失败策略，以及 `.env.example` 完整文档化。

**原则**：所有 URL、端口、超时、重试、路由策略、配额、开关必须外部化（环境变量或配置文件），**禁止硬编码**。

---

## 1) 任务 43.1 - 配置加载与 Schema 校验：缺配置快速失败（英文错误）

### 目标
实现前端和后端的统一配置加载机制，使用 schema 进行配置校验，确保关键配置缺失时服务启动立即失败并输出清晰英文错误。

### 关键设计决策

#### 后端配置架构（Pydantic BaseSettings）

**文件位置**：`backend/gangqing/config.py`（新建）

**分层设计**：

| 层级 | 模块 | 职责 |
|------|------|------|
| 基础层 | `BaseConfigModel` | 通用校验逻辑、环境变量加载、`.env.local` 支持 |
| 分类层 | `DatabaseConfig` / `LLMConfig` / `SecurityConfig` / `AuditConfig` / `ToolConfig` / `ObservabilityConfig` | 按功能分组的配置模型 |
| 聚合层 | `GangQingConfig` | 统一聚合所有配置；启动时一次性校验 |
| 访问层 | `get_config()` | 全局访问点；确保单例 |

**配置加载优先级**（强制）：
1. 进程环境变量（最高优先级）
2. `.env.local` 文件（仅本地开发）
3. 默认值（如定义）

**`.env.local` 约束**：
- 仅用于本地开发与测试
- 严禁提交到仓库（已存在于 `.gitignore`）
- 加载库使用 `python-dotenv`，显式指定路径（仓库根目录）

#### 前端配置架构（Zod Schema）

**文件位置**：
- `web/src/config/index.ts`（新建：配置加载与访问）
- `web/src/schemas/config.ts`（更新：补充完整配置 schema）

**配置分类**：

| 分类 | Schema 名称 | 说明 |
|------|-------------|------|
| 运行时 | `WebRuntimeConfigSchema` | API Base URL、租户/项目 ID、SSE 配置（已存在，需扩展） |
| 功能开关 | `FeatureFlagsSchema` | 各功能模块启用/禁用开关 |
| 日志 | `LoggingConfigSchema` | 日志级别、格式配置 |

**加载机制**：
- 构建时通过 `import.meta.env` 读取环境变量
- 运行时通过统一 `loadConfig()` 函数校验
- 校验失败时在控制台输出英文错误，并抛出异常阻止应用启动

#### 配置分类完整清单

**后端必需配置（缺失时快速失败）**：

| 分类 | 配置项 | 用途 | 是否可默认 |
|------|--------|------|------------|
| **Database** | `GANGQING_DATABASE_URL` | PostgreSQL 连接串 | ❌ 必填 |
| **Security** | `GANGQING_JWT_SECRET` | JWT 签名密钥 | ❌ 必填（生产） |
| **Security** | `GANGQING_JWT_ALG` | JWT 算法 | ✅ 默认 HS256 |
| **Tenant** | `GANGQING_ISOLATION_ENABLED` | 多租户隔离开关 | ✅ 默认 true |
| **Tool** | `GANGQING_TOOL_MAX_RETRIES` | 工具最大重试次数 | ✅ 默认 3 |
| **Audit** | `GANGQING_AUDIT_ASYNC_ENABLED` | 审计异步写入 | ✅ 默认 false |

**后端可选配置（有合理默认值）**：

| 分类 | 配置项 | 默认值 | 说明 |
|------|--------|--------|------|
| **API** | `GANGQING_API_HOST` | 127.0.0.1 | 监听地址 |
| **API** | `GANGQING_API_PORT` | 8000 | 监听端口 |
| **Log** | `GANGQING_LOG_LEVEL` | INFO | 日志级别 |
| **Log** | `GANGQING_LOG_FORMAT` | json | 日志格式 |
| **LLM** | `GANGQING_LLAMACPP_BASE_URL` | - | llama.cpp 地址 |
| **Health** | `GANGQING_HEALTHCHECK_CACHE_TTL_SECONDS` | 0 | 健康检查缓存 |

**前端必需配置**：

| 分类 | 配置项 | 用途 |
|------|--------|------|
| **Runtime** | `VITE_API_BASE_URL` | 后端 API 地址 |
| **Runtime** | `VITE_TENANT_ID` | 默认租户 ID（开发用） |
| **Runtime** | `VITE_PROJECT_ID` | 默认项目 ID（开发用） |

### 快速失败策略

**后端启动流程**：
1. 导入 `gangqing.config` 时立即触发 `GangQingConfig()` 实例化
2. Pydantic 自动校验所有字段类型与取值范围
3. 对标记为 `required_at_startup` 的字段，若缺失立即抛出 `ConfigMissingError`
4. 错误消息格式（英文，结构化）：
   ```
   Missing required configuration: {CONFIG_NAME}. 
   Please set {ENV_VAR} in .env.local or environment.
   See .env.example for all available options.
   ```
5. 异常捕获并记录结构化日志后，调用 `sys.exit(1)` 终止进程

**前端启动流程**：
1. `main.tsx` 中首先调用 `loadConfig()`
2. Zod 校验所有 schema
3. 校验失败时输出英文错误到控制台，并阻止 React 应用挂载
4. 错误格式：
   ```
   [Config Validation Error] {field}: {message}
   Please check your .env.local or build-time environment variables.
   ```

### 交付物

- [ ] `backend/gangqing/config.py` - 后端 Pydantic 配置模型与加载机制
- [ ] `backend/tests/test_config_validation.py` - 后端配置校验单元测试
- [ ] `web/src/config/index.ts` - 前端配置加载与访问
- [ ] `web/src/schemas/config.ts` - 前端 Zod schema（扩展已有内容）
- [ ] `web/src/config/__tests__/config.test.ts` - 前端配置校验单元测试

---

## 2) 任务 43.2 - 配置错误消息规范与错误码定义

### 目标
统一定义配置相关的错误码、错误消息格式、以及配置校验失败的日志输出规范。

### 错误码定义

新增配置专用错误码（补充到全局错误码定义）：

| 错误码 | 触发场景 | retryable | HTTP 状态码 |
|--------|----------|-----------|-------------|
| `CONFIG_MISSING` | 启动时缺少必需配置项 | false | 500（启动失败） |
| `CONFIG_INVALID` | 配置值格式/取值范围不合法 | false | 500（启动失败） |
| `CONFIG_TYPE_ERROR` | 配置值类型不匹配（如预期 int 得 str） | false | 500（启动失败） |
| `CONFIG_DEPRECATED` | 使用了已废弃的配置项 | false | warning |

**错误码声明位置**：
- 后端：`backend/gangqing/common/errors.py`（补充 `ErrorCode` 枚举）
- 文档：`docs/contracts/api-and-events-draft.md`（更新错误码表）

### 错误消息模板（英文）

**缺失配置**：
```python
f"Missing required configuration: {config_name}. "
f"Please set {env_var} in .env.local or environment. "
f"See .env.example for all available options."
```

**格式错误**：
```python
f"Invalid configuration value for {config_name}: {value}. "
f"Expected format: {expected_format}. "
f"Error: {validation_error}"
```

**类型错误**：
```python
f"Configuration type error for {config_name}: "
f"expected {expected_type}, got {actual_type}. "
f"Please check .env.example for correct format."
```

### 结构化日志输出规范

配置加载日志必须包含以下字段：

```json
{
  "timestamp": "2026-03-21T07:55:00Z",
  "level": "ERROR",
  "code": "CONFIG_MISSING",
  "config_key": "GANGQING_DATABASE_URL",
  "config_category": "database",
  "message": "Missing required configuration: DATABASE_URL...",
  "stage": "startup",
  "status": "failed"
}
```

**日志级别策略**：
- 配置加载成功：`INFO` 级别，记录已加载配置的分类统计（不含敏感值）
- 配置缺失/无效：`ERROR` 级别，包含完整错误上下文
- 配置使用默认值：`WARNING` 级别，提醒显式设置

### 健康检查集成

健康检查端点 `/api/v1/health` 的 `dependencies` 数组中增加 `config` 项：

```json
{
  "name": "config",
  "status": "ok | degraded | unavailable",
  "critical": true,
  "details": {
    "reason": "not_configured | missing_required_keys | validation_failed",
    "missingKeys": ["GANGQING_DATABASE_URL"]
  }
}
```

**状态映射**：
- `ok`: 所有必需配置已加载且校验通过
- `degraded`: 使用默认值运行，建议显式配置
- `unavailable`: 缺少必需配置，服务无法启动或运行

### 交付物

- [ ] `backend/gangqing/common/errors.py` - 补充配置错误码
- [ ] `backend/gangqing/config.py` - 包含配置错误消息模板
- [ ] `docs/contracts/api-and-events-draft.md` - 更新错误码表（补充 CONFIG_* 错误码）
- [ ] `docs/api/openapi.yaml` - 更新 HealthResponse 的 config 依赖说明

---

## 3) 任务 43.3 - `.env.example` 完整性与文档同步

### 目标
完整列举所有配置项到 `.env.example`，并确保与代码中 schema 定义同步。

### `.env.example` 结构规范

按功能分组，每组包含标准格式注释：

```bash
# ==========================================
# Group: {分类名} ({重要性}: REQUIRED/OPTIONAL)
# 说明：{功能描述}
# ==========================================

# {配置项名}
# 用途：{详细说明}
# 是否必填：{YES/NO}
# 默认值：{默认值或无}
# 示例值：{示例}
{ENV_VAR_NAME}={默认值或空}
```

### 配置分组结构

| 分组 | 重要性 | 包含配置项 |
|------|--------|-----------|
| **Core** | REQUIRED | GANGQING_ENV, GANGQING_LOG_LEVEL, GANGQING_LOG_FORMAT |
| **API Server** | REQUIRED | GANGQING_API_HOST, GANGQING_API_PORT |
| **Database** | REQUIRED | GANGQING_DATABASE_URL |
| **Security/JWT** | REQUIRED | GANGQING_JWT_SECRET, GANGQING_JWT_ALG, GANGQING_JWT_EXP_HOURS |
| **Isolation** | REQUIRED | GANGQING_ISOLATION_ENABLED |
| **Audit** | OPTIONAL | GANGQING_AUDIT_ASYNC_ENABLED, GANGQING_AUDIT_ASYNC_MAX_WORKERS |
| **Masking** | OPTIONAL | GANGQING_MASKING_DEFAULT_ACTION, GANGQING_MASKING_POLICY_REQUIRED |
| **Guardrail** | OPTIONAL | GANGQING_GUARDRAIL_POLICY_REQUIRED |
| **Tool** | OPTIONAL | GANGQING_TOOL_MAX_RETRIES, GANGQING_TOOL_BACKOFF_* |
| **Postgres Tool** | OPTIONAL | GANGQING_POSTGRES_TOOL_* |
| **LLM/llama.cpp** | OPTIONAL | GANGQING_LLAMACPP_* |
| **Provider** | OPTIONAL | GANGQING_PROVIDER_* |
| **Health Check** | OPTIONAL | GANGQING_HEALTHCHECK_* |
| **Contract Validation** | OPTIONAL | GANGQING_CONTRACT_VALIDATION_* |
| **Seed Data** | OPTIONAL | GANGQING_SEED_* |
| **Data Quality** | OPTIONAL | GANGQING_DATA_QUALITY_* |
| **Connectors** | OPTIONAL | GANGQING_CONNECTOR_* |
| **CORS** | OPTIONAL | GANGQING_CORS_ALLOW_ORIGINS |
| **Upload** | OPTIONAL | GANGQING_UPLOAD_DIR |
| **Bootstrap** | OPTIONAL | GANGQING_BOOTSTRAP_* |
| **Service Info** | OPTIONAL | GANGQING_SERVICE_NAME, GANGQING_BUILD, GANGQING_COMMIT |

### 配置变更同步机制

**文档同步检查清单**：
- 新增配置项时，必须同步更新：
  1. `.env.example` - 添加配置项及完整注释
  2. `backend/gangqing/config.py` - 添加 Pydantic 字段定义
  3. `docs/contracts/api-and-events-draft.md` - 如涉及错误码变更
  4. `docs/api/openapi.yaml` - 如影响 API 契约

**自动化校验脚本（可选，推荐）**：
```python
# backend/scripts/check_env_example_sync.py
# 功能：检查 .env.example 中的配置项是否都在 Pydantic 模型中有定义
```

### 交付物

- [ ] `.env.example` - 完整更新，按规范分组和注释
- [ ] `docs/config.md`（新建）- 配置项完整参考文档，包含每个配置项的详细说明

---

## 4) 目录结构定义

### 后端文件结构

```
backend/gangqing/
├── __init__.py
├── config.py                 # NEW: 统一配置模型与加载
├── common/
│   ├── __init__.py
│   ├── errors.py              # UPDATE: 补充 CONFIG_* 错误码
│   └── logging.py             # UPDATE: 支持配置日志级别/格式
├── app/
│   └── main.py                # UPDATE: 启动时加载配置
└── ...

tests/
├── test_config_validation.py   # NEW: 配置校验单元测试
```

### 前端文件结构

```
web/src/
├── config/
│   ├── index.ts              # NEW: 配置加载与访问
│   └── __tests__/
│       └── config.test.ts    # NEW: 配置校验单元测试
├── schemas/
│   └── config.ts             # UPDATE: 补充完整配置 schema
└── main.tsx                  # UPDATE: 启动时加载配置
```

### 文档结构

```
docs/
├── contracts/
│   └── api-and-events-draft.md   # UPDATE: 补充 CONFIG_* 错误码
├── api/
│   └── openapi.yaml              # UPDATE: HealthResponse config 依赖
├── config.md                     # NEW: 配置项参考文档
└── tasks.md                      # UPDATE: 标记任务 43 完成
```

---

## 5) 验证计划（整体验收）

### 单元测试

**后端**：`pytest backend/tests/test_config_validation.py -v`

测试场景：
1. ✅ 正常配置加载（所有必需配置存在且合法）
2. ✅ 可选配置使用默认值
3. ❌ 缺失必需配置时快速失败
4. ❌ 配置值格式错误时返回 CONFIG_INVALID
5. ❌ 配置值类型错误时返回 CONFIG_TYPE_ERROR
6. ✅ 环境变量优先级高于 `.env.local`
7. ✅ 敏感配置项（如密码）在日志中脱敏

**前端**：`npm -C web test`

测试场景：
1. ✅ 正常配置加载
2. ❌ 配置校验失败时阻止应用启动
3. ✅ 从 `import.meta.env` 正确读取环境变量

### 冒烟测试

**脚本**：`backend/scripts/config_validation_smoke_test.py`

测试场景：
1. ✅ 配置完整时服务正常启动
2. ❌ 移除必需配置（如 `GANGQING_DATABASE_URL`），验证服务启动立即失败
3. ✅ 验证错误消息为英文且清晰
4. ✅ 验证日志包含结构化错误字段（`code`, `config_key`）
5. ✅ 验证 `.env.local` 加载机制（存在时优先）
6. ✅ 健康检查端点 `/api/v1/health` 返回 config 依赖状态

### 配置一致性验证

手动检查清单：
- [ ] `.env.example` 中所有配置项在 `backend/gangqing/config.py` 中有对应定义
- [ ] `backend/gangqing/config.py` 中所有字段在 `.env.example` 中有示例
- [ ] 前端 `web/src/schemas/config.ts` 中必需配置与后端一致
- [ ] 错误码 `CONFIG_MISSING`, `CONFIG_INVALID`, `CONFIG_TYPE_ERROR` 在全局错误码中定义

---

## 6) 接口定义（Schema 单一事实源）

### 后端 Pydantic 模型接口

```python
# backend/gangqing/config.py

from pydantic import BaseSettings, Field, validator
from typing import Optional, List

class DatabaseConfig(BaseSettings):
    """数据库配置"""
    url: str = Field(..., env="GANGQING_DATABASE_URL")
    
    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"

class SecurityConfig(BaseSettings):
    """安全配置"""
    jwt_secret: str = Field(..., env="GANGQING_JWT_SECRET")
    jwt_alg: str = Field("HS256", env="GANGQING_JWT_ALG")
    jwt_exp_hours: int = Field(8, env="GANGQING_JWT_EXP_HOURS")

class GangQingConfig(BaseSettings):
    """统一配置聚合"""
    env: str = Field("dev", env="GANGQING_ENV")
    log_level: str = Field("INFO", env="GANGQING_LOG_LEVEL")
    log_format: str = Field("json", env="GANGQING_LOG_FORMAT")
    
    # 子配置
    database: DatabaseConfig
    security: SecurityConfig
    # ... 其他配置
    
    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"
        # 优先级：环境变量 > .env.local > 默认值
        env_prefix = "GANGQING_"

def get_config() -> GangQingConfig:
    """获取全局配置实例（单例）"""
    ...
```

### 前端 Zod Schema 接口

```typescript
// web/src/schemas/config.ts

import { z } from 'zod';

export const WebRuntimeConfigSchema = z.object({
  apiBaseUrl: z.string().url(),
  tenantId: z.string().min(1),
  projectId: z.string().min(1),
  // 扩展其他必需配置
});

export const FeatureFlagsSchema = z.object({
  enableAudit: z.boolean().default(true),
  enableIsolation: z.boolean().default(true),
  // 其他功能开关
});

export const AppConfigSchema = z.object({
  runtime: WebRuntimeConfigSchema,
  features: FeatureFlagsSchema,
  // 其他配置分组
});

export type AppConfig = z.infer<typeof AppConfigSchema>;
```

---

## 7) 依赖关系

```
任务 43.1 (配置加载与校验)
    │
    ├── 依赖：无（基础设施，可被其他任务依赖）
    │
    └── 被依赖：
        ├── 任务 43.2 (配置错误消息规范)
        └── 几乎所有其他后端/前端任务

任务 43.2 (配置错误消息规范)
    │
    ├── 依赖：任务 43.1（配置加载机制）
    │
    └── 被依赖：无

任务 43.3 (.env.example 完整性)
    │
    ├── 依赖：任务 43.1（明确所有配置项）
    │
    └── 被依赖：无
```

---

## 8) 风险与注意事项

| 风险 | 缓解措施 |
|------|----------|
| 配置变更导致现有环境启动失败 | 1. 分阶段引入：先标记 deprecated，下一版本改为必需<br>2. 提供详细的迁移指南 |
| 敏感配置泄露 | 1. 日志中自动脱敏<br>2. 健康检查不暴露配置值<br>3. 审计不记录敏感配置内容 |
| 前后端配置不一致 | 1. 建立配置变更同步检查清单<br>2. 冒烟测试验证配置一致性 |
| 启动失败难以排查 | 1. 错误消息必须包含配置项名称和环境变量名<br>2. 结构化日志包含完整上下文 |

---

## 9) 验收标准

- [ ] `backend/gangqing/config.py` 实现统一的 Pydantic 配置模型
- [ ] `web/src/config/index.ts` 实现统一的前端配置加载
- [ ] 关键配置缺失时服务启动立即失败，并输出清晰的英文错误消息
- [ ] `.env.example` 完整列举所有配置项，按功能分组，每项包含详细注释
- [ ] 新增 `CONFIG_MISSING`, `CONFIG_INVALID`, `CONFIG_TYPE_ERROR` 错误码
- [ ] 健康检查 `/api/v1/health` 返回 config 依赖状态
- [ ] 单元测试覆盖正常加载、缺配置失败、配置类型错误场景
- [ ] 冒烟测试验证配置缺失时的快速失败行为
- [ ] 验收日志记录在 `reports/YYYY-MM-DD_T43_config-externalization.md`
