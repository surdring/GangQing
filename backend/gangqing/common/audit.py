from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time
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
    result_summary: dict[str, Any] | None = None,
    result_status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    tool_call_id: str | None = None,
    evidence_refs: list[str] | None = None,
) -> None:
    try:
        error_obj = None
        if error_code is not None and error_message is not None:
            error_obj = {"code": error_code, "message": error_message}
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
            resultSummary=result_summary,
            toolCallId=tool_call_id,
            stepId=ctx.step_id,
            error=error_obj,
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

            def _write_with_retry() -> None:
                last_err: Exception | None = None
                for attempt in range(1, 3):
                    try:
                        insert_audit_log_event(event, ctx=ctx)
                        return
                    except Exception as e:
                        last_err = e
                        time.sleep(0.05 * attempt)
                raise last_err or RuntimeError("Audit write failed")
            try:
                executor.submit(_write_with_retry)
            except Exception:
                insert_audit_log_event(event, ctx=ctx)
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
    tool_call_id: str | None = None,
    duration_ms: int | None = None,
    args_summary: dict[str, Any] | None,
    result_status: str,
    error_code: str | None = None,
    evidence_refs: list[str] | None = None,
) -> None:
    write_audit_event(
        ctx=ctx,
        event_type=AuditEventType.TOOL_CALL_AUDIT.value,
        resource=tool_name,
        tool_call_id=tool_call_id,
        action_summary={
            "toolName": tool_name,
            "durationMs": duration_ms,
            "argsSummary": args_summary,
            "stepId": ctx.step_id,
        },
        result_status=result_status,
        error_code=error_code,
        evidence_refs=evidence_refs,
    )
