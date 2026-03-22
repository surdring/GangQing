# GangQing 自研 AI Copilot 核心组件技术方案
## 基于 CopilotKit 设计模式的工业级实现

---

## 文档元信息
- **版本**：v1.0
- **生成时间**：2026-02-26
- **适用阶段**：L1-L4
- **目标读者**：GangQing 开发团队、架构师
- **状态**：草案（待评审）

---

## 1. 方案概述

### 1.1 核心目标

**借鉴 CopilotKit 的优秀设计模式，自研符合 GangQing 工业场景强制约束的 AI Copilot 核心组件。**

### 1.2 设计原则

1. **安全第一**：只读默认、审计不可篡改、Kill Switch、OT 写入门禁
2. **证据驱动**：所有数值结论可追溯到数据源
3. **契约强制**：Zod/Pydantic 单一事实源，运行时校验
4. **多租户隔离**：tenantId/projectId 强制过滤
5. **可观测性**：requestId 全链路贯穿，结构化日志
6. **渐进式演进**：L1 只读查询 → L4 受控闭环

### 1.3 架构分层

```
┌─────────────────────────────────────────────────────────────┐ │ 前端层（React + TypeScript + Zod） │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ useGangQingChat Hook（借鉴 useCopilotChat） │ │ │ │ - SSE 客户端状态机 │ │ │ │ - 自动重连 + 错误处理 + 取消传播 │ │ │ │ - Zod schema 运行时校验 │ │ │ └─────────────────────────────────────────────────────┘ │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ Context Panel（证据链可视化） │ │ │ │ - Trust Pill（数值胶囊） │ │ │ │ - Evidence 展开与追溯 │ │ │ │ - 降级态表达（缺失/不可验证/冲突） │ │ │ └─────────────────────────────────────────────────────┘ │ └─────────────────────────────────────────────────────────────┘ ↓ SSE/WebSocket ┌─────────────────────────────────────────────────────────────┐ │ API 网关层（FastAPI + Pydantic） │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ RequestContext 自动注入（借鉴 CopilotKit） │ │ │ │ - 中间件提取 requestId/tenantId/projectId │ │ │ │ - 强制校验（缺失返回 AUTH_ERROR） │ │ │ │ - FastAPI Depends 依赖注入 │ │ │ └─────────────────────────────────────────────────────┘ │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ SSE Envelope 统一封装 │ │ │ │ - 强制字段（type/requestId/tenantId/sequence） │ │ │ │ - 结构化错误（error 事件同构 ErrorResponse） │ │ │ │ - 证据链增量（evidence.update） │ │ │ └─────────────────────────────────────────────────────┘ │ └─────────────────────────────────────────────────────────────┘ ↓ ┌─────────────────────────────────────────────────────────────┐ │ 编排层（Orchestration Engine） │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ 意图识别 + 策略路由 │ │ │ │ - QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE │ │ │ │ - 写操作倾向拦截（只读默认） │ │ │ └─────────────────────────────────────────────────────┘ │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ 工具链注册与调用（借鉴 useCopilotAction） │ │ │ │ - @tool 装饰器自动注册 │ │ │ │ - RBAC 门禁 + 脱敏 + 审计 │ │ │ │ - 超时重试 + 降级 │ │ │ └─────────────────────────────────────────────────────┘ │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ Evidence 引擎（GangQing 独有） │ │ │ │ - Citation/Lineage/ToolCallTrace 组装 │ │ │ │ - 增量更新（SSE evidence.update） │ │ │ │ - 降级规则（缺失/不可验证/冲突） │ │ │ └─────────────────────────────────────────────────────┘ │ └─────────────────────────────────────────────────────────────┘ ↓ ┌─────────────────────────────────────────────────────────────┐ │ 工具与适配层（Tools & Adapters） │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ Postgres 查询工具（只读） │ │ │ │ - 模板化 SQL + 仅 SELECT │ │ │ │ - 数据域过滤 + 字段脱敏 │ │ │ │ - Evidence 输出 │ │ │ └─────────────────────────────────────────────────────┘ │ │ ┌─────────────────────────────────────────────────────┐ │ │ │ ERP/MES/EAM 连接器（L2+） │ │ │ │ - 统一接口规范 │ │ │ │ - 超时重试 + 降级 │ │ │ │ - 审计 + Evidence │ │ │ └─────────────────────────────────────────────────────┘ │ └─────────────────────────────────────────────────────────────┘ ↓ ┌─────────────────────────────────────────────────────────────┐ │ 数据层 + 模型推理层 │ │ - Postgres（多租户隔离 + 审计 append-only） │ │ - llama.cpp（私有化部署 + 并发控制） │ │ - Elasticsearch（审计检索增强） │ └─────────────────────────────────────────────────────────────┘
```


---

## 2. 核心组件详细设计

### 2.1 前端：useGangQingChat Hook

#### 2.1.1 设计目标

**借鉴 CopilotKit 的 `useCopilotChat`，封装 SSE 复杂性，提供 React Hook 接口。**

#### 2.1.2 核心功能

- SSE 连接管理（连接/断开/重连）
- 事件解析与状态更新（message.delta/evidence.update/error/final）
- 自动重连（指数退避）
- 错误处理（结构化错误解析）
- 取消传播（客户端断开 → 服务端停止）
- Zod schema 运行时校验

#### 2.1.3 实现代码

