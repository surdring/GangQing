from __future__ import annotations

import time

from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.auth import require_authed_request_context
from gangqing.common.masking import apply_role_based_masking, load_masking_policy
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import has_capability, require_capability
from gangqing.common.redaction import redact_sensitive
from gangqing_db.audit_query import AuditLogRecord, list_audit_events


router = APIRouter()


class AuditEventsResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[AuditLogRecord]

    model_config = {"populate_by_name": True}


def _write_audit_query_audit(
    *,
    request: Request,
    ctx: RequestContext,
    query_summary: dict,
    result_status: str,
    started_monotonic: float,
    total: int | None = None,
    returned: int | None = None,
    masking_hit_count: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    result_summary: dict[str, int | bool] = {"durationMs": duration_ms}
    if total is not None:
        result_summary["total"] = int(total)
    if returned is not None:
        result_summary["returned"] = int(returned)
    if masking_hit_count is not None:
        result_summary["maskingApplied"] = bool(masking_hit_count > 0)
        result_summary["policyHitCount"] = int(masking_hit_count)

    write_audit_event(
        ctx=ctx,
        event_type=AuditEventType.AUDIT_QUERY.value,
        resource=str(getattr(getattr(request, "url", None), "path", None) or "audit.events"),
        action_summary={"query": query_summary},
        result_summary=result_summary,
        result_status=result_status,
        error_code=error_code,
        error_message=error_message,
    )


class TimeRange(BaseModel):
    start: datetime
    end: datetime


class AuditEventsQuery(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    request_id: str | None = Field(default=None, alias="requestId")
    event_type: str | None = Field(default=None, alias="eventType")
    user_id: str | None = Field(default=None, alias="userId")
    tool_name: str | None = Field(default=None, alias="toolName")
    time_range: TimeRange | None = Field(default=None, alias="timeRange")
    unmask: bool = False

    model_config = {"populate_by_name": True}


@router.get("/audit/events", response_model=AuditEventsResponse)
def get_audit_events(
    request: Request,
    ctx: RequestContext = Depends(require_authed_request_context),
    _: RequestContext = Depends(require_capability("audit:event:read")),
    q: AuditEventsQuery = Depends(),
) -> AuditEventsResponse:
    started = time.monotonic()
    query_summary = redact_sensitive(
        {
            "limit": q.limit,
            "offset": q.offset,
            "requestId": q.request_id,
            "eventType": q.event_type,
            "userId": q.user_id,
            "toolName": q.tool_name,
            "timeRange": None
            if q.time_range is None
            else {"start": q.time_range.start.isoformat(), "end": q.time_range.end.isoformat()},
            "unmask": bool(q.unmask),
        }
    )

    # Defense-in-depth: scope must come from request context (headers/JWT), never from query params.
    forbidden_scope_params = {
        "tenantid",
        "projectid",
        "tenant_id",
        "project_id",
        "tenant",
        "project",
    }
    raw_query_keys = {str(k).lower() for k in request.query_params.keys()}
    forbidden_present = sorted(raw_query_keys & forbidden_scope_params)
    if forbidden_present:
        _write_audit_query_audit(
            request=request,
            ctx=ctx,
            query_summary=query_summary,
            result_status="failure",
            started_monotonic=started,
            error_code=ErrorCode.VALIDATION_ERROR.value,
            error_message="Invalid query parameters",
        )
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid query parameters",
            request_id=ctx.request_id,
            details={"forbiddenParams": forbidden_present},
            retryable=False,
        )

    if q.time_range is not None and q.time_range.end <= q.time_range.start:
        _write_audit_query_audit(
            request=request,
            ctx=ctx,
            query_summary=query_summary,
            result_status="failure",
            started_monotonic=started,
            error_code=ErrorCode.VALIDATION_ERROR.value,
            error_message="Invalid timeRange",
        )
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid timeRange",
            request_id=ctx.request_id,
            details={"reason": "end_must_be_greater_than_start"},
            retryable=False,
        )

    try:
        total, items = list_audit_events(
            ctx=ctx,
            limit=q.limit,
            offset=q.offset,
            request_id=q.request_id,
            event_type=q.event_type,
            user_id=q.user_id,
            tool_name=q.tool_name,
            time_range_start=None if q.time_range is None else q.time_range.start,
            time_range_end=None if q.time_range is None else q.time_range.end,
        )

        try:
            policy = load_masking_policy()
        except ValueError as e:
            raise AppError(
                ErrorCode.CONTRACT_VIOLATION,
                "Invalid masking policy",
                request_id=ctx.request_id,
                details={"reason": str(e)},
                retryable=False,
            ) from e
        role_raw = (ctx.role or "").strip() or None
        has_unmask_cap = has_capability(role_raw=(role_raw or ""), capability="data:unmask:read")
        if q.unmask and not has_unmask_cap:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Forbidden",
                request_id=ctx.request_id,
                details={"capability": "data:unmask:read", "reason": "missing_capability"},
                retryable=False,
            )
        can_unmask = bool(q.unmask and has_unmask_cap)

        masking_hits: dict[str, int] = {}
        masked_items: list[AuditLogRecord] = []
        for item in items:
            masked_action_summary, masking_meta = apply_role_based_masking(
                item.action_summary,
                role=role_raw,
                can_unmask=can_unmask,
                policy=policy,
            )
            if masking_meta is not None:
                masked_action_summary = (
                    {} if masked_action_summary is None else dict(masked_action_summary)
                )
                masked_action_summary["masking"] = masking_meta
                policy_key = f"{masking_meta.get('policyId')}@{masking_meta.get('version')}"
                masking_hits[policy_key] = masking_hits.get(policy_key, 0) + 1

            masked_items.append(
                AuditLogRecord(
                    id=item.id,
                    eventType=item.event_type,
                    timestamp=item.timestamp,
                    requestId=item.request_id,
                    tenantId=item.tenant_id,
                    projectId=item.project_id,
                    sessionId=item.session_id,
                    userId=item.user_id,
                    role=item.role,
                    resource=item.resource,
                    actionSummary=masked_action_summary,
                    result=item.result_status,
                    errorCode=item.error_code,
                    evidenceRefs=item.evidence_refs,
                )
            )

        if masking_hits:
            write_audit_event(
                ctx=ctx,
                event_type=AuditEventType.DATA_MASKED.value,
                resource=str(
                    getattr(getattr(request, "url", None), "path", None) or "audit.events"
                ),
                action_summary={
                    "policyHits": [
                        {"policyKey": k, "count": v} for k, v in sorted(masking_hits.items())
                    ],
                },
                result_status="success",
                error_code=None,
            )

        _write_audit_query_audit(
            request=request,
            ctx=ctx,
            query_summary=query_summary,
            result_status="success",
            started_monotonic=started,
            total=total,
            returned=len(masked_items),
            masking_hit_count=sum(masking_hits.values()) if masking_hits else 0,
            error_code=None,
            error_message=None,
        )

        return AuditEventsResponse(total=total, items=masked_items)

    except AppError as e:
        _write_audit_query_audit(
            request=request,
            ctx=ctx,
            query_summary=query_summary,
            result_status="failure",
            started_monotonic=started,
            error_code=e.code.value,
            error_message=e.message,
        )
        raise

    except Exception:
        _write_audit_query_audit(
            request=request,
            ctx=ctx,
            query_summary=query_summary,
            result_status="failure",
            started_monotonic=started,
            error_code=ErrorCode.INTERNAL_ERROR.value,
            error_message="Internal error",
        )
        raise
