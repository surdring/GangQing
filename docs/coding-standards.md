---
trigger: always_on
---

# 全局编码规范

本文档定义仓库的通用编码标准与特定语言规范。当前主工程以 TypeScript（Node.js）为主；其他语言仅在需要时使用，且应遵循各自章节规范。

## 1. 通用原则 (General Principles)

### 1.1 命名与语义
- **变量名**: 应当是名词，清晰描述变量的内容（如 `userProfile`）。
- **函数名**: 应当是动词或动词短语，描述具体动作（如 `calculateTotal`, `fetchUserData`）。
- **布尔值**: 使用 `is`, `has`, `can` 等前缀（如 `isVisible`, `hasAccess`）。
- **避免缩写**: 除非是广泛通用的缩写（如 `ID`, `URL`, `API`），否则优先使用全拼。

### 1.2 注释规范

*   语言：
    *   文档注释 (Docstrings/JSDoc)：推荐使用 **中文** 描述业务逻辑，关键参数说明可辅助英文。
    *   行内注释：使用 **中文** 解释复杂的算法或业务决策。
    *   TODO/FIXME：使用英文，方便全局搜索（例：`// TODO: Refactor this later`）。
*   内容：注释应解释"为什么" (Why) 这么做，而不是"在做什么" (What)。

### 1.3 错误处理

*   错误消息：必须使用 **英文**，以便于日志搜索和通过 LLM 进行分析。
*   结构化错误：对外接口（REST/SSE/Streaming/Events）出现错误时，必须转换为结构化错误模型（例如 `AppError`）：
    *   `code`：稳定错误码（如 `VALIDATION_ERROR`/`AUTH_ERROR`/`UPSTREAM_TIMEOUT`/`CONTRACT_VIOLATION`/`GUARDRAIL_BLOCKED`）
    *   `message`：英文可读描述
    *   `details?`：结构化上下文（禁止放敏感信息）
    *   `retryable`：是否可重试
    *   `requestId`：用于链路追踪
*   上下文：错误产生处必须补充可定位上下文（如：业务实体 ID、操作名、失败阶段/stepId）。

### 1.4 契约与 Schema（强制）

*   单一事实源：所有输入/输出/配置/工具参数/事件模型/引用模型必须以 **Zod Schema** 作为单一事实源。
*   边界校验：
    *   API 入参（REST handler、SSE/streaming endpoint）必须 `schema.parse()`（或等价安全解析）后再进入业务逻辑。
    *   对外响应（尤其是 events/citations/evidence）必须在输出前通过 schema 断言，避免“看起来像对”的隐性契约漂移。
*   类型派生：TypeScript 类型应从 Zod schema 推导（`z.infer<typeof Schema>`），避免维护重复的 DTO 类型。

### 1.5 可观测性与上下文贯穿（强制）

*   RequestContext：需要统一并贯穿请求级上下文（至少包含 `requestId`, `tenantId`, `projectId?`）。
*   贯穿范围：
    *   后端入站（HTTP REST / SSE）
    *   模型调用 / 工具调用 / step events
    *   日志、指标与错误返回
*   结构化日志：日志字段至少包含：`requestId`, `tenantId`, `projectId`（可选）, `taskId/sessionId/stepId`（可选）。

### 1.6 代码提交 (Git)

*   使用 Conventional Commits 规范：
    *   `feat: ...` 新功能
    *   `fix: ...` 修复 Bug
    *   `docs: ...` 文档变更
    *   `refactor: ...` 代码重构（不改变逻辑）
    *   `chore: ...` 构建过程或辅助工具变动

### 1.7 隔离与权限上下文（强制）

*   必填上下文：对后端来说，`tenantId` 为必填；涉及资料范围/引用/证据链的请求必须包含 `projectId`（按产品策略决定是否允许可选）。
*   默认隔离：
    *   所有数据读写默认必须带 `tenantId` 过滤。
    *   检索、引用与证据链默认必须带 `projectId` 并限制在该 Project 范围内。
*   隔离违规处理：一旦检测到跨 `tenantId`/`projectId` 访问，必须返回结构化错误（如 `AUTH_ERROR`）并包含 `requestId`。

### 1.8 流式与事件协议（强制）