```typescript
// web/src/hooks/useGangQingChat.ts

import { useState, useCallback, useRef, useEffect } from 'react';
import { z } from 'zod';

// ============ Schema 定义（单一事实源） ============

// SSE Envelope Schema
const SSEEnvelopeSchema = z.object({
  type: z.enum([
    'meta',
    'progress',
    'tool.call',
    'tool.result',
    'message.delta',
    'evidence.update',
    'warning',
    'error',
    'final'
  ]),
  timestamp: z.string(),
  requestId: z.string(),
  tenantId: z.string(),
  projectId: z.string(),
  sessionId: z.string().optional(),
  sequence: z.number(),
  payload: z.unknown() // 根据 type 动态解析
});

// ErrorResponse Schema
const ErrorResponseSchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
  retryable: z.boolean(),
  requestId: z.string()
});

// Evidence Schema
const EvidenceSchema = z.object({
  evidenceId: z.string(),
  sourceSystem: z.enum(['ERP', 'MES', 'DCS', 'EAM', 'LIMS', 'Manual', 'Detector']),
  sourceLocator: z.string(),
  timeRange: z.object({
    start: z.string(),
    end: z.string()
  }),
  toolCallId: z.string().optional(),
  lineageVersion: z.string().optional(),
  dataQualityScore: z.number().min(0).max(1).optional(),
  confidence: z.enum(['Low', 'Medium', 'High']),
  validation: z.enum(['verifiable', 'not_verifiable', 'out_of_bounds', 'mismatch']),
  redactions: z.record(z.unknown()).optional()
});

// ============ 类型推导 ============

type SSEEnvelope = z.infer<typeof SSEEnvelopeSchema>;
type ErrorResponse = z.infer<typeof ErrorResponseSchema>;
type Evidence = z.infer<typeof EvidenceSchema>;

// ============ 状态定义 ============

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface ChatState {
  status: 'idle' | 'connecting' | 'streaming' | 'error' | 'done';
  messages: ChatMessage[];
  evidence: Evidence[];
  currentMessage: string; // 当前流式消息缓冲
  error: ErrorResponse | null;
  requestId: string | null;
}

// ============ Hook 实现 ============

export function useGangQingChat(sessionId: string) {
  const [state, setState] = useState<ChatState>({
    status: 'idle',
    messages: [],
    evidence: [],
    currentMessage: '',
    error: null,
    requestId: null
  });

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const maxRetries = 3;
  const baseRetryDelay = 1000; // 1秒

  // ============ SSE 连接 ============

  const connect = useCallback((query: string) => {
    setState(s => ({ ...s, status: 'connecting', error: null }));

    const url = new URL('/api/v1/chat/stream', window.location.origin);
    url.searchParams.set('sessionId', sessionId);
    url.searchParams.set('query', query);

    const eventSource = new EventSource(url.toString());
    eventSourceRef.current = eventSource;

    // ============ 事件处理 ============

    eventSource.addEventListener('message', (e) => {
      try {
        // 1. 解析 SSE Envelope
        const envelope = SSEEnvelopeSchema.parse(JSON.parse(e.data));

        // 2. 更新 requestId
        if (!state.requestId) {
          setState(s => ({ ...s, requestId: envelope.requestId }));
        }

        // 3. 根据事件类型处理
        switch (envelope.type) {
          case 'meta':
            setState(s => ({ ...s, status: 'streaming' }));
            break;

          case 'progress':
            // 可选：显示进度提示
            console.log('[Progress]', envelope.payload);
            break;

          case 'tool.call':
            // 可选：显示工具调用提示
            console.log('[Tool Call]', envelope.payload);
            break;

          case 'tool.result':
            // 可选：显示工具结果提示
            console.log('[Tool Result]', envelope.payload);
            break;

          case 'message.delta':
            // 增量渲染消息
            const delta = (envelope.payload as any).delta as string;
            setState(s => ({
              ...s,
              currentMessage: s.currentMessage + delta
            }));
            break;

          case 'evidence.update':
            // 更新证据链
            const evidencePayload = envelope.payload as any;
            if (evidencePayload.mode === 'append' && evidencePayload.evidence) {
              const evidence = EvidenceSchema.parse(evidencePayload.evidence);
              setState(s => ({
                ...s,
                evidence: [...s.evidence, evidence]
              }));
            } else if (evidencePayload.mode === 'update' && evidencePayload.evidence) {
              const evidence = EvidenceSchema.parse(evidencePayload.evidence);
              setState(s => ({
                ...s,
                evidence: s.evidence.map(e =>
                  e.evidenceId === evidence.evidenceId ? evidence : e
                )
              }));
            }
            break;

          case 'warning':
            // 可选：显示警告提示
            console.warn('[Warning]', envelope.payload);
            break;

          case 'error':
            // 解析结构化错误
            const error = ErrorResponseSchema.parse(envelope.payload);
            setState(s => ({
              ...s,
              status: 'error',
              error
            }));
            break;

          case 'final':
            // 结束流式输出
            setState(s => ({
              ...s,
              status: 'done',
              messages: [
                ...s.messages,
                {
                  id: envelope.requestId,
                  role: 'assistant',
                  content: s.currentMessage,
                  timestamp: envelope.timestamp
                }
              ],
              currentMessage: ''
            }));
            eventSource.close();
            retryCountRef.current = 0; // 重置重试计数
            break;
        }
      } catch (err) {
        console.error('[SSE Parse Error]', err);
        setState(s => ({
          ...s,
          status: 'error',
          error: {
            code: 'CLIENT_PARSE_ERROR',
            message: 'Failed to parse SSE event',
            retryable: false,
            requestId: state.requestId || 'unknown'
          }
        }));
      }
    });

    // ============ 错误处理与重连 ============

    eventSource.onerror = () => {
      console.error('[SSE Error] Connection failed');
      eventSource.close();

      if (retryCountRef.current < maxRetries) {
        // 指数退避重连
        const delay = baseRetryDelay * Math.pow(2, retryCountRef.current);
        retryCountRef.current++;

        console.log(`[SSE Retry] Attempt ${retryCountRef.current}/${maxRetries} in ${delay}ms`);

        setTimeout(() => {
          connect(query);
        }, delay);
      } else {
        // 超过最大重试次数
        setState(s => ({
          ...s,
          status: 'error',
          error: {
            code: 'CONNECTION_FAILED',
            message: 'Failed to connect after multiple retries',
            retryable: false,
            requestId: state.requestId || 'unknown'
          }
        }));
      }
    };
  }, [sessionId, state.requestId]);

  // ============ 取消 ============

  const cancel = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setState(s => ({ ...s, status: 'idle' }));
    }
  }, []);

  // ============ 发送消息 ============

  const sendMessage = useCallback((content: string) => {
    // 添加用户消息到历史
    setState(s => ({
      ...s,
      messages: [
        ...s.messages,
        {
          id: `user-${Date.now()}`,
          role: 'user',
          content,
          timestamp: new Date().toISOString()
        }
      ]
    }));

    // 建立 SSE 连接
    connect(content);
  }, [connect]);

  // ============ 清理 ============

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return {
    state,
    sendMessage,
    cancel,
    retry: () => {
      if (state.messages.length > 0) {
        const lastUserMessage = [...state.messages]
          .reverse()
          .find(m => m.role === 'user');
        if (lastUserMessage) {
          retryCountRef.current = 0;
          connect(lastUserMessage.content);
        }
      }
    }
  };
}
```

