from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Any

import structlog

from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext
from gangqing.common.settings import load_settings
from gangqing_db.audit_log import AuditLogEvent, insert_audit_log_event


logger = structlog.get_logger(__name__)


_executor_lock = threading.Lock()
_audit_executor: ThreadPoolExecutor | None = None


def _get_audit_executor() -> ThreadPoolExecutor:
    global _audit_executor
    with _executor_lock:
        if _audit_executor is None:
            settings = load_settings()
            _audit_executor = ThreadPoolExecutor(max_workers=int(settings.audit_async_max_workers))
        return _audit_executor


def write_audit_event(
    *,
    ctx: RequestContext,
    event_type: str,
    resource: str | None,
    action_summary: dict[str, Any] | None,
    result_status: str,
    error_code: str | None = None,
    evidence_refs: list[str] | None = None,
) -> None:
    try:
        event = AuditLogEvent(
            eventType=event_type,
            requestId=ctx.request_id,
            tenantId=ctx.tenant_id,
            projectId=ctx.project_id,
            sessionId=ctx.session_id,
            userId=ctx.user_id,
            role=ctx.role,
            resource=resource,
            actionSummary=action_summary,
            result=result_status,
            errorCode=error_code,
            evidenceRefs=evidence_refs,
        )
    except Exception as e:
        logger.warning(
            "audit_event_invalid",
            error=str(e),
            eventType=event_type,
            resource=resource,
            result=result_status,
            requestId=getattr(ctx, "request_id", None),
            tenantId=getattr(ctx, "tenant_id", None),
            projectId=getattr(ctx, "project_id", None),
        )
        return
    try:
        settings = load_settings()
        if settings.audit_async_enabled:
            executor = _get_audit_executor()

            def _write() -> None:
                insert_audit_log_event(event, ctx=ctx)

            executor.submit(_write)
        else:
            insert_audit_log_event(event, ctx=ctx)
    except Exception as e:
        logger.warning(
            "audit_write_failed",
            error=str(e),
            eventType=event.event_type,
            resource=event.resource,
            result=event.result_status,
            requestId=ctx.request_id,
            tenantId=ctx.tenant_id,
            projectId=ctx.project_id,
        )


def write_tool_call_event(
    *,
    ctx: RequestContext,
    tool_name: str,
    args_summary: dict[str, Any] | None,
    result_status: str,
    error_code: str | None = None,
    evidence_refs: list[str] | None = None,
) -> None:
    write_audit_event(
        ctx=ctx,
        event_type=AuditEventType.TOOL_CALL.value,
        resource=tool_name,
        action_summary={
            "toolName": tool_name,
            "argsSummary": args_summary,
        },
        result_status=result_status,
        error_code=error_code,
        evidence_refs=evidence_refs,
    )