*   Streaming：流式输出必须遵循 **Vercel AI Data Stream Protocol**。
*   错误块：流式过程中发生错误时，必须返回可被前端识别的错误块，并可解析为 `AppError`（含 `code/message/retryable/requestId`）。
*   阶段/步骤标记：流中必须包含可供 UI 分段的结构化标记（阶段/步骤），以避免 UI 仅能按纯文本猜测。
*   取消语义：客户端断开/用户取消必须传播到后端，并取消底层模型请求。
*   TTFT：必须可观测首 Token 延迟（TTFT），并与 `requestId` 关联（日志或指标任一即可）。
*   Step Events：
    *   事件必须包含：`type`, `taskId`, `stepId`, `timestamp`, `requestId`, `payload`（以及需要时的 `stepName`）。
    *   `tool_called` 的参数摘要必须脱敏。
    *   `step_failed` 必须包含结构化错误（可解析为 `AppError`）。

---
## 2. TypeScript 规范

### 2.1 类型定义

*   优先使用 `interface`：除非需要联合类型 (`|`) 或映射类型，否则优先使用 `interface` 定义对象结构。
*   严格类型：
    *   所有函数参数和返回值必须有明确的类型注解。
    *   **禁止** 隐式 `any`。如果必须处理未知类型，使用 `unknown` 并配合类型守卫。
*   Zod 优先：对外契约（API 输入/输出、工具参数/返回、事件、引用、配置）必须先定义 Zod schema，并以 `z.infer` 推导 TypeScript 类型。
*   空值处理：优先使用可选链 `?.` 和空值合并 `??`。

### 2.2 命名约定

*   类名：PascalCase (例: `ArchitectureDesignEngine`)
*   接口名：以 `I` 开头 (例: `ILLMInterface`)
*   类型名：PascalCase (例: `ServiceArchitecture`)
*   枚举名：PascalCase (例: `ArchitectureType`)
*   函数/变量：camelCase (例: `designDataFlow`, `storageStrategies`)
*   常量：UPPER_SNAKE_CASE (例: `MAX_RETRIES`)
*   私有成员：以 `_` 开头 (例: `_cache`)

### 2.3 规范示例

```typescript
/**
 * 设计数据流和存储策略
 * 
 * @param services - 服务列表
 * @returns 数据流设计方案
 */
async designDataFlow(services: Service[]): Promise<DataFlowDesign> {
    try {
        const result = await this._llm.predict(services);
        return result;
    } catch (error) {
        // 英文错误信息，包含上下文
        throw new Error(`Failed to design data flow for ${services.length} services: ${error}`);
    }
}
```

### 2.4 文件组织

*   文件名：kebab-case (例: `architecture-design-engine.ts`)
*   导入顺序：
    1. Node.js 内置模块
    2. 第三方库 (`node_modules`)
    3. 项目绝对路径/别名引入
    4. 相对路径引入

---
## 3. Python 规范

### 3.1 代码风格

*   格式化：严格遵循 **PEP 8**。
*   工具：强制使用 `Black` 进行格式化，`isort` 管理导入，`Flake8` 或 `Ruff` 进行 Lint 检查。

### 3.2 类型提示 (Type Hints)

*   强制类型注解：Python 3.10+ 风格。
*   复杂类型：使用 `typing` 模块或内置集合类型。

```python
# ✅ 好 (Python 3.10+)
def process_items(items: list[str], config: dict[str, int] | None = None) -> int:
    ...
```

### 3.3 命名约定

*   类名：PascalCase (例: `DataProcessor`)
*   函数/变量/模块：snake_case (例: `calculate_metrics`, `user_id`)
*   常量：UPPER_SNAKE_CASE (例: `DEFAULT_TIMEOUT`)
*   私有成员：以 `_` 开头 (例: `_internal_helper`)

### 3.4 文档字符串 (Docstrings)

使用 **Google Style** 文档字符串。

```python
def fetch_user_data(user_id: int) -> dict[str, Any]:
    """获取用户的详细信息。

    Args:
        user_id: 用户的唯一标识符。

    Returns:
        包含用户属性的字典。

    Raises:
        ValueError: 当 user_id 无效时抛出。
    """
    ...
```

### 3.5 错误处理

使用 `try-except` 块，并尽量捕获具体的异常类型，避免裸露的 `except:`。

```python
try:
    data = json.loads(raw_response)

except json.JSONDecodeError as e:
    logger.error(f"Failed to decode JSON: {e}")
    raise DataParsingError("Invalid JSON format received") from e
```

---
## 4. Rust 规范

### 4.1 代码风格

*   工具：必须通过 `rustfmt` 格式化，必须通过 `clippy` 检查且无警告。
*   版本：使用 stable toolchain，除非有特殊说明。

### 4.2 命名约定