#### 2.1.4 使用示例

```typescript
// web/src/components/ChatInterface.tsx

import React from 'react';
import { useGangQingChat } from '../hooks/useGangQingChat';

export function ChatInterface({ sessionId }: { sessionId: string }) {
  const { state, sendMessage, cancel } = useGangQingChat(sessionId);
  const [input, setInput] = React.useState('');

  const handleSend = () => {
    if (input.trim()) {
      sendMessage(input);
      setInput('');
    }
  };

  return (
    <div className="chat-interface">
      {/* 消息列表 */}
      <div className="messages">
        {state.messages.map(msg => (
          <div key={msg.id} className={`message ${msg.role}`}>
            {msg.content}
          </div>
        ))}

        {/* 流式消息 */}
        {state.currentMessage && (
          <div className="message assistant streaming">
            {state.currentMessage}
          </div>
        )}

        {/* 错误提示 */}
        {state.error && (
          <div className="error">
            <strong>{state.error.code}</strong>: {state.error.message}
            {state.error.retryable && (
              <button onClick={() => retry()}>重试</button>
            )}
          </div>
        )}
      </div>

      {/* 输入框 */}
      <div className="input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSend()}
          disabled={state.status === 'streaming'}
        />
        <button onClick={handleSend} disabled={state.status === 'streaming'}>
          发送
        </button>
        {state.status === 'streaming' && (
          <button onClick={cancel}>取消</button>
        )}
      </div>

      {/* 证据链面板 */}
      <div className="evidence-panel">
        <h3>证据链 ({state.evidence.length})</h3>
        {state.evidence.map(ev => (
          <div key={ev.evidenceId} className="evidence-item">
            <span className="source">{ev.sourceSystem}</span>
            <span className="confidence">{ev.confidence}</span>
            <span className="validation">{ev.validation}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```
2.2 后端：RequestContext 自动注入
2.2.1 设计目标
借鉴 CopilotKit 的上下文管理，使用 FastAPI Depends 实现自动注入，强制校验 tenantId/projectId。

2.2.2 核心功能
中间件提取请求头（X-Request-Id/X-Tenant-Id/X-Project-Id）
强制校验（缺失返回 AUTH_ERROR）
依赖注入（FastAPI Depends）
全链路贯穿（HTTP → 编排 → 工具 → 审计）
2.2.3 实现代码
```py
# backend/gangqing/core/context.py

from dataclasses import dataclass
from typing import Optional
from fastapi import Request, HTTPException, status
from uuid import uuid4

@dataclass
class RequestContext:
    """请求上下文（贯穿全链路）"""
    request_id: str
    tenant_id: str
    project_id: str
    user_id: str
    role: str
    session_id: Optional[str] = None
    
    @classmethod
    def from_request(cls, request: Request) -> "RequestContext":
        """从请求头提取并校验上下文"""
        
        # 1. 提取 requestId（未传入则生成）
        request_id = request.headers.get("X-Request-Id")
        if not request_id:
            request_id = f"req-{uuid4().hex[:12]}"
        
        # 2. 提取 tenantId（强制）
        tenant_id = request.headers.get("X-Tenant-Id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AUTH_ERROR",
                    "message": "Missing X-Tenant-Id header",
                    "retryable": False,
                    "requestId": request_id
                }
            )
        
        # 3. 提取 projectId（强制）
        project_id = request.headers.get("X-Project-Id")
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AUTH_ERROR",
                    "message": "Missing X-Project-Id header",
                    "retryable": False,
                    "requestId": request_id
                }
            )
        
        # 4. 提取用户信息（从 JWT 或其他认证机制）
        # TODO: 实际实现需要从 JWT 解析
        user_id = request.headers.get("X-User-Id", "unknown")
        role = request.headers.get("X-User-Role", "guest")
        
        # 5. 可选：sessionId
        session_id = request.headers.get("X-Session-Id")
        
        return cls(
            request_id=request_id,
            tenant_id=tenant_id,
            project_id=project_id,
            user_id=user_id,
            role=role,
            session_id=session_id
        )
    
    def to_dict(self) -> dict:
        """转换为字典（用于日志/审计）"""
        return {
            "requestId": self.request_id,
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "userId": self.user_id,
            "role": self.role,
            "sessionId": self.session_id
        }


# ============ FastAPI Depends ============

async def get_request_context(request: Request) -> RequestContext:
    """依赖注入：自动提取并校验请求上下文"""
    return RequestContext.from_request(request)
```

