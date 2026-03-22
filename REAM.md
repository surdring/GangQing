# GangQing 开发与部署说明

本文档用于指导在本仓库中进行本地开发、构建与部署（前端 + 后端）。

## 1. 仓库结构

- **后端**：`backend/`（FastAPI）
- **前端**：`web/`（Vite + React + TypeScript）
- **文档**：`docs/`
- **验证脚本**：`backend/scripts/`

## 2. 环境变量与配置（强制）

### 2.1 后端环境变量

后端环境变量示例见：`.env.example`。

- 推荐：在仓库根目录创建 `.env.local`（不会提交到仓库），并填入真实值。
- 后端常用：
  - `GANGQING_API_HOST`
  - `GANGQING_API_PORT`
  - `GANGQING_DATABASE_URL`
  - `GANGQING_BOOTSTRAP_ADMIN_USER_ID` / `GANGQING_BOOTSTRAP_ADMIN_PASSWORD`
  - `GANGQING_TENANT_ID` / `GANGQING_PROJECT_ID`（用于脚本/造数/冒烟测试）

### 2.2 前端运行时配置（Vite env，强制 Zod 校验）

前端使用 `web/runtimeConfig.ts` 从 `import.meta.env` 读取配置，并通过 `web/schemas/config.ts` 做 **Zod 校验**。

强制要求：**不得在代码中硬编码默认值**；缺失配置时会抛出英文错误（便于日志检索）。

需要提供的变量（推荐写到 `web/.env.local`）：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_TENANT_ID=t1
VITE_PROJECT_ID=p1

# SSE 重连策略（毫秒/次数）
VITE_SSE_RECONNECT_BASE_DELAY_MS=200
VITE_SSE_RECONNECT_MAX_DELAY_MS=2000
VITE_SSE_RECONNECT_MAX_ATTEMPTS=3
```

说明：

- **`VITE_API_BASE_URL`**：后端 API 基址（不带尾部 `/` 也可）。
- **`VITE_TENANT_ID`/`VITE_PROJECT_ID`**：后端多租户/多项目隔离必填请求头来源。
- **`VITE_SSE_RECONNECT_*`**：前端 SSE 断线重连策略。

## 3. 后端部署（FastAPI）

### 3.1 Python 虚拟环境（强制）

项目约定使用仓库根目录的 `.venv`：

```bash
python -m venv .venv
```

运行任何 Python 命令时，推荐显式使用：

```bash
.venv/bin/python -V
```

### 3.2 安装依赖

本仓库使用 `pyproject.toml` 管理依赖。请使用你们团队约定的方式安装（例如 `pip`/`uv`/`poetry`）。

### 3.3 数据库迁移（Alembic）

后端使用 Alembic：`backend/alembic.ini`、`backend/migrations/`。

执行迁移（示例）：

```bash
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
```

### 3.4 启动后端服务

```bash
.venv/bin/python -m uvicorn gangqing.app.main:create_app --factory --host 127.0.0.1 --port 8000 --log-level info
```

健康检查（需要租户/项目请求头）：

```bash
curl -sS -H "X-Tenant-Id: t1" -H "X-Project-Id: p1" http://127.0.0.1:8000/api/v1/health
```

说明：后端 API 全局依赖 `build_request_context`，要求所有请求携带 `X-Tenant-Id` 与 `X-Project-Id` 请求头，否则返回 `AUTH_ERROR`。

## 4. 前端部署（Vite）

### 4.1 安装依赖

```bash
npm -C web install
```

### 4.2 本地开发启动

确保已配置 `web/.env.local` 的 `VITE_*` 后：

```bash
npm -C web run dev
```

### 4.3 构建产物

```bash
npm -C web run build
```

构建产物输出在：`web/dist/`。

### 4.4 静态部署

- 将 `web/dist/` 作为静态站点发布。
- 需要反向代理 `/api/v1/*` 到后端服务，或使用 `VITE_API_BASE_URL` 指向后端网关地址。

## 5. SSE（流式）相关部署注意

前端通过 `POST /api/v1/chat/stream` 建立 SSE 流式连接。部署时需确保：

- 反向代理支持 `text/event-stream`，并关闭对该路由的缓存/缓冲（否则会影响流式分片渲染）。
- 客户端可调用取消端点：`POST /api/v1/chat/stream/cancel`。

## 6. 验证（强制执行）

### 6.1 前端单元测试

```bash
npm -C web test
```

### 6.2 前端构建

```bash
npm -C web run build
```

### 6.3 后端 SSE E2E 冒烟测试（真实后端）

```bash
.venv/bin/python backend/scripts/web_sse_e2e_smoke_test.py
```

说明：该脚本会启动后端并验证：

- SSE 成功路径包含 `message.delta` 与 `final`
- 可控错误路径：缺少租户/项目 scope header 时返回结构化 `ErrorResponse`
