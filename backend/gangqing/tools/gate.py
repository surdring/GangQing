from __future__ import annotations

from typing import Any
from typing import Callable

from pydantic import BaseModel, Field

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import has_capability
from gangqing.schemas.intent import IntentResult, IntentType
from gangqing.tools.metadata import ToolAccessMode, ToolMetadata
from gangqing.tools.registry import ToolRegistry


class AllowedToolsInput(BaseModel):
    intent: IntentType
    role: str | None = None
    tenant_id: str = Field(alias="tenantId")
    project_id: str = Field(alias="projectId")

    model_config = {"populate_by_name": True}


class AllowedToolsDecision(BaseModel):
    allowed_tool_names: list[str] = Field(alias="allowedToolNames")

    model_config = {"populate_by_name": True}


def _assert_scope_present(*, ctx: RequestContext) -> None:
    """校验 RequestContext 中必须存在 tenant/project 作用域。

    参数：
    - ctx: RequestContext

    异常：
    - AppError(AUTH_ERROR): tenantId/projectId 缺失
    """
    if not (ctx.tenant_id or "").strip() or not (ctx.project_id or "").strip():
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Authentication context missing tenantId/projectId",
            request_id=ctx.request_id,
            details={"stage": "tool.gate.scope"},
            retryable=False,
        )


def _assert_params_scope(
    *,
    ctx: RequestContext,
    raw_params_summary: dict[str, Any] | None,
) -> None:
    """校验工具调用参数摘要中的 scope 不得跨 tenant/project。

    说明：
    - 当 raw_params_summary 包含 tenantId/projectId 时，必须与 ctx 中一致。
    - 仅用于门禁阶段的防护；真实工具 params 仍应在工具层做强校验。

    异常：
    - AppError(AUTH_ERROR):
      - scope 部分缺失（只给 tenantId 或只给 projectId）
      - scope 与 ctx 不一致（cross-scope）
    """
    if not raw_params_summary:
        return
    tenant_id = raw_params_summary.get("tenantId")
    project_id = raw_params_summary.get("projectId")
    if tenant_id is None and project_id is None:
        return
    if not tenant_id or not project_id:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Authentication context missing tenantId/projectId",
            request_id=ctx.request_id,
            details={"stage": "tool.gate.params_scope", "reason": "partial_scope"},
            retryable=False,
        )
    if str(tenant_id) != str(ctx.tenant_id) or str(project_id) != str(ctx.project_id):
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Cross-scope access is not allowed",
            request_id=ctx.request_id,
            details={
                "stage": "tool.gate.params_scope",
                "tenantId": tenant_id,
                "projectId": project_id,
            },
            retryable=False,
        )


def compute_allowed_tools(*, ctx: RequestContext, intent_result: IntentResult, registry: ToolRegistry) -> AllowedToolsDecision:
    """根据 role + intent + registry 计算本次请求允许调用的工具列表。

    参数：
    - ctx: RequestContext（包含 role/tenant/project 等）
    - intent_result: IntentResult（包含 intent 与是否写意图）
    - registry: ToolRegistry（已注册工具元数据）

    返回：
    - AllowedToolsDecision: allowedToolNames

    异常：
    - AppError(GUARDRAIL_BLOCKED): 检测到写意图（只读默认策略）
    - AppError(AUTH_ERROR): scope 缺失
    """
    _assert_scope_present(ctx=ctx)

    if intent_result.intent in {IntentType.ACTION_PREPARE, IntentType.ACTION_EXECUTE} or bool(
        intent_result.has_write_intent
    ):
        raise AppError(
            ErrorCode.GUARDRAIL_BLOCKED,
            "Write intent blocked by read-only default policy",
            request_id=ctx.request_id,
            details={
                "stage": "tool.gate.intent",
                "intent": intent_result.intent.value,
            },
            retryable=False,
        )

    role_raw = (ctx.role or "").strip()
    allowed: list[str] = []
    for meta in registry.list_enabled():
        if meta.governance.access_mode != ToolAccessMode.READ_ONLY:
            continue

        cap = (meta.rbac.required_capability or "").strip() or None
        if cap is not None and not has_capability(role_raw=role_raw, capability=cap):
            continue

        allowed.append(meta.tool_name)

    return AllowedToolsDecision(allowedToolNames=allowed)


def _find_tool_meta(*, registry: ToolRegistry, tool_name: str) -> ToolMetadata | None:
    for meta in registry.list_enabled():
        if meta.tool_name == tool_name:
            return meta
    return None


def assert_tool_call_allowed(
    *,
    ctx: RequestContext,
    intent_result: IntentResult,
    registry: ToolRegistry,
    tool_name: str,
    tool_call_id: str | None,
    raw_params_summary: dict[str, Any] | None,
    audit_fn: Callable[..., Any] = write_audit_event,
) -> None:
    """在工具执行前进行强制门禁校验。

    参数：
    - ctx: RequestContext
    - intent_result: IntentResult
    - registry: ToolRegistry
    - tool_name: 工具名
    - tool_call_id: 本次工具调用唯一标识（用于审计/追溯）
    - raw_params_summary: 脱敏后的参数摘要（用于审计/门禁 scope 检查）
    - audit_fn: 审计写入函数（允许测试注入）

    异常：
    - AppError(AUTH_ERROR/GUARDRAIL_BLOCKED/FORBIDDEN): 任何门禁拒绝
    """
    _assert_scope_present(ctx=ctx)
    _assert_params_scope(ctx=ctx, raw_params_summary=raw_params_summary)

    try:
        decision = compute_allowed_tools(ctx=ctx, intent_result=intent_result, registry=registry)
    except AppError as e:
        audit_fn(
            ctx=ctx,
            event_type=AuditEventType.RBAC_DENIED.value,
            resource=tool_name,
            action_summary={
                "stage": "tool.gate",
                "intent": intent_result.intent.value,
                "toolName": tool_name,
                "toolCallId": tool_call_id,
                "durationMs": 0,
                "evidenceRefs": None,
                "reasonCode": e.code.value,
                "argsSummary": raw_params_summary,
            },
            result_status="failure",
            error_code=e.code.value,
            evidence_refs=None,
        )
        raise

    if tool_name not in set(decision.allowed_tool_names):
        meta = _find_tool_meta(registry=registry, tool_name=tool_name)
        details: dict[str, Any] = {
            "stage": "tool.gate.allowed_tools",
            "intent": intent_result.intent.value,
            "toolName": tool_name,
            "allowedToolNames": decision.allowed_tool_names,
            "knownTool": meta is not None,
        }
        err = AppError(
            ErrorCode.FORBIDDEN,
            "Forbidden",
            request_id=ctx.request_id,
            details=details,
            retryable=False,
        )

        audit_fn(
            ctx=ctx,
            event_type=AuditEventType.RBAC_DENIED.value,
            resource=tool_name,
            action_summary={
                "stage": "tool.gate",
                "intent": intent_result.intent.value,
                "toolName": tool_name,
                "toolCallId": tool_call_id,
                "durationMs": 0,
                "evidenceRefs": None,
                "reasonCode": err.code.value,
                "argsSummary": raw_params_summary,
                "details": details,
            },
            result_status="failure",
            error_code=err.code.value,
            evidence_refs=None,
        )
        raise err