#### 2.2.4 使用示例
```py
# backend/gangqing/api/chat.py

from fastapi import APIRouter, Depends
from gangqing.core.context import RequestContext, get_request_context
from gangqing.schemas.chat import QueryRequest, QueryResponse

router = APIRouter()

@router.post("/api/v1/chat")
async def chat(
    query: QueryRequest,
    ctx: RequestContext = Depends(get_request_context)  # 自动注入
):
    """对话接口（非流式）"""
    
    # 上下文已自动注入，无需手动提取
    # ctx.request_id / ctx.tenant_id / ctx.project_id 可直接使用
    
    # 调用编排层
    result = await orchestrator.process(ctx, query)
    
    return QueryResponse(
        requestId=ctx.request_id,
        sessionId=ctx.session_id,
        assistantMessage=result.message,
        evidenceChain=result.evidence
    )
```
### 2.3 后端：工具装饰器自动注册
2.3.1 设计目标
借鉴 CopilotKit 的 useCopilotAction，使用装饰器简化工具注册，自动化 RBAC/脱敏/审计。

2.3.2 核心功能
装饰器声明工具元信息（name/description/capabilities/masking_policy）
自动注册到工具注册表
自动 RBAC 检查（基于 capabilities）
自动数据域过滤（基于 ctx.tenant_id/project_id）
自动脱敏（基于 masking_policy）
自动审计（tool.call/tool.result）
自动 Evidence 生成
2.3.3 实现代码

```py
# backend/gangqing/tools/decorators.py

from typing import Callable, List, Optional, Any
from functools import wraps
from pydantic import BaseModel
from gangqing.core.context import RequestContext
from gangqing.core.rbac import check_capabilities
from gangqing.core.masking import apply_masking
from gangqing.core.audit import log_tool_call
from gangqing.core.evidence import generate_evidence

class ToolRegistry:
    """工具注册表（单例）"""
    _instance = None
    _tools = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, tool: Callable):
        """注册工具"""
        self._tools[name] = tool
    
    def get(self, name: str) -> Optional[Callable]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """列出所有工具"""
        return list(self._tools.keys())


# ============ 装饰器 ============

def tool(
    name: str,
    description: str,
    capabilities: List[str],
    masking_policy: str = "none",
    timeout_seconds: int = 30,
    max_retries: int = 3
):
    """
    工具装饰器
    
    Args:
        name: 工具名称
        description: 工具描述
        capabilities: RBAC 能力点列表（例如 ["kpi:read:cost"]）
        masking_policy: 脱敏策略（none/role_based/strict）
        timeout_seconds: 超时时间（秒）
        max_retries: 最大重试次数
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(ctx: RequestContext, params: BaseModel) -> Any:
            tool_call_id = f"tc-{uuid4().hex[:12]}"
            
            # 1. RBAC 检查
            if not check_capabilities(ctx.role, capabilities):
                raise PermissionError(
                    f"Role '{ctx.role}' lacks required capabilities: {capabilities}"
                )
            
            # 2. 记录审计（tool.call）
            await log_tool_call(
                ctx=ctx,
                tool_call_id=tool_call_id,
                tool_name=name,
                params_summary=params.dict(exclude_unset=True)  # 脱敏
            )
            
            try:
                # 3. 执行工具（带超时）
                result = await asyncio.wait_for(
                    func(ctx, params),
                    timeout=timeout_seconds
                )
                
                # 4. 脱敏输出
                masked_result = apply_masking(
                    data=result,
                    policy=masking_policy,
                    role=ctx.role
                )
                
                # 5. 生成 Evidence
                evidence = generate_evidence(
                    ctx=ctx,
                    tool_call_id=tool_call_id,
                    tool_name=name,
                    result=masked_result
                )
                
                # 6. 记录审计（tool.result success）
                await log_tool_result(
                    ctx=ctx,
                    tool_call_id=tool_call_id,
                    status="success",
                    evidence_id=evidence.evidence_id
                )
                
                return {
                    "result": masked_result,
                    "evidence": evidence
                }
                
            except asyncio.TimeoutError:
                # 超时错误
                await log_tool_result(
                    ctx=ctx,
                    tool_call_id=tool_call_id,
                    status="failure",
                    error_code="UPSTREAM_TIMEOUT"
                )
                raise
            
            except Exception as e:
                # 其他错误
                await log_tool_result(
                    ctx=ctx,
                    tool_call_id=tool_call_id,
                    status="failure",
                    error_code="TOOL_EXECUTION_ERROR"
                )
                raise
        
                # 注册到工具注册表
        registry = ToolRegistry()
        registry.register(name, wrapper)
        
        # 保存元信息（用于文档生成）
        wrapper._tool_metadata = {
            "name": name,
            "description": description,
            "capabilities": capabilities,
            "masking_policy": masking_policy,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries
        }
        
        return wrapper
    
    return decorator

```
#### 2.3.4 使用示例
```py
# backend/gangqing/tools/cost_query.py

from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from gangqing.tools.decorators import tool
from gangqing.core.context import RequestContext

# ============ 参数 Schema（Pydantic 单一事实源） ============

class TimeRange(BaseModel):
    start: datetime
    end: datetime

class QueryCostParams(BaseModel):
    time_range: TimeRange
    equipment_ids: Optional[List[str]] = None
    cost_types: Optional[List[str]] = None  # 原料/能耗/人工/折旧

# ============ 工具定义 ============

@tool(
    name="query_cost",
    description="查询成本数据（只读）",
    capabilities=["kpi:read:cost"],
    masking_policy="role_based",
    timeout_seconds=30
)
async def query_cost(
    ctx: RequestContext,
    params: QueryCostParams
) -> dict:
    """
    查询成本数据
    
    自动化能力：
    - RBAC 检查（基于 capabilities）
    - 数据域过滤（基于 ctx.tenant_id/project_id）
    - 脱敏输出（基于 masking_policy）
    - 审计记录（tool.call/tool.result）
    - Evidence 生成
    """
    
    # 1. 构建查询（自动叠加数据域过滤）
    query = f"""
        SELECT 
            date,
            equipment_id,
            cost_type,
            amount,
            unit
        FROM fact_cost_daily
        WHERE tenant_id = :tenant_id
          AND project_id = :project_id
          AND date BETWEEN :start AND :end
    """
    
    if params.equipment_ids:
        query += " AND equipment_id = ANY(:equipment_ids)"
    
    if params.cost_types:
        query += " AND cost_type = ANY(:cost_types)"
    
    # 2. 执行查询
    async with get_db_session() as session:
        result = await session.execute(
            query,
            {
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "start": params.time_range.start,
                "end": params.time_range.end,
                "equipment_ids": params.equipment_ids,
                "cost_types": params.cost_types
            }
        )
        rows = result.fetchall()
    
    # 3. 返回结果（装饰器会自动脱敏 + 生成 Evidence）
    return {
        "total_records": len(rows),
        "data": [
            {
                "date": row.date.isoformat(),
                "equipment_id": row.equipment_id,
                "cost_type": row.cost_type,
                "amount": float(row.amount),
                "unit": row.unit
            }
            for row in rows
        ],
        "time_range": {
            "start": params.time_range.start.isoformat(),
            "end": params.time_range.end.isoformat()
        }
    }

```
### 2.4 后端：Evidence 引擎
2.4.1 设计目标
GangQing 独有能力，所有数值结论必须可追溯到数据源。

