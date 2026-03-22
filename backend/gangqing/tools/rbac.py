from __future__ import annotations

from typing import Any, Callable

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import assert_has_capability


def require_tool_capability(
    *,
    ctx: RequestContext,
    capability: str,
    tool_name: str | None = None,
    audit_fn: Callable[..., Any] = write_audit_event,
) -> None:
    role_raw = (ctx.role or "").strip()
    try:
        assert_has_capability(ctx=ctx, role_raw=role_raw, capability=capability)
    except AppError as e:
        if e.code == ErrorCode.FORBIDDEN:
            audit_fn(
                ctx=ctx,
                event_type=AuditEventType.RBAC_DENIED.value,
                resource=tool_name or "tool",
                action_summary={
                    "capability": capability,
                    "role": role_raw or None,
                    "details": e.details,
                },
                result_status="failure",
                error_code=e.code.value,
            )
        raise
