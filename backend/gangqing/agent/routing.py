from __future__ import annotations

from enum import Enum
from typing import Any
import uuid

import structlog
from pydantic import BaseModel
from pydantic import Field

from gangqing.common.audit import write_audit_event
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import has_capability
from gangqing.schemas.intent import IntentResult, IntentType
from gangqing.schemas.routing import (
    ActionDraft,
    RouteDecision,
    RouteDecisionType,
)


logger = structlog.get_logger(__name__)


class ToolSpec(BaseModel):
    name: str = Field(min_length=1)
    required_capability: str | None = Field(default=None, alias="requiredCapability")

    model_config = {"populate_by_name": True}


def _build_audit_tags(*, intent_result: IntentResult) -> dict[str, str]:
    return {
        "intent": intent_result.intent.value,
        "riskLevel": intent_result.risk_level.value,
        "hasWriteIntent": "true" if intent_result.has_write_intent else "false",
    }


def _build_action_draft(*, intent_result: IntentResult) -> ActionDraft:
    return ActionDraft(
        draftId=f"draft_{uuid.uuid4().hex}",
        actionType="unknown",
        targetResourceSummary="unknown",
        constraints=[],
        riskLevel=intent_result.risk_level,
        riskReasonCodes=list(intent_result.reason_codes),
        requiredCapabilities=[],
    )


def _assert_tools_authorized(*, ctx: RequestContext, tool_specs: list[ToolSpec]) -> None:
    role_raw = (ctx.role or "").strip()
    for spec in tool_specs:
        cap = (spec.required_capability or "").strip() or None
        if cap is None:
            continue
        if not has_capability(role_raw=role_raw, capability=cap):
            write_audit_event(
                ctx=ctx,
                event_type="rbac.denied",
                resource=spec.name,
                action_summary={
                    "stage": "intent.routing.rbac",
                    "toolName": spec.name,
                    "capability": cap,
                    "role": role_raw or None,
                },
                result_status="failure",
                error_code=ErrorCode.FORBIDDEN.value,
                evidence_refs=None,
            )
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Forbidden",
                request_id=ctx.request_id,
                details={
                    "stage": "intent.routing.rbac",
                    "toolName": spec.name,
                    "capability": cap,
                    "role": role_raw or None,
                },
                retryable=False,
            )


def route_intent(
    *,
    ctx: RequestContext,
    intent_result: IntentResult,
    tool_specs: list[ToolSpec],
) -> RouteDecision:
    """Convert intent into execution policy and allowed tools.

    Read-only default:
    - ACTION_EXECUTE: blocked at L1.
    - ACTION_PREPARE: draft-only (no tool execution by default).

    RBAC:
    - Tool list is filtered/validated by capability; missing capability raises FORBIDDEN.
    """

    selected_intent = intent_result.intent

    if intent_result.needs_clarification:
        decision = RouteDecision(
            decisionType=RouteDecisionType.CLARIFY,
            selectedIntent=selected_intent,
            allowedToolNames=[],
            blockedReasonCode=None,
            clarification=list(intent_result.clarification_questions),
            draft=None,
            auditTags=_build_audit_tags(intent_result=intent_result),
        )

        write_audit_event(
            ctx=ctx,
            event_type="routing.decided",
            resource="routing",
            action_summary={
                "decisionType": decision.decision_type.value,
                "selectedIntent": decision.selected_intent.value,
                "allowedToolNames": decision.allowed_tool_names,
                "blockedReasonCode": decision.blocked_reason_code,
                "auditTags": decision.audit_tags,
            },
            result_status="success",
            error_code=None,
            evidence_refs=None,
        )

        return decision

    if selected_intent == IntentType.ACTION_EXECUTE:
        err = AppError(
            ErrorCode.GUARDRAIL_BLOCKED,
            "Write intent blocked by read-only default policy",
            request_id=ctx.request_id,
            details={
                "stage": "intent.routing.guardrail",
                "intent": selected_intent.value,
            },
            retryable=False,
        )

        decision = RouteDecision(
            decisionType=RouteDecisionType.BLOCK,
            selectedIntent=selected_intent,
            allowedToolNames=[],
            blockedReasonCode=err.code.value,
            clarification=None,
            draft=None,
            auditTags=_build_audit_tags(intent_result=intent_result),
        )

        logger.info(
            "intent_routed",
            requestId=ctx.request_id,
            tenantId=ctx.tenant_id,
            projectId=ctx.project_id,
            sessionId=ctx.session_id,
            intent=selected_intent.value,
            decisionType=RouteDecisionType.BLOCK.value,
            blockCode=err.code.value,
        )

        write_audit_event(
            ctx=ctx,
            event_type="routing.decided",
            resource="routing",
            action_summary={
                "decisionType": RouteDecisionType.BLOCK.value,
                "selectedIntent": selected_intent.value,
                "allowedToolNames": [],
                "blockedReasonCode": err.code.value,
                "auditTags": _build_audit_tags(intent_result=intent_result),
            },
            result_status="success",
            error_code=None,
            evidence_refs=None,
        )

        return decision

    if selected_intent == IntentType.ACTION_PREPARE:
        draft = _build_action_draft(intent_result=intent_result)
        decision = RouteDecision(
            decisionType=RouteDecisionType.DRAFT,
            selectedIntent=selected_intent,
            allowedToolNames=[],
            blockedReasonCode=None,
            clarification=None,
            draft=draft,
            auditTags=_build_audit_tags(intent_result=intent_result),
        )

        write_audit_event(
            ctx=ctx,
            event_type="routing.decided",
            resource="routing",
            action_summary={
                "decisionType": decision.decision_type.value,
                "selectedIntent": decision.selected_intent.value,
                "allowedToolNames": decision.allowed_tool_names,
                "blockedReasonCode": decision.blocked_reason_code,
                "auditTags": decision.audit_tags,
            },
            result_status="success",
            error_code=None,
            evidence_refs=None,
        )

        write_audit_event(
            ctx=ctx,
            event_type="draft.created",
            resource="draft",
            action_summary=draft.model_dump(by_alias=True),
            result_status="success",
            error_code=None,
            evidence_refs=None,
        )

        return decision

    _assert_tools_authorized(ctx=ctx, tool_specs=tool_specs)

    allowed = [s.name for s in tool_specs]
    decision = RouteDecision(
        decisionType=RouteDecisionType.ALLOW,
        selectedIntent=selected_intent,
        allowedToolNames=allowed,
        blockedReasonCode=None,
        clarification=None,
        draft=None,
        auditTags=_build_audit_tags(intent_result=intent_result),
    )

    write_audit_event(
        ctx=ctx,
        event_type="routing.decided",
        resource="routing",
        action_summary={
            "decisionType": decision.decision_type.value,
            "selectedIntent": decision.selected_intent.value,
            "allowedToolNames": decision.allowed_tool_names,
            "blockedReasonCode": decision.blocked_reason_code,
            "auditTags": decision.audit_tags,
        },
        result_status="success",
        error_code=None,
        evidence_refs=None,
    )

    return decision