2.4.2 核心功能
Citation（数据源引用）
Lineage（指标口径版本）
ToolCallTrace（工具调用轨迹）
增量更新（SSE evidence.update）
降级规则（缺失/不可验证/冲突）
2.4.3 实现代码
```py
# backend/gangqing/core/evidence.py

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from enum import Enum

class SourceSystem(str, Enum):
    ERP = "ERP"
    MES = "MES"
    DCS = "DCS"
    EAM = "EAM"
    LIMS = "LIMS"
    MANUAL = "Manual"
    DETECTOR = "Detector"

class Confidence(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

class Validation(str, Enum):
    VERIFIABLE = "verifiable"
    NOT_VERIFIABLE = "not_verifiable"
    OUT_OF_BOUNDS = "out_of_bounds"
    MISMATCH = "mismatch"

@dataclass
class TimeRange:
    start: datetime
    end: datetime

@dataclass
class Evidence:
    """证据链对象"""
    evidence_id: str
    source_system: SourceSystem
    source_locator: str  # 表名/接口名/文档路径
    time_range: TimeRange
    tool_call_id: Optional[str] = None
    lineage_version: Optional[str] = None
    data_quality_score: Optional[float] = None
    confidence: Confidence = Confidence.MEDIUM
    validation: Validation = Validation.VERIFIABLE
    redactions: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """转换为字典（用于 SSE 输出）"""
        return {
            "evidenceId": self.evidence_id,
            "sourceSystem": self.source_system.value,
            "sourceLocator": self.source_locator,
            "timeRange": {
                "start": self.time_range.start.isoformat(),
                "end": self.time_range.end.isoformat()
            },
            "toolCallId": self.tool_call_id,
            "lineageVersion": self.lineage_version,
            "dataQualityScore": self.data_quality_score,
            "confidence": self.confidence.value,
            "validation": self.validation.value,
            "redactions": self.redactions
        }


# ============ Evidence 生成器 ============

def generate_evidence(
    ctx: RequestContext,
    tool_call_id: str,
    tool_name: str,
    result: dict
) -> Evidence:
    """
    自动生成 Evidence
    
    规则：
    - 从工具结果中提取数据源信息
    - 计算数据质量评分
    - 判断置信度与验证状态
    """
    
    # 1. 生成 evidenceId
    evidence_id = f"ev-{uuid4().hex[:12]}"
    
    # 2. 提取数据源信息
    source_system = _infer_source_system(tool_name)
    source_locator = _extract_source_locator(result)
    
    # 3. 提取时间范围
    time_range = _extract_time_range(result)
    
    # 4. 计算数据质量评分
    data_quality_score = _calculate_data_quality(result)
    
    # 5. 判断置信度
    confidence = _determine_confidence(data_quality_score, result)
    
    # 6. 判断验证状态
    validation = _determine_validation(result)
    
    # 7. 提取脱敏信息
    redactions = result.get("_redactions")
    
    return Evidence(
        evidence_id=evidence_id,
        source_system=source_system,
        source_locator=source_locator,
        time_range=time_range,
        tool_call_id=tool_call_id,
        lineage_version=result.get("lineage_version"),
        data_quality_score=data_quality_score,
        confidence=confidence,
        validation=validation,
        redactions=redactions
    )


# ============ 辅助函数 ============

def _infer_source_system(tool_name: str) -> SourceSystem:
    """从工具名推断数据源系统"""
    if "cost" in tool_name or "finance" in tool_name:
        return SourceSystem.ERP
    elif "production" in tool_name:
        return SourceSystem.MES
    elif "dcs" in tool_name or "realtime" in tool_name:
        return SourceSystem.DCS
    elif "maintenance" in tool_name or "eam" in tool_name:
        return SourceSystem.EAM
    else:
        return SourceSystem.MANUAL

def _extract_source_locator(result: dict) -> str:
    """提取数据源定位信息"""
    # 优先从结果中提取
    if "_source_table" in result:
        return result["_source_table"]
    elif "_source_api" in result:
        return result["_source_api"]
    else:
        return "unknown"

def _extract_time_range(result: dict) -> TimeRange:
    """提取时间范围"""
    if "time_range" in result:
        return TimeRange(
            start=datetime.fromisoformat(result["time_range"]["start"]),
            end=datetime.fromisoformat(result["time_range"]["end"])
        )
    else:
        # 默认使用当前时间
        now = datetime.utcnow()
        return TimeRange(start=now, end=now)

def _calculate_data_quality(result: dict) -> float:
    """计算数据质量评分（0-1）"""
    # 简化实现：基于缺失率
    if "data" in result and isinstance(result["data"], list):
        total = len(result["data"])
        if total == 0:
            return 0.0
        
        # 计算缺失字段数量
        missing_count = sum(
            1 for row in result["data"]
            if any(v is None for v in row.values())
        )
        
        return 1.0 - (missing_count / total)
    
    return 1.0  # 默认满分

def _determine_confidence(data_quality_score: float, result: dict) -> Confidence:
    """判断置信度"""
    if data_quality_score >= 0.9:
        return Confidence.HIGH
    elif data_quality_score >= 0.7:
        return Confidence.MEDIUM
    else:
        return Confidence.LOW

def _determine_validation(result: dict) -> Validation:
    """判断验证状态"""
    # 检查是否有数据源
    if "_source_table" not in result and "_source_api" not in result:
        return Validation.NOT_VERIFIABLE
    
    # 检查是否越界（需要配置边界规则）
    if "_out_of_bounds" in result and result["_out_of_bounds"]:
        return Validation.OUT_OF_BOUNDS
    
    # 检查是否冲突
    if "_conflict" in result and result["_conflict"]:
        return Validation.MISMATCH
    
    return Validation.VERIFIABLE

```
### 2.5 后端：SSE Envelope 统一封装
2.5.1 设计目标
统一 SSE 事件格式，强制字段（requestId/tenantId/projectId/sequence），便于审计与追溯。