*   Struct/Enum/Trait：PascalCase (例: `TcpConnection`, `ComputeResult`)
*   函数/变量/模块：snake_case (例: `new_connection`, `process_data`)
*   常量/静态变量：UPPER_SNAKE_CASE (例: `GLOBAL_TIMEOUT`)
*   泛型参数：单大写字母或 PascalCase (例: `T`, `InputType`)

### 4.3 错误处理

*   Result vs Panic：库代码 **严禁** 使用 `panic!` 或 `unwrap()`。必须返回 `Result<T, E>`。
*   错误传播：优先使用 `?` 操作符。
*   自定义错误：使用 `thiserror` 定义库错误，`anyhow` 处理应用层错误。

```rust
use anyhow::{Context, Result};

/// 处理输入数据并返回结果
/// 
/// # Errors
/// 如果文件读取失败或格式错误，将返回错误
pub fn process_data_file(path: &str) -> Result<DataStruct> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read file: {}", path))?;
    
    let data: DataStruct = serde_json::from_str(&content)
        .context("Failed to parse JSON content")?;
        
    Ok(data)
}
```

### 4.4 最佳实践

*   所有权：优先使用借用 (`&T`) 而非克隆 (`.clone()`), 除非确有所有权转移需求。
*   模块化：保持 `lib.rs` 或 `main.rs` 简洁，将逻辑拆分到模块中。

---
## 5. Go (Golang) 规范

### 5.1 代码风格

*   工具：提交前必须执行 `gofmt` 或 `goimports`。
*   Linter：使用 `golangci-lint`。

### 5.2 命名约定

*   可见性：大写字母开头为 Exported (Public)，小写字母开头为 private。
*   风格：CamelCase (大驼峰或小驼峰)。**不要** 使用下划线 (snake_case)。
*   接口：通常以 `er` 结尾 (例: `Reader`, `Writer`, `Formatter`)。
*   变量名：惯用短命名 (例: `ctx` 而非 `context`, `err` 而非 `error`, `i` 循环索引)。

### 5.3 错误处理

*   检查错误：必须显式检查 `err != nil`。
*   错误包装：使用 `fmt.Errorf("...: %w", err)` 包装错误以保留堆栈/上下文。

```go
func (s *Service) LoadConfig(path string) (*Config, error) {
    f, err := os.Open(path)
    if err != nil {
        // 包含操作名称和原因
        return nil, fmt.Errorf("failed to open config file '%s': %w", path, err)
    }
    defer f.Close()
    
    // ... logic
}
```

### 5.4 项目结构

遵循 Standard Go Project Layout：

*   `/cmd`: 应用程序入口 (`main.go`)
*   `/pkg`: 可被外部导入的库代码
*   `/internal`: 私有应用程序代码 (强制隔离)

---
## 6. 通用最佳实践 (Cross-Language Best Practices)

### 6.1 避免魔法数字 (Magic Numbers)

直接在代码中使用数字会降低可读性和可维护性。

```typescript
// 不好
if (retries > 3) { ... }

// 好
const MAX_RETRIES = 3;
if (retries > MAX_RETRIES) { ... }
```

### 6.2 提前返回 (Early Return)

减少嵌套层级，使逻辑更清晰。

```python
# 不好
if user.is_active:
    if user.has_permission:
        do_something()
    else:
        return error
else:
    return error

# 好
if not user.is_active:
    return error
if not user.has_permission:
    return error

do_something()
```

### 6.3 变量命名语义化

避免单字母命名（循环变量 `i`, `j` 除外），变量名应体现其业务含义。

```rust
// 不好
let m = map.get("k");

// 好
let storage_strategy = strategy_map.get("PersistenceService");
```

### 6.4 契约测试与向后兼容（强制）

*   契约测试优先：对 streaming/events/citation/evidence 这类跨端契约，必须用自动化测试兜底（以 Zod schema parse 断言为准）。
*   只增不改：对外契约字段演进以“新增字段向后兼容”为默认策略；如必须破坏性变更，需要同时提供版本化策略（路径/header/schemaVersion 等）。

### 6.5 安全与合规（强制）

*   禁止伪造引用：引用（`citationId` 等）必须能映射回真实检索/深读结果；不可映射必须视为契约违规（如 `CONTRACT_VIOLATION`），不得“编造 citationId”。
*   事件脱敏：`tool_called` 等事件中的参数摘要必须脱敏，禁止直接输出敏感字段或大段原文。
*   Guardrails 语义：触发安全护栏阻断时，必须返回结构化错误（如 `GUARDRAIL_BLOCKED`），并设置 `retryable=false`。
