from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.auth import require_authed_request_context
from gangqing.common.masking import apply_role_based_masking, load_masking_policy
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import require_capability
from gangqing_db.audit_query import AuditLogRecord, list_audit_events


router = APIRouter()


class AuditEventsResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[AuditLogRecord]

    model_config = {"populate_by_name": True}


@router.get("/audit/events", response_model=AuditEventsResponse)
def get_audit_events(
    request: Request,
    ctx: RequestContext = Depends(require_authed_request_context),
    _: RequestContext = Depends(require_capability("audit:event:read")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    request_id: str | None = Query(default=None, alias="requestId"),
) -> AuditEventsResponse:
    total, items = list_audit_events(
        ctx=ctx,
        limit=limit,
        offset=offset,
        request_id=request_id,
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

    masking_hits: dict[str, int] = {}
    masked_items: list[AuditLogRecord] = []
    for item in items:
        masked_action_summary, masking_meta = apply_role_based_masking(
            item.action_summary,
            role=role_raw,
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
            resource=str(getattr(getattr(request, "url", None), "path", None) or "audit.events"),
            action_summary={
                "policyHits": [
                    {"policyKey": k, "count": v} for k, v in sorted(masking_hits.items())
                ],
            },
            result_status="success",
            error_code=None,
        )

    return AuditEventsResponse(total=total, items=masked_items)