2.5.2 核心功能
统一 Envelope 结构
自动注入上下文字段
序列号自动递增
结构化错误同构
2.5.3 实现代码
```py
# backend/gangqing/core/sse.py

from typing import Any, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class SSEEventType(str, Enum):
    META = "meta"
    PROGRESS = "progress"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    MESSAGE_DELTA = "message.delta"
    EVIDENCE_UPDATE = "evidence.update"
    WARNING = "warning"
    ERROR = "error"
    FINAL = "final"

@dataclass
class SSEEnvelope:
    """SSE 事件 Envelope"""
    type: SSEEventType
    timestamp: datetime
    request_id: str
    tenant_id: str
    project_id: str
    session_id: Optional[str]
    sequence: int
    payload: Any
    
    def to_sse_event(self) -> str:
        """转换为 SSE 事件格式（单行 JSON）"""
        import json
        
        data = {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "requestId": self.request_id,
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "sessionId": self.session_id,
            "sequence": self.sequence,
            "payload": self.payload
        }
        
        # 单行 JSON（SSE 要求）
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============ SSE 流生成器 ============

class SSEStreamBuilder:
    """SSE 流构建器"""
    
    def __init__(self, ctx: RequestContext):
        self.ctx = ctx
        self.sequence = 0
    
    def _next_sequence(self) -> int:
        """获取下一个序列号"""
        self.sequence += 1
        return self.sequence
    
    def emit(self, event_type: SSEEventType, payload: Any) -> str:
        """发送事件"""
        envelope = SSEEnvelope(
            type=event_type,
            timestamp=datetime.utcnow(),
            request_id=self.ctx.request_id,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
            session_id=self.ctx.session_id,
            sequence=self._next_sequence(),
            payload=payload
        )
        return envelope.to_sse_event()
    
    def emit_meta(self, capabilities: dict) -> str:
        """发送 meta 事件（首事件）"""
        return self.emit(SSEEventType.META, {
            "capabilities": capabilities
        })
    
    def emit_progress(self, stage: str, message: str) -> str:
        """发送 progress 事件"""
        return self.emit(SSEEventType.PROGRESS, {
            "stage": stage,
            "message": message
        })
    
    def emit_tool_call(self, tool_call_id: str, tool_name: str, args_summary: dict) -> str:
        """发送 tool.call 事件"""
        return self.emit(SSEEventType.TOOL_CALL, {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "argsSummary": args_summary
        })
    
    def emit_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        status: str,
        result_summary: Optional[dict] = None,
        error: Optional[dict] = None,
        evidence_refs: Optional[List[str]] = None
    ) -> str:
        """发送 tool.result 事件"""
        payload = {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "status": status
        }
        
        if result_summary:
            payload["resultSummary"] = result_summary
        
        if error:
            payload["error"] = error
        
        if evidence_refs:
            payload["evidenceRefs"] = evidence_refs
        
        return self.emit(SSEEventType.TOOL_RESULT, payload)
    
    def emit_message_delta(self, delta: str) -> str:
        """发送 message.delta 事件"""
        return self.emit(SSEEventType.MESSAGE_DELTA, {
            "delta": delta
        })
    
    def emit_evidence_update(
        self,
        mode: str,
        evidence: Optional[Evidence] = None,
        evidence_id: Optional[str] = None
    ) -> str:
        """发送 evidence.update 事件"""
        payload = {"mode": mode}
        
        if evidence:
            payload["evidence"] = evidence.to_dict()
        
        if evidence_id:
            payload["evidenceId"] = evidence_id
        
        return self.emit(SSEEventType.EVIDENCE_UPDATE, payload)
    
    def emit_warning(self, code: str, message: str, details: Optional[dict] = None) -> str:
        """发送 warning 事件"""
        payload = {
            "code": code,
            "message": message
        }
        
        if details:
            payload["details"] = details
        
        return self.emit(SSEEventType.WARNING, payload)
    
    def emit_error(self, error: dict) -> str:
        """发送 error 事件（同构 ErrorResponse）"""
        return self.emit(SSEEventType.ERROR, error)
    
    def emit_final(self, status: str, summary: Optional[dict] = None) -> str:
        """发送 final 事件（最后一个事件）"""
        payload = {"status": status}
        
        if summary:
            payload["summary"] = summary
        
        return self.emit(SSEEventType.FINAL, payload)

```
### 2.5.4 使用示例
```py
# backend/gangqing/api/chat_stream.py

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from gangqing.core.context import RequestContext, get_request_context
from gangqing.core.sse import SSEStreamBuilder

router = APIRouter()

@router.get("/api/v1/chat/stream")
async def chat_stream(
    sessionId: str,
    query: str,
    ctx: RequestContext = Depends(get_request_context)
):
    """对话流式接口（SSE）"""
    
    async def event_generator():
        builder = SSEStreamBuilder(ctx)
        
        try:
            # 1. 发送 meta 事件（首事件）
            yield builder.emit_meta({
                "streaming": True,
                "evidenceIncremental": True,
                "cancellationSupported": True
            })
            
            # 2. 发送 progress 事件
            yield builder.emit_progress("intent", "识别意图中...")
            
            # 3. 意图识别
            intent = await identify_intent(ctx, query)
            
            # 4. 发送 progress 事件
            yield builder.emit_progress("tooling", "调用工具中...")
            
            # 5. 工具调用
            tool_call_id = "tc-123"
            yield builder.emit_tool_call(
                tool_call_id=tool_call_id,
                tool_name="query_cost",
                args_summary={"time_range": "2026-02-01~2026-02-28"}
            )
            
            # 6. 执行工具
            tool_result = await execute_tool(ctx, "query_cost", {...})
            
            # 7. 发送 tool.result 事件
            yield builder.emit_tool_result(
                tool_call_id=tool_call_id,
                tool_name="query_cost",
                status="success",
                evidence_refs=[tool_result["evidence"].evidence_id]
            )
            
            # 8. 发送 evidence.update 事件
            yield builder.emit_evidence_update(
                mode="append",
                evidence=tool_result["evidence"]
            )
            
            # 9. 生成回答（流式）
            async for delta in generate_answer(ctx, tool_result):
                yield builder.emit_message_delta(delta)
            
            # 10. 发送 final 事件
            yield builder.emit_final("success")
            
        except Exception as e:
            # 发送 error 事件
            yield builder.emit_error({
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "retryable": False,
                "requestId": ctx.request_id
            })
            
            # 发送 final 事件
            yield builder.emit_final("error")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

```
### 
2.6 后端：只读默认门禁
2.6.1 设计目标
GangQing 安全红线，写操作必须草案→审批→执行→回滚。

2.6.2 核心功能
意图识别（QUERY/ANALYZE/ACTION_PREPARE/ACTION_EXECUTE）
写操作拦截（返回 GUARDRAIL_BLOCKED）
草案生成（不执行）
审批流程（多签）
受控执行（Kill Switch + 白名单）
回滚机制
2.6.3 实现代码

```py
# backend/gangqing/core/guardrails.py

from enum import Enum
from typing import Optional

class Intent(str, Enum):
    QUERY = "QUERY"
    ANALYZE = "ANALYZE"
    ALERT = "ALERT"
    ACTION_PREPARE = "ACTION_PREPARE"
    ACTION_EXECUTE = "ACTION_EXECUTE"

class GuardrailEngine:
    """只读默认门禁引擎"""
    
    def __init__(self):
        self.kill_switch_enabled = False  # 从配置加载
    
    async def check_intent(
        self,
        ctx: RequestContext,
        intent: Intent,
        target_resource: Optional[str] = None
    ) -> dict:
        """
        检查意图是否允许执行
        
        Returns:
            {
                "allowed": bool,
                "reason": str,
                "error_code": str,
                "alternative": str  # 替代方案
            }
        """
        
        # 1. 只读意图：直接放行
        if intent in [Intent.QUERY, Intent.ANALYZE, Intent.ALERT]:
            return {
                "allowed": True,
                "reason": "Read-only intent",
                "error_code": None,
                "alternative": None
            }
        
        # 2. 草案生成：允许（不执行）
        if intent == Intent.ACTION_PREPARE:
            return {
                "allowed": True,
                "reason": "Draft generation allowed",
                "error_code": None,
                "alternative": None
            }
        
        # 3. 写操作执行：严格检查
        if intent == Intent.ACTION_EXECUTE:
            # 3.1 检查 Kill Switch
            if self.kill_switch_enabled:
                return {
                    "allowed": False,
                    "reason": "Kill Switch is enabled",
                    "error_code": "GUARDRAIL_BLOCKED",
                    "alternative": "请联系管理员关闭熔断开关"
                }
            
            # 3.2 检查权限
            if not await self._check_write_permission(ctx):
                return {
                    "allowed": False,
                    "reason": "Insufficient write permission",
                    "error_code": "FORBIDDEN",
                    "alternative": "请申请写操作权限"
                }
            
            # 3.3 检查审批状态
            approval_status = await self._check_approval_status(ctx, target_resource)
            if approval_status != "approved":
                return {
                    "allowed": False,
                    "reason": f"Approval status is {approval_status}",
                    "error_code": "GUARDRAIL_BLOCKED",
                    "alternative": "请先提交审批并等待批准"
                }
            
            # 3.4 检查白名单
            if not await self._check_whitelist(ctx, target_resource):
                return {
                    "allowed": False,
                    "reason": "Resource not in whitelist",
                    "error_code": "GUARDRAIL_BLOCKED",
                    "alternative": "目标资源不在允许范围内"
                }
            
            # 3.5 所有检查通过
            return {
                "allowed": True,
                "reason": "All checks passed",
                "error_code": None,
                "alternative": None
            }
        
        # 4. 未知意图：拒绝
        return {
            "allowed": False,
            "reason": "Unknown intent",
            "error_code": "VALIDATION_ERROR",
            "alternative": "请明确操作意图"
        }
    
    async def _check_write_permission(self, ctx: RequestContext) -> bool:
        """检查写权限"""
        # 从 RBAC 系统检查
        return await check_capabilities(ctx.role, ["execution:execute:it"])
    
    async def _check_approval_status(
        self,
        ctx: RequestContext,
        target_resource: Optional[str]
    ) -> str:
        """检查审批状态"""
        # 从审批系统查询
        # 返回：pending/approved/rejected/expired
        return "pending"  # 示例
    
    async def _check_whitelist(
        self,
        ctx: RequestContext,
        target_resource: Optional[str]
    ) -> bool:
        """检查白名单"""
        # 从配置或数据库查询
        return False  # 示例

```
3. 实施路线图
3.1 Phase 1：核心组件落地（L1，4-6 周）
目标
完成核心组件的自研实现，替换现有手动传参/硬编码模式。

任务清单
| 任务 | 组件 | 工作量 | 依赖 | 验收标准 | |------|------|--------|------|---------| | T1.1 | 前端 useGangQingChat Hook | 3天 | 无 | SSE 连接/重连/错误处理/取消传播 | | T1.2 | 前端 Context Panel 强化 | 2天 | T1.1 | Evidence 展示/降级态表达 | | T1.3 | 后端 RequestContext 依赖注入 | 2天 | 无 | 自动提取/强制校验/全链路贯穿 | | T1.4 | 后端工具装饰器 | 5天 | T1.3 | 自动注册/RBAC/脱敏/审计 | | T1.5 | Evidence 引擎 | 5天 | T1.4 | Citation/Lineage/增量更新 | | T1.6 | SSE Envelope 封装 | 3天 | T1.3 | 统一格式/强制字段/序列号 | | T1.7 | 只读默认门禁 | 4天 | T1.4 | 意图识别/拦截/审计 | | T1.8 | 集成测试 | 3天 | 全部 | 端到端流程验证 |

总工作量：约 27 人天（4-6 周，2-3 人并行）

验收标准
✅ 前端 SSE 客户端支持自动重连、错误处理、取消传播
✅ 后端工具注册简化为装饰器模式，自动化 RBAC/脱敏/审计
✅ 上下文自动注入，减少手动传参
✅ 所有数值结论可追溯到 Evidence
✅ 写操作被拦截并审计
3.2 Phase 2：能力增强（L2，6-8 周）
目标
在核心组件基础上，增强工业场景特有能力。

任务清单
| 任务 | 组件 | 工作量 | 依赖 | 验收标准 | |------|------|--------|------|---------| | T2.1 | RAG 文档库 | 8天 | Phase 1 | 检索/引用/间接注入防护 | | T2.2 | 模型并发控制 | 3天 | Phase 1 | 队列/取消/降级 | | T2.3 | Token 预算与配额 | 5天 | Phase 1 | 路由/限流/缓存 | | T2.4 | 异常主动推送 | 5天 | Phase 1 | 告警规则/升级/订阅 | | T2.5 | 设备多模态诊断 | 10天 | T2.1 | 图像/音频/维修方案 | | T2.6 | OpenTelemetry 集成 | 5天 | Phase 1 | Traces/Metrics/健康检查 | | T2.7 | 移动端适配 | 5天 | Phase 1 | 弱网/离线/语音降级 | | T2.8 | 集成测试 | 4天 | 全部 | 端到端流程验证 |

总工作量：约 45 人天（6-8 周，2-3 人并行）

3.3 Phase 3：受控闭环（L4，10-12 周）
目标
实现写操作全链路治理。

任务清单
| 任务 | 组件 | 工作量 | 依赖 | 验收标准 | |------|------|--------|------|---------| | T3.1 | 草案生成 | 5天 | Phase 2 | 可编辑/约束清单/影响评估 | | T3.2 | 审批与多签 | 8天 | T3.1 | 路由/状态机/审计 | | T3.3 | 受控执行网关 | 10天 | T3.2 | 幂等/超时/阈值/熔断 | | T3.4 | 回滚机制 | 5天 | T3.3 | 回滚点/一键回滚